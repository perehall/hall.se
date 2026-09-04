#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities.json"

STATUS_TEXT_REPLACEMENTS = {
    "PLANERAT": "AKTUELL PLAN",
    "PRELIMINÄRT": "KAN ÄNDRAS",
    "VILLKORAT": "KAN ÄNDRAS",
    "ÖPPET": "INTE BESTÄMT",
    "Planerat": "Aktuell plan",
    "Preliminärt": "Kan ändras",
    "Villkorat": "Kan ändras",
    "Öppet": "Inte bestämt",
}

FORBIDDEN_VISIBLE_TERMS = (
    (re.compile(r"\blapparna\b", re.IGNORECASE), "intervallerna"),
    (re.compile(r"\blappar\b", re.IGNORECASE), "intervaller"),
    (re.compile(r"\blaps\b", re.IGNORECASE), "intervaller"),
)

STRUCTURE_RE = re.compile(
    r"(?P<sets>\d+)\s*[×xX]\s*(?P<reps>\d+)\s*(?P<kind>backintervaller|backar|intervaller)\b",
    re.IGNORECASE,
)

OLD_LEGEND = (
    '<div class="dashboard-legend">✓ genomfört · ● planerat · '
    '◐ preliminärt/villkorat · · öppet</div>'
)
NEW_LEGEND = (
    '<div class="dashboard-legend">✓ genomfört · ● aktuell plan · '
    '◐ kan ändras · · inte bestämt<br>'
    '<small>Aktuell plan = passet du utgår från. Kan ändras = samma konkreta pass gäller, '
    'men coachen får justera det om ny information ger sakliga skäl.</small></div>'
)


def load(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def visible_training_language(text):
    value = str(text or "")
    for pattern, replacement in FORBIDDEN_VISIBLE_TERMS:
        value = pattern.sub(replacement, value)
    return value


def explicit_interval_structure(user_report):
    report = str(user_report or "").strip()
    match = STRUCTURE_RE.search(report)
    if not match:
        return None
    sets = int(match.group("sets"))
    reps = int(match.group("reps"))
    label = "backintervaller" if match.group("kind").lower().startswith("back") else "intervaller"
    return f"{sets} × {reps} {label} ({sets * reps} totalt)"


def latest_structured_report(activities_state):
    activities = activities_state.get("activities") or []
    ordered = sorted(
        activities,
        key=lambda item: item.get("start_date_local") or item.get("start_date") or "",
        reverse=True,
    )
    for activity in ordered:
        structure = explicit_interval_structure(activity.get("user_report"))
        if structure:
            return structure
    return None


def replace_exact_element_text(page, old, new):
    return page.replace(f">{old}<", f">{new}<")


def humanize_statuses(page):
    page = page.replace(OLD_LEGEND, NEW_LEGEND)
    for old, new in STATUS_TEXT_REPLACEMENTS.items():
        page = replace_exact_element_text(page, old, new)
    return page


def humanize_post_workout_details(page, reported_structure=None):
    page = page.replace(
        '<span class="today-outcome-label">Plan</span>',
        '<span class="today-outcome-label">Plan före passet</span>',
    )
    page = page.replace(
        '<span class="today-outcome-label">Utfall</span>',
        '<span class="today-outcome-label">Genomfört</span>',
    )
    if not reported_structure or 'data-post-workout-state="completed"' not in page:
        return page

    pattern = re.compile(
        r'(<div><span class="today-outcome-label">Genomfört</span><strong>)(.*?)(</strong></div>)',
        re.S,
    )
    replacement = r"\1" + html.escape(reported_structure) + r"\3"
    return pattern.sub(replacement, page, count=1)


def humanize_page(page, reported_structure=None):
    page = humanize_statuses(page)
    page = humanize_post_workout_details(page, reported_structure=reported_structure)
    page = visible_training_language(page)
    return page


def html_targets():
    targets = [ROOT / "index.html"]
    archive_root = ROOT / "vecka"
    if archive_root.exists():
        targets.extend(sorted(archive_root.glob("*/index.html")))
    return [path for path in targets if path.exists()]


def main():
    activities = load(ACTIVITIES_FILE, {"activities": []})
    current_structure = latest_structured_report(activities)
    changed = 0
    for path in html_targets():
        page = path.read_text(encoding="utf-8")
        structure = current_structure if path == ROOT / "index.html" else None
        rendered = humanize_page(page, reported_structure=structure)
        if rendered != page:
            path.write_text(rendered, encoding="utf-8")
            changed += 1
    print(f"Mänskligt träningsspråk OK: {changed} sida/sidor uppdaterade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
