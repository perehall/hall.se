#!/usr/bin/env python3
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
CURRENT_INDEX = ROOT / "index.html"
PAGES_DIR = ROOT / "vecka"

CSS_MARKER = "/* workout-prescription-v1 */"
CSS = r'''
/* workout-prescription-v1 */
.development-focus{margin-top:11px;padding:10px 12px;border:1px solid #c7d2fe;border-radius:12px;background:#f8faff;display:grid;gap:3px}.development-focus strong{color:#4338ca;font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.07em}.development-focus span{color:#312e81;font-size:.88rem;line-height:1.42}
.workout-prescription{margin:10px 0 4px;padding:10px 12px;border:1px solid #dbe4f0;border-radius:12px;background:#fff;display:grid;gap:0}.workout-prescription-head{font-size:.72rem;font-weight:800;color:#475569;margin-bottom:3px}.workout-prescription-row{display:grid;grid-template-columns:minmax(72px,auto) 1fr;gap:10px;padding:7px 0;border-top:1px solid #eef2f7;align-items:start}.workout-prescription-row:first-of-type{border-top:0}.workout-prescription-dose{font-weight:800;color:#0f172a;white-space:nowrap}.workout-prescription-text{color:#334155;line-height:1.38}.workout-prescription-recovery{color:#64748b}.future-compact .workout-prescription,.past-completed .workout-prescription,.today-completed .workout-prescription{display:none}
@media (max-width:520px){.workout-prescription-row{grid-template-columns:68px 1fr;gap:8px}.workout-prescription{padding:9px 10px}}
/* workout-prescription-v1 */
'''.strip()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_css(page):
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Progressions-UI: sidan saknar </style>")
    return page.replace("</style>", CSS + "\n</style>", 1)


def card_bounds(page, date):
    marker = f'<div class="day" id="dag-{html.escape(date)}">'
    start = page.find(marker)
    if start < 0:
        raise RuntimeError(f"Progressions-UI: dagkort saknas för {date}")
    next_start = page.find('<div class="day" id="dag-', start + len(marker))
    if next_start < 0:
        section_end = page.find('<h2 class="section">', start + len(marker))
        footer = page.find("<footer", start + len(marker))
        candidates = [value for value in (section_end, footer) if value >= 0]
        next_start = min(candidates) if candidates else len(page)
    return start, next_start


def selected_candidate(day):
    design = day.get("workout_design") or {}
    selected_id = str(design.get("selected_candidate_id") or "").strip()
    return next(
        (
            item
            for item in (design.get("candidates") or [])
            if str(item.get("id") or "").strip() == selected_id
        ),
        {},
    )


def _duration(seconds):
    seconds = int(seconds or 0)
    if seconds <= 0:
        return ""
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds} s"


def _work_dose(work):
    work = work or {}
    sets = work.get("sets")
    per_set = work.get("repetitions_per_set")
    reps = work.get("repetitions")
    distance = work.get("distance_m")
    duration = work.get("duration_s")

    if sets and per_set and distance:
        return f"{int(sets)}×{int(per_set)}×{int(distance)} m"
    if reps and distance:
        if int(reps) == 1:
            return f"{int(distance)} m"
        return f"{int(reps)}×{int(distance)} m"
    if reps and duration:
        return f"{int(reps)}×{_duration(duration)}"
    if distance:
        return f"{int(distance)} m"
    if duration:
        return _duration(duration)
    return ""


def _recovery_text(recovery):
    recovery = recovery or {}
    parts = []
    duration = _duration(recovery.get("duration_s"))
    instruction = str(recovery.get("instruction") or "").strip()
    if duration:
        parts.append(f"vila {duration}")
    if instruction:
        parts.append(instruction)
    return " · ".join(parts)


