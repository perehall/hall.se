#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
INDEX_FILE = ROOT / "index.html"
CSS_MARKER = "/* workout-history-v3 */"

CSS = r'''
/* workout-history-v3 */
.workout-history{margin:13px 0 4px;padding:12px 13px;border:1px solid #bfdbfe;background:#f8fbff;border-radius:14px}.workout-history-label{margin-bottom:7px;color:#1d4ed8;font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em}.workout-history .swim-set-list{margin-top:9px}.workout-history-note{margin-top:8px;color:#64748b;font-size:.78rem}.workout-equipment{display:grid;gap:2px;margin-top:7px;color:#475569;font-size:.8rem}.workout-equipment strong{color:#334155}
'''.strip()


def activity_date(activity):
    value = activity.get("start_date_local") or ""
    return value[:10] if len(value) >= 10 else ""


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


def day_segment(page, date):
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
    return start, end, page[start:end]


def remove_marked_div(segment, marker):
    marker_pos = segment.find(marker)
    if marker_pos < 0:
        return segment, False
    block_start = segment.rfind('<div class="workout-history"', 0, marker_pos + 1)
    if block_start < 0:
        raise RuntimeError("Workout history: marker hittades utan workout-history-container")

    depth = 0
    block_end = None
    for match in re.finditer(r"</?div\b[^>]*>", segment[block_start:], flags=re.IGNORECASE):
        token = match.group(0).lower()
        if token.startswith("</div"):
            depth -= 1
            if depth == 0:
                block_end = block_start + match.end()
                break
        else:
            depth += 1
    if block_end is None:
        raise RuntimeError("Workout history: kunde inte hitta slutet på duplicerat passblock")
    return segment[:block_start] + segment[block_end:], True


def main():
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    activities = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
    page = INDEX_FILE.read_text(encoding="utf-8")

    all_activities = activities.get("activities", [])
    completed_swim_dates = matching_swim_dates(all_activities)
    structured_days = [
        day
        for day in plan.get("days", [])
        if (day.get("watch_workout") or {}).get("type") == "Swim"
    ]

    # Planned structured swims must still be complete enough for the primary
    # day-card renderer. A completed pass must never get a second copy of that
    # prescription below the original plan.
    for day in structured_days:
        date = day.get("date", "")
        completed = date in completed_swim_dates
        workout = day.get("watch_workout") or {}
        if not completed and "equipment" not in workout:
            raise RuntimeError(
                f"Workout history: planerat strukturerat simpass {date} saknar equipment"
            )

    removed = 0
    for day in structured_days:
        date = day.get("date", "")
        if date not in completed_swim_dates:
            continue
        workout = day.get("watch_workout") or {}
        workout_id = str(workout.get("id") or workout.get("external_id") or date)
        marker = f'data-workout-history="{html.escape(workout_id)}"'

        start, end, segment = day_segment(page, date)
        segment, changed = remove_marked_div(segment, marker)
        if changed:
            removed += 1
            page = page[:start] + segment + page[end:]

    # v3 supersedes the old behaviour where completed swim prescriptions were
    # copied into a second visible block.
    page = page.replace("/* workout-history-v1 */", "/* workout-history-v1-old */")
    page = page.replace("/* workout-history-v2 */", "/* workout-history-v2-old */")
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Workout history: kunde inte hitta </style>")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    INDEX_FILE.write_text(page, encoding="utf-8")

    rendered = INDEX_FILE.read_text(encoding="utf-8")
    missing = []
    for day in structured_days:
        date = day.get("date", "")
        if date not in completed_swim_dates:
            continue
        workout = day.get("watch_workout") or {}
        workout_id = str(workout.get("id") or workout.get("external_id") or date)
        marker = f'data-workout-history="{html.escape(workout_id)}"'
        if marker in rendered:
            missing.append(f"duplicerat passblock kvar för {date}")
    if missing:
        raise RuntimeError("Workout history-validering misslyckades: " + repr(missing))

    print(
        f"Workout history v3 OK: genomförda simpass dupliceras inte (borttagna block={removed})."
    )


if __name__ == "__main__":
    main()
