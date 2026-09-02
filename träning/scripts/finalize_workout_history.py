#!/usr/bin/env python3
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
INDEX_FILE = ROOT / "index.html"
CSS_MARKER = "/* workout-history-v2 */"

CSS = r'''
/* workout-history-v2 */
.workout-history{margin:13px 0 4px;padding:12px 13px;border:1px solid #bfdbfe;background:#f8fbff;border-radius:14px}.workout-history-label{margin-bottom:7px;color:#1d4ed8;font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em}.workout-history .swim-set-list{margin-top:9px}.workout-history-note{margin-top:8px;color:#64748b;font-size:.78rem}.workout-equipment{display:grid;gap:2px;margin-top:7px;color:#475569;font-size:.8rem}.workout-equipment strong{color:#334155}
'''.strip()

EQUIPMENT_LABELS = {
    "paddles": "paddlar",
    "paddlar": "paddlar",
    "pull_buoy": "dolme",
    "dolme": "dolme",
    "fins": "fenor",
    "fenor": "fenor",
    "snorkel": "snorkel",
    "kickboard": "platta",
    "platta": "platta",
}


def activity_date(activity):
    value = activity.get("start_date_local") or ""
    return value[:10] if len(value) >= 10 else ""


def fmt_distance(value):
    meters = int(round(float(value)))
    return f"{meters} m"


def fmt_equipment(value, unknown="ej registrerat"):
    if value is None:
        return unknown
    if value in ("none", "inga"):
        return "inga"
    if isinstance(value, str):
        if value in ("tbd", "to_be_determined"):
            return "fastställs med exakt pass"
        return EQUIPMENT_LABELS.get(value, value)
    if isinstance(value, list):
        if not value:
            return "inga"
        return " + ".join(EQUIPMENT_LABELS.get(str(item), str(item)) for item in value)
    raise RuntimeError(f"Workout history: ogiltigt hjälpmedelsvärde {value!r}")


def matching_swim_dates(activities):
    dates = set()
    for activity in activities:
        if activity.get("sport_type") != "Swim":
            continue
        if activity.get("plan_relation") == "separate":
            continue
        date = activity_date(activity)
        if date:
            dates.add(date)
    return dates


def render_workout(day, completed):
    workout = day.get("watch_workout") or {}
    title = workout.get("name") or day.get("session") or "Simning"
    rows = []
    has_lap_rest = False

    planned_equipment = fmt_equipment(
        workout.get("equipment"),
        unknown="ej registrerat i ordinationen",
    )
    actual_equipment = fmt_equipment(
        day.get("actual_swim_equipment"),
        unknown="ej registrerat",
    )

    for block in workout.get("blocks", []):
        repeat = int(block.get("repeat") or 1)
        steps = block.get("steps") or []
        swim_steps = [step for step in steps if step.get("kind") == "swim"]
        timed_rests = [step for step in steps if step.get("kind") == "rest"]
        lap_rests = [step for step in steps if step.get("kind") == "lap_rest"]

        if lap_rests and not swim_steps:
            has_lap_rest = True
            continue

        rest_text = ""
        if timed_rests:
            seconds = timed_rests[0].get("duration_s")
            if seconds:
                rest_text = f" · {int(seconds)} s vila"

        for step in swim_steps:
            distance = step.get("distance_m")
            if not distance:
                continue
            dose = fmt_distance(distance)
            if repeat > 1:
                dose = f"{repeat} × {dose}"
            description = (step.get("text") or block.get("name") or "Simning").strip()
            if "equipment" in step:
                description += f" · {fmt_equipment(step.get('equipment'))}"
            rows.append(
                '<div class="swim-set-row">'
                f'<span class="swim-dose">{html.escape(dose)}</span>'
                f'<span>{html.escape(description + rest_text)}</span>'
                '</div>'
            )

    if not rows:
        return ""

    label = "Genomfört simpass · passupplägg" if completed else "Passupplägg"
    note = (
        '<div class="workout-history-note">Setvila mellan huvudblock: LAP-styrd.</div>'
        if has_lap_rest else ""
    )
    equipment_html = (
        '<div class="workout-equipment">'
        f'<div><strong>Planerade hjälpmedel:</strong> {html.escape(planned_equipment)}</div>'
        + (
            f'<div><strong>Faktiskt använda:</strong> {html.escape(actual_equipment)}</div>'
            if completed else ""
        )
        + '</div>'
    )
    workout_id = workout.get("id") or workout.get("external_id") or day.get("date", "")
    return (
        f'<div class="workout-history" data-workout-history="{html.escape(str(workout_id))}">'
        f'<div class="workout-history-label">{label}</div>'
        f'<div class="swim-session-head"><strong>{html.escape(title)}</strong></div>'
        f'{equipment_html}'
        f'<div class="swim-set-list">{"".join(rows)}</div>'
        f'{note}'
        '</div>'
    )