def prescription_html(day):
    candidate = selected_candidate(day)
    prescription = candidate.get("prescription") or {}
    if prescription.get("completeness") == "external":
        return ""
    blocks = prescription.get("blocks") or []
    if not blocks:
        return ""

    rows = []
    for block in blocks:
        dose = _work_dose(block.get("work"))
        instruction = str(block.get("instruction") or block.get("name") or "").strip()
        recovery = _recovery_text(block.get("recovery"))
        if recovery:
            instruction = (
                f"{instruction} · {recovery}"
                if instruction
                else recovery
            )
        if not dose and not instruction:
            continue
        rows.append(
            '<div class="workout-prescription-row">'
            f'<span class="workout-prescription-dose">{html.escape(dose or "—")}</span>'
            f'<span class="workout-prescription-text">{html.escape(instruction)}</span>'
            '</div>'
        )
    if not rows:
        return ""
    return (
        '<div class="workout-prescription">'
        '<div class="workout-prescription-head">Passupplägg</div>'
        + "".join(rows)
        + "</div>"
    )


def inject_prescription(page, day):
    block = prescription_html(day)
    if not block:
        return page

    start, end = card_bounds(page, day["date"])
    segment = page[start:end]
    if 'class="workout-prescription"' in segment:
        return page

    reason_marker = '<div class="reason">'
    position = segment.find(reason_marker)
    if position < 0:
        closing = segment.rfind("</div>")
        if closing < 0:
            raise RuntimeError(f"Progressions-UI: kunde inte placera passupplägg {day['date']}")
        position = closing
    segment = segment[:position] + block + segment[position:]
    return page[:start] + segment + page[end:]


def inject_focus(page, day):
    sport = day.get("sport")
    if sport in {"open", "rest"}:
        return page
    focus = str(day.get("development_focus") or "").strip()
    if not focus:
        raise RuntimeError(
            f"Progressions-UI: {day.get('date')} {sport} saknar development_focus"
        )
    start, end = card_bounds(page, day["date"])
    segment = page[start:end]
    if 'class="development-focus"' in segment:
        return page
    closing = segment.rfind("</div>")
    if closing < 0:
        raise RuntimeError(f"Progressions-UI: kunde inte avsluta dagkort {day['date']}")
    block = (
        '<div class="development-focus"><strong>Utvecklingsfokus</strong>'
        f'<span>{html.escape(focus)}</span></div>'
    )
    segment = segment[:closing] + block + segment[closing:]
    return page[:start] + segment + page[end:]


def validate_page(page, document):
    for day in document.get("days", []):
        sport = day.get("sport")
        if sport in {"open", "rest"}:
            continue
        start, end = card_bounds(page, day["date"])
        segment = page[start:end]
        if 'class="development-focus"' not in segment:
            raise RuntimeError(
                f"Progressions-UI: utvecklingsfokus renderades inte för {day['date']}"
            )

        candidate = selected_candidate(day)
        prescription = candidate.get("prescription") or {}
        should_render = bool(prescription.get("blocks")) and prescription.get("completeness") != "external"
        if should_render and 'class="workout-prescription"' not in segment:
            raise RuntimeError(
                f"Progressions-UI: passupplägg renderades inte för {day['date']}"
            )


def patch_page(path, document):
    page = add_css(path.read_text(encoding="utf-8"))
    for day in document.get("days", []):
        page = inject_prescription(page, day)
        page = inject_focus(page, day)
    validate_page(page, document)
    path.write_text(page, encoding="utf-8")


def main():
    plan = load_json(PLAN_FILE)
    upcoming = load_json(UPCOMING_FILE)
    patch_page(CURRENT_INDEX, plan)

    upcoming_key = str(upcoming.get("week_key") or "").strip()
    if not upcoming_key:
        raise RuntimeError("Progressions-UI: upcoming_week.week_key saknas")
    upcoming_page = PAGES_DIR / upcoming_key / "index.html"
    if not upcoming_page.exists():
        raise RuntimeError(f"Progressions-UI: framtidssida saknas: {upcoming_key}")
    patch_page(upcoming_page, upcoming)

    current_recipes = sum(
        1
        for day in plan.get("days", [])
        if prescription_html(day)
    )
    preview_recipes = sum(
        1
        for day in upcoming.get("days", [])
        if prescription_html(day)
    )
    print(
        f"Progressions-UI OK: {current_recipes} aktuella och "
        f"{preview_recipes} kommande pass med synligt passupplägg."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
