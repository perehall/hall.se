#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finalize_post_workout_ui import build_outcome_insight, fmt_distance, fmt_duration, fmt_hr

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
PERFORMANCE_FILE = ROOT / "data" / "performance_history.json"
COACH_FILE = ROOT / "data" / "coach.json"
INDEX_FILE = ROOT / "index.html"

CSS_MARKER = "/* week-activity-insight-v1 */"
CARD_MARKER = 'data-week-activity-insight="'

CSS = r"""
/* week-activity-insight-v1 */
.week-activity-insight{margin:9px 0 7px;padding:12px 13px;border:1px solid #dbe5df;border-radius:14px;background:#fff}
.week-activity-insight-kicker{font-size:.66rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#64748b}
.week-activity-insight h3{margin:4px 0 6px;font-size:1rem;line-height:1.28;letter-spacing:-.01em}
.week-activity-insight p{margin:0;color:#475569;font-size:.82rem;line-height:1.45}
.week-activity-plan-impact{margin-top:8px!important;padding-top:8px;border-top:1px solid #e2e8f0;color:#334155!important}
.week-activity-plan-impact strong{color:#0f172a}
.week-activity-insight details{margin-top:8px}
.week-activity-insight summary{cursor:pointer;list-style:none;color:#64748b;font-size:.75rem;font-weight:800}
.week-activity-insight summary::-webkit-details-marker{display:none}
.week-activity-insight summary:after{content:" +"}
.week-activity-insight details[open] summary:after{content:" −"}
.week-activity-facts{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}
.week-activity-facts>div{padding:7px 8px;border-radius:10px;background:#f8fafc}
.week-activity-facts span{display:block;color:#64748b;font-size:.61rem;font-weight:850;text-transform:uppercase;letter-spacing:.05em}
.week-activity-facts strong{display:block;margin-top:2px;font-size:.82rem;font-variant-numeric:tabular-nums}
@media(max-width:620px){.week-activity-insight{padding:11px 12px}.week-activity-facts{gap:5px}.week-activity-facts>div{padding:7px}}
""".strip()

DAY_RE = re.compile(r'<div class="day(?P<classes>[^"]*)" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">')


def load_json(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date") or ""
    return value[:10] if isinstance(value, str) and len(value) >= 10 else ""


def day_ranges(page):
    matches = list(DAY_RE.finditer(page))
    result = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
        result.append((match.start(), end, match))
    return result


def analysis_for(activity, coach_state):
    activity_id = activity.get("id")
    matches = [
        row for row in coach_state.get("analyses") or []
        if str(row.get("activity_id")) == str(activity_id)
    ]
    if not matches:
        return None
    return max(matches, key=lambda row: row.get("generated_at_utc") or "")


def performance_for(activity, performance_state):
    activity_id = activity.get("id")
    return next(
        (
            row for row in performance_state.get("entries") or []
            if str(row.get("activity_id")) == str(activity_id)
        ),
        None,
    )


def activity_label(activity):
    return (
        str(activity.get("display_label") or "").strip()
        or str(activity.get("sport_type") or "").strip()
        or "Aktivitet"
    )


def render_activity_insight(day, activity, analysis, performance):
    insight = build_outcome_insight(day, analysis, performance)
    action = (analysis or {}).get("plan_action") or {}
    recommendation = str(action.get("recommendation") or "").strip()
    impact_html = (
        f'<p class="week-activity-plan-impact"><strong>Påverkan på planen:</strong> '
        f'{html.escape(recommendation)}</p>'
        if recommendation else ""
    )
    facts = [
        ("Tid", fmt_duration(activity.get("elapsed_time_s"))),
        ("Distans", fmt_distance(activity)),
        ("Snittpuls", fmt_hr(activity)),
    ]
    facts_html = "".join(
        f'<div><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in facts
    )
    return f"""<section class="week-activity-insight" data-week-activity-insight="{html.escape(str(activity.get("id")))}">
  <div class="week-activity-insight-kicker">{html.escape(activity_label(activity))} · Coach Insight</div>
  <h3>{html.escape(insight["headline"])}</h3>
  <p>{html.escape(insight["body"])}</p>
  {impact_html}
  <details><summary>Visa passfakta</summary><div class="week-activity-facts">{facts_html}</div></details>
</section>"""


def add_css(page):
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Veckoinsikter: sidan saknar </style>")
    return page.replace("</style>", CSS + "\n</style>", 1)


def insertion_point(block):
    # Keep the compact Strava summary first, then the new signal card, then raw historical AI details.
    historical = block.find('<details class="historical-coach">')
    if historical >= 0:
        return historical
    coach = block.find('<div class="coach')
    if coach >= 0:
        return coach
    return len(block)


def apply_week_activity_insights(page, plan, activities_state, coach_state, performance_state, today):
    week_start = str((plan.get("meta") or {}).get("week_start") or "")
    week_end = str((plan.get("meta") or {}).get("week_end") or "")
    days_by_date = {day.get("date"): day for day in plan.get("days") or []}

    activities = [
        activity for activity in activities_state.get("activities") or []
        if week_start <= local_date(activity) <= week_end and local_date(activity) < today
    ]
    if not activities:
        return page

    page = add_css(page)
    grouped = {}
    for activity in activities:
        grouped.setdefault(local_date(activity), []).append(activity)

    for start, end, match in reversed(day_ranges(page)):
        day_text = match.group("date")
        day_activities = grouped.get(day_text) or []
        if not day_activities:
            continue
        day = days_by_date.get(day_text) or {"date": day_text}
        block = page[start:end]

        cards = []
        for activity in sorted(day_activities, key=lambda row: row.get("start_date_local") or row.get("start_date") or ""):
            marker = f'{CARD_MARKER}{html.escape(str(activity.get("id")))}"'
            if marker in block:
                continue
            cards.append(
                render_activity_insight(
                    day,
                    activity,
                    analysis_for(activity, coach_state),
                    performance_for(activity, performance_state),
                )
            )
        if not cards:
            continue
        point = insertion_point(block)
        block = block[:point] + "".join(cards) + block[point:]
        page = page[:start] + block + page[end:]

    return page


def main():
    plan = load_json(PLAN_FILE, {})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    coach = load_json(COACH_FILE, {"analyses": []})
    performance = load_json(PERFORMANCE_FILE, {"entries": []})
    page = INDEX_FILE.read_text(encoding="utf-8")
    tz = ZoneInfo((plan.get("meta") or {}).get("timezone") or "Europe/Stockholm")
    today = datetime.now(tz).date().isoformat()

    rendered = apply_week_activity_insights(page, plan, activities, coach, performance, today)
    INDEX_FILE.write_text(rendered, encoding="utf-8")

    expected = [
        activity for activity in activities.get("activities") or []
        if str((plan.get("meta") or {}).get("week_start") or "") <= local_date(activity)
        <= str((plan.get("meta") or {}).get("week_end") or "")
        and local_date(activity) < today
    ]
    verify = INDEX_FILE.read_text(encoding="utf-8")
    missing = [
        str(activity.get("id")) for activity in expected
        if f'{CARD_MARKER}{html.escape(str(activity.get("id")))}"' not in verify
    ]
    if missing:
        raise RuntimeError("Veckoinsikter: saknar retroaktiv Coach Insight för " + repr(missing))
    if expected and CSS_MARKER not in verify:
        raise RuntimeError("Veckoinsikter: CSS saknas")
    print(f"Veckoinsikter OK: {len(expected)} tidigare aktiviteter har Coach Insight.")


if __name__ == "__main__":
    main()
