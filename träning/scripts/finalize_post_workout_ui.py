#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
COACH_FILE = ROOT / "data" / "coach.json"
INDEX_FILE = ROOT / "index.html"

CSS_MARKER = "/* post-workout-ux-v1 */"
CARD_MARKER = 'data-post-workout-state="completed"'

CSS = r"""
/* post-workout-ux-v1 */
.today-outcome{background:#fff;border:1px solid #dbe5df;border-radius:20px;padding:18px 20px;margin:0 0 14px;box-shadow:0 8px 24px rgba(15,23,42,.06)}
.today-outcome-head{display:flex;align-items:center;gap:12px;margin-bottom:7px}
.today-outcome-check{width:34px;height:34px;flex:0 0 34px;border-radius:50%;display:grid;place-items:center;background:#dcfce7;color:#15803d;font-weight:950;font-size:1rem}
.today-outcome-kicker{font-size:.7rem;font-weight:900;letter-spacing:.09em;text-transform:uppercase;color:#64748b}
.today-outcome h2{font-size:1.2rem;line-height:1.25;margin:1px 0 0}
.today-outcome-note{margin:0 0 15px;color:#334155;font-size:.92rem;line-height:1.45}
.today-outcome-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 14px}
.today-outcome-metrics>div{border:1px solid #e2e8f0;border-radius:13px;padding:10px 11px;background:#f8fafc}
.today-outcome-metrics dt{font-size:.67rem;font-weight:850;letter-spacing:.06em;text-transform:uppercase;color:#64748b}
.today-outcome-metrics dd{margin:2px 0 0;font-size:1rem;font-weight:900;font-variant-numeric:tabular-nums}
.today-outcome-compare{display:grid;grid-template-columns:1fr 1fr;border:1px solid #e2e8f0;border-radius:15px;overflow:hidden;margin-bottom:12px}
.today-outcome-compare>div{padding:12px 13px;min-width:0}
.today-outcome-compare>div+div{border-left:1px solid #e2e8f0;background:#fbfdfc}
.today-outcome-label{display:block;margin-bottom:4px;font-size:.67rem;font-weight:900;letter-spacing:.07em;text-transform:uppercase;color:#64748b}
.today-outcome-compare strong{display:block;font-size:.9rem;line-height:1.4}
.today-outcome-coach{padding:12px 13px;border:1px solid #ddd6fe;border-radius:15px;background:#faf5ff;margin-bottom:12px}
.today-outcome-coach p{margin:0;color:#3b0764;font-size:.9rem;line-height:1.45}
.today-outcome-impact{margin-top:8px;padding-top:8px;border-top:1px solid #e9d5ff;color:#4c1d95!important}
.today-outcome-next{padding:12px 13px;border:1px solid #cbd5e1;border-radius:15px;background:#f8fafc}
.today-outcome-next strong{display:block;font-size:.96rem;line-height:1.4}
.today-outcome-next small{display:block;margin-top:4px;color:#64748b;font-size:.76rem;line-height:1.35}
.today-outcome-link{display:inline-block;margin-top:11px;color:#475569;font-size:.8rem;font-weight:800;text-underline-offset:3px}
@media(max-width:620px){
  .today-outcome{padding:16px 15px;border-radius:17px}
  .today-outcome-metrics{gap:6px}
  .today-outcome-metrics>div{padding:9px 8px}
  .today-outcome-metrics dd{font-size:.92rem}
  .today-outcome-compare{grid-template-columns:1fr}
  .today-outcome-compare>div+div{border-left:0;border-top:1px solid #e2e8f0}
}
""".strip()

MONTHS = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "maj", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec",
}


def load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def local_date(activity):
    value = activity.get("start_date_local") or ""
    return value[:10] if len(value) >= 10 else ""


def fmt_duration(seconds):
    if seconds is None:
        return "—"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def fmt_distance(activity):
    meters = float(activity.get("distance_m") or 0)
    if meters <= 0:
        return "—"
    if activity.get("sport_type") == "Swim":
        return f"{round(meters):,} m".replace(",", " ")
    return f"{meters / 1000:.2f} km".replace(".", ",")