def main():
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    activities = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
    page = INDEX_FILE.read_text(encoding="utf-8")

    all_activities = activities.get("activities", [])
    completed_dates = {
        activity_date(activity)
        for activity in all_activities
        if activity_date(activity)
    }
    completed_swim_dates = matching_swim_dates(all_activities)

    structured_days = [
        day
        for day in plan.get("days", [])
        if (day.get("watch_workout") or {}).get("type") == "Swim"
    ]

    # Any newly planned structured swim must explicitly state equipment. Historical
    # workouts created before this rule may show "ej registrerat" instead of guessing.
    for day in structured_days:
        date = day.get("date", "")
        completed = date in completed_swim_dates
        workout = day.get("watch_workout") or {}
        if not completed and "equipment" not in workout:
            raise RuntimeError(
                f"Workout history: planerat strukturerat simpass {date} saknar equipment"
            )

    for day in structured_days:
        date = day.get("date", "")
        anchor = f'<div class="day" id="dag-{html.escape(date)}">'
        start = page.find(anchor)
        if start < 0:
            date_marker = f'<div class="date">{html.escape(date)}</div>'
            date_pos = page.find(date_marker)
            if date_pos < 0:
                raise RuntimeError(f"Workout history: dagkort saknas för {date}")
            start = page.rfind('<div class="day">', 0, date_pos)
            if start < 0:
                raise RuntimeError(f"Workout history: kunde inte avgränsa dagkort för {date}")

        next_anchor = page.find('<div class="day"', start + 1)
        end = next_anchor if next_anchor >= 0 else page.find('<h2 class="section">', start + 1)
        if end < 0:
            end = len(page)
        segment = page[start:end]

        workout = day.get("watch_workout") or {}
        workout_id = str(workout.get("id") or workout.get("external_id") or date)
        marker = f'data-workout-history="{html.escape(workout_id)}"'
        if marker in segment:
            # Replace an older history block so equipment changes are reflected.
            block_start = segment.find('<div class="workout-history"', 0)
            if block_start >= 0:
                block_end = segment.find('</div><div class="pass">', block_start)
                if block_end >= 0:
                    completed = date in completed_swim_dates
                    replacement = render_workout(day, completed=True) if completed else ""
                    segment = segment[:block_start] + replacement + segment[block_end + len('</div>'):]
                    page = page[:start] + segment + page[end:]
            continue

        completed = date in completed_swim_dates
        if not completed:
            continue

        block = render_workout(day, completed=True)
        if not block:
            raise RuntimeError(f"Workout history: tom workout-struktur för {date}")

        insert_at = segment.find('<div class="pass">')
        if insert_at < 0:
            insert_at = segment.find('<div class="coach')
        if insert_at < 0:
            raise RuntimeError(f"Workout history: ingen säker infogningspunkt för {date}")

        segment = segment[:insert_at] + block + segment[insert_at:]
        page = page[:start] + segment + page[end:]

    # Remove v1 CSS if present; v2 supersedes it.
    page = page.replace("/* workout-history-v1 */", "/* workout-history-v1-old */")
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Workout history: kunde inte hitta </style>")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    INDEX_FILE.write_text(page, encoding="utf-8")

    rendered = INDEX_FILE.read_text(encoding="utf-8")
    required = [CSS_MARKER]
    for day in structured_days:
        date = day.get("date", "")
        if date in completed_swim_dates:
            workout = day.get("watch_workout") or {}
            workout_id = str(workout.get("id") or workout.get("external_id") or date)
            required.append(f'data-workout-history="{html.escape(workout_id)}"')
            required.append("Planerade hjälpmedel:")
            required.append("Faktiskt använda:")

    missing = [snippet for snippet in required if snippet not in rendered]
    if missing:
        raise RuntimeError("Workout history-validering misslyckades: " + repr(missing))

    print(
        "Workout history OK: strukturerade simpass visar passupplägg och hjälpmedel."
    )


if __name__ == "__main__":
    main()
