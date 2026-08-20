#!/usr/bin/env python3
import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
INDEX_FILE = ROOT / "index.html"
SUMMARY_FILE = ROOT / "data" / "dashboard_summary.json"

SPORT_GROUPS = {
    "Run": "Löpning",
    "TrailRun": "Löpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "MountainBikeRide": "MTB/XC",
    "Ride": "Cykel",
    "VirtualRide": "Cykel",
    "WeightTraining": "Styrka",
}


def activity_duration_s(activity):
    """Canonical dashboard duration: full recorded session time.

    Use elapsed_time so dashboard totals match the duration shown on the
    activity/day cards. Fall back to moving_time only when elapsed is absent.
    """
    elapsed = activity.get("elapsed_time_s")
    if elapsed is not None and int(elapsed) >= 0:
        return int(elapsed)
    moving = activity.get("moving_time_s")
    return int(moving or 0)


def fmt_compact_duration(seconds):
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def local_date(activity):
    value = activity.get("start_date_local") or ""
    return value[:10] if len(value) >= 10 else ""


def replace_between(text, start_marker, end_marker, replacement):
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"Dashboard marker saknas: {start_marker!r}")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"Dashboard marker saknas: {end_marker!r}")
    return text[:start] + replacement + text[end:]


plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
page = INDEX_FILE.read_text(encoding="utf-8")

week_start = plan["meta"]["week_start"]
week_end = plan["meta"]["week_end"]
activities = state.get("activities", [])

ids = [int(a["id"]) for a in activities if a.get("id") is not None]
if len(ids) != len(set(ids)):
    raise RuntimeError("Dashboardvalidering: dubbla aktivitets-ID i activities.json")

week_activities = [
    a for a in activities
    if local_date(a) and week_start <= local_date(a) <= week_end
]

pass_count = len(week_activities)
training_days = len({local_date(a) for a in week_activities})
total_seconds = sum(activity_duration_s(a) for a in week_activities)

sport_seconds = {}
for activity in week_activities:
    group = SPORT_GROUPS.get(
        activity.get("sport_type"), activity.get("sport_type") or "Övrigt"
    )
    sport_seconds[group] = sport_seconds.get(group, 0) + activity_duration_s(activity)

# Independent arithmetic invariant: sport breakdown must equal weekly total.
if sum(sport_seconds.values()) != total_seconds:
    raise RuntimeError("Dashboardvalidering: grenfördelning summerar inte till total passtid")

summary = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "week_start": week_start,
    "week_end": week_end,
    "duration_definition": "elapsed_time_s; moving_time_s endast som fallback",
    "pass_count": pass_count,
    "training_days": training_days,
    "session_time_s": total_seconds,
    "by_sport_s": dict(sorted(sport_seconds.items())),
    "activity_ids": [a.get("id") for a in week_activities],
}
SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

metrics_html = f'''<div class="metrics">
    <div class="metric"><strong>{pass_count}</strong><span>pass</span></div>
    <div class="metric"><strong>{fmt_compact_duration(total_seconds)}</strong><span>passtid</span></div>
    <div class="metric"><strong>{training_days}</strong><span>träningsdagar</span></div>
  </div>
  '''
page = replace_between(
    page,
    '<div class="metrics">',
    '<div class="dashboard-grid">',
    metrics_html,
)

sport_rows = []
for group, seconds in sorted(sport_seconds.items(), key=lambda item: item[1], reverse=True):
    pct = round(seconds / total_seconds * 100) if total_seconds else 0
    sport_rows.append(
        f'''<div class="sport-row">
  <div class="sport-head"><span>{html.escape(group)}</span><strong>{fmt_compact_duration(seconds)}</strong></div>
  <div class="sport-track"><div class="sport-fill" style="width:{pct}%"></div></div>
</div>'''
    )
sport_distribution = "".join(sport_rows) or '<div class="dashboard-empty">Ingen registrerad aktivitet denna vecka ännu.</div>'

sport_card = f'''<div class="dashboard-card">
      <div class="dashboard-title">Grenfördelning · passtid</div>
      {sport_distribution}
    </div>
    '''
page = replace_between(
    page,
    '<div class="dashboard-card">\n      <div class="dashboard-title">Grenfördelning',
    '<div class="dashboard-card">\n      <div class="dashboard-title">Plan → utfall',
    sport_card,
)

INDEX_FILE.write_text(page, encoding="utf-8")

# Fail closed: never publish if the rendered dashboard cannot be proven to
# contain the exact independently calculated aggregates.
rendered = INDEX_FILE.read_text(encoding="utf-8")
required = [
    f'<div class="metric"><strong>{pass_count}</strong><span>pass</span></div>',
    f'<div class="metric"><strong>{fmt_compact_duration(total_seconds)}</strong><span>passtid</span></div>',
    f'<div class="metric"><strong>{training_days}</strong><span>träningsdagar</span></div>',
    '<div class="dashboard-title">Grenfördelning · passtid</div>',
]
for group, seconds in sport_seconds.items():
    required.append(
        f'<div class="sport-head"><span>{html.escape(group)}</span><strong>{fmt_compact_duration(seconds)}</strong></div>'
    )

missing = [snippet for snippet in required if snippet not in rendered]
if missing:
    raise RuntimeError("Dashboardvalidering misslyckades; publicering stoppas: " + repr(missing))

print(
    f"Dashboard OK: {pass_count} pass, {fmt_compact_duration(total_seconds)} passtid, "
    f"{training_days} träningsdagar."
)