def fmt_hr(activity):
    value = activity.get("average_heartrate")
    return str(round(float(value))) if value else "—"


def first_sentence(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^Utfall:\s*", "", text, flags=re.IGNORECASE)
    match = re.match(r"(.+?[.!?])(?:\s|$)", text)
    return (match.group(1) if match else text).strip()


def find_primary_activity(day, activities):
    if not activities:
        return None
    activity_id = day.get("activity_id")
    if activity_id is not None:
        linked = next((a for a in activities if str(a.get("id")) == str(activity_id)), None)
        if linked:
            return linked
    return max(activities, key=lambda a: a.get("start_date_local") or a.get("start_date") or "")


def find_coach_analysis(day, coach_state, today):
    analyses = [a for a in coach_state.get("analyses", []) if a.get("activity_date") == today]
    if not analyses:
        return None
    activity_id = day.get("activity_id")
    if activity_id is not None:
        linked = next((a for a in analyses if str(a.get("activity_id")) == str(activity_id)), None)
        if linked:
            return linked
    return max(analyses, key=lambda a: a.get("generated_at_utc") or "")


def planned_text(day):
    return (
        str(day.get("planned_session") or "").strip()
        or str(day.get("original_session") or "").strip()
        or "Planerad dos saknas i historiken."
    )


def actual_text(day, activity):
    actual = day.get("actual_session") or {}
    reps = actual.get("reps")
    up = actual.get("hill_duration_s_approx")
    down = actual.get("downhill_recovery_s_approx")
    if reps:
        bits = [f"{reps} backar"]
        if up:
            bits.append(f"ca {round(float(up))} s upp")
        if down:
            bits.append(f"ca {round(float(down))} s jogg ned")
        return " · ".join(bits)
    session = str(day.get("session") or "").strip()
    planned = planned_text(day)
    if session and session != planned:
        return session
    return str((activity or {}).get("name") or "Genomfört pass").strip()


def next_planned_day(plan, today):
    for day in sorted(plan.get("days", []), key=lambda d: d.get("date") or ""):
        if day.get("date", "") <= today:
            continue
        if day.get("status") == "completed":
            continue
        return day
    return None


def format_day(day):
    if not day:
        return ""
    date_value = datetime.strptime(day["date"], "%Y-%m-%d").date()
    label = str(day.get("label") or "").strip()
    return f"{label} {date_value.day} {MONTHS[date_value.month]}"


def completion_note(day):
    note = first_sentence(day.get("development_focus"))
    if note:
        return note
    return "Passet är registrerat och faktisk dos har vägts in i den fortsatta planen."


def render_post_workout(day, activity, analysis, next_day):
    metrics = [
        ("Tid", fmt_duration((activity or {}).get("elapsed_time_s"))),
        ("Distans", fmt_distance(activity or {})),
        ("Snittpuls", fmt_hr(activity or {})),
    ]
    metrics_html = "".join(
        f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>"
        for label, value in metrics
    )

    coach_html = ""
    adjusted_next = False
    if analysis:
        assessment = analysis.get("assessment") or {}
        action = analysis.get("plan_action") or {}
        summary = first_sentence(assessment.get("summary"))
        recommendation = str(action.get("recommendation") or "").strip()
        applied = bool((analysis.get("auto_apply") or {}).get("applied"))
        adjusted_next = bool(
            applied and next_day and action.get("target_date") == next_day.get("date")
        )
        if summary or recommendation:
            impact = (
                f'<p class="today-outcome-impact"><strong>Effekt på planen:</strong> '
                f'{html.escape(recommendation)}</p>'
                if recommendation else ""
            )
            coach_html = f"""
  <div class="today-outcome-coach">
    <span class="today-outcome-label">Coachens bedömning</span>
    <p>{html.escape(summary or "Genomförandet är inläst i nästa beslut.")}</p>
    {impact}
  </div>"""

    next_html = ""
    if next_day:
        adjustment = (
            "Justerat efter dagens faktiska utfall."
            if adjusted_next else
            "Nästa planerade steg i mikrocykeln."
        )
        next_html = f"""
  <div class="today-outcome-next">
    <span class="today-outcome-label">Nästa pass · {html.escape(format_day(next_day))}</span>
    <strong>{html.escape(str(next_day.get("session") or "Öppet beslut"))}</strong>
    <small>{html.escape(adjustment)}</small>
  </div>"""

    return f"""<section class="today-outcome" {CARD_MARKER} aria-labelledby="todayOutcomeTitle">
  <div class="today-outcome-head">
    <span class="today-outcome-check" aria-hidden="true">✓</span>
    <div><div class="today-outcome-kicker">Dagens pass</div><h2 id="todayOutcomeTitle">Genomfört</h2></div>
  </div>
  <p class="today-outcome-note">{html.escape(completion_note(day))}</p>
  <dl class="today-outcome-metrics">{metrics_html}</dl>
  <div class="today-outcome-compare" aria-label="Planerad och faktisk dos">
    <div><span class="today-outcome-label">Plan</span><strong>{html.escape(planned_text(day))}</strong></div>
    <div><span class="today-outcome-label">Utfall</span><strong>{html.escape(actual_text(day, activity))}</strong></div>
  </div>
  {coach_html}
  {next_html}
  <a class="today-outcome-link" href="#aktuell-vecka">Se hela planen ↓</a>
</section>"""


def add_css(page):
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Post-workout UX: sidan saknar </style>")
    return page.replace("</style>", CSS + "\n</style>", 1)


def add_week_anchor(page):
    old = '<h2 class="section">Aktuell vecka</h2>'
    new = '<h2 class="section" id="aktuell-vecka">Aktuell vecka</h2>'
    if new in page:
        return page
    if old not in page:
        raise RuntimeError("Post-workout UX: rubriken Aktuell vecka saknas")
    return page.replace(old, new, 1)


def replace_training_brain(page, card):
    if CARD_MARKER in page:
        return page
    start_marker = "<!-- training-brain-v1:start -->"
    end_marker = "<!-- training-brain-v1:end -->"
    start = page.find(start_marker)
    end = page.find(end_marker, start + len(start_marker)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise RuntimeError("Post-workout UX: träningshjärnans stabila renderingsmarkörer saknas")
    end += len(end_marker)
    replacement = start_marker + "\n" + card + "\n" + end_marker
    return page[:start] + replacement + page[end:]


def apply_post_workout_ui(page, plan, activities_state, coach_state, today):
    day = next((d for d in plan.get("days", []) if d.get("date") == today), None)
    today_activities = [
        a for a in activities_state.get("activities", []) if local_date(a) == today
    ]
    if not day or not today_activities:
        return page

    activity = find_primary_activity(day, today_activities)
    analysis = find_coach_analysis(day, coach_state, today)
    next_day = next_planned_day(plan, today)
    card = render_post_workout(day, activity, analysis, next_day)

    page = add_css(page)
    page = add_week_anchor(page)
    page = replace_training_brain(page, card)
    return page


def main():
    plan = load_json(PLAN_FILE, {})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    coach = load_json(COACH_FILE, {"analyses": []})
    page = INDEX_FILE.read_text(encoding="utf-8")
    tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
    today = datetime.now(tz).date().isoformat()

    rendered = apply_post_workout_ui(page, plan, activities, coach, today)
    INDEX_FILE.write_text(rendered, encoding="utf-8")

    today_has_activity = any(
        local_date(a) == today for a in activities.get("activities", [])
    )
    if today_has_activity and any(d.get("date") == today for d in plan.get("days", [])):
        verify = INDEX_FILE.read_text(encoding="utf-8")
        required = [
            CSS_MARKER,
            CARD_MARKER,
            'id="todayOutcomeTitle">Genomfört</h2>',
            'class="today-outcome-metrics"',
            'class="today-outcome-compare"',
            'id="aktuell-vecka"',
            'class="today-outcome-link"',
        ]
        missing = [marker for marker in required if marker not in verify]
        if missing:
            raise RuntimeError("Post-workout UX-validering misslyckades: " + repr(missing))
        print("Post-workout UX OK: genomfört → plan/utfall → coachkonsekvens → nästa pass.")
    else:
        print("Post-workout UX: inget genomfört pass idag; före-pass-läget lämnas oförändrat.")


if __name__ == "__main__":
    main()
