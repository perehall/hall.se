#!/usr/bin/env python3
"""Second Quiet Performance pass: reduce visual chrome and sharpen hierarchy.

V1 established palette and component styling. V2 changes presentation hierarchy
without changing training semantics: Today's decision comes first, duplicate
upcoming-summary UI disappears from the current page, and secondary overview /
historical surfaces become progressively quieter.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
WEEK_DIR = ROOT / "vecka"
GOAL_PAGE = ROOT / "malbild" / "index.html"
GOAL_PUBLIC_PAGE = ROOT / "malbild-2027" / "index.html"

CSS_START = "/* quiet-performance-v2:start */"
CSS_END = "/* quiet-performance-v2:end */"
CSS_BLOCK_RE = re.compile(re.escape(CSS_START) + r".*?" + re.escape(CSS_END), re.S)
DIV_TAG_RE = re.compile(r"<div\b[^>]*>|</div>", re.I)
BODY_RE = re.compile(r"<body(?P<attrs>[^>]*)>", re.I)
CLASS_RE = re.compile(r'\sclass="(?P<classes>[^"]*)"', re.I)
TRAINING_START = "<!-- training-brain-v1:start -->"
TRAINING_END = "<!-- training-brain-v1:end -->"
UPCOMING_TITLE = '<div class="dashboard-title">Kommande dagar</div>'

CSS = r'''
/* Current page has one strong operational surface; everything else recedes. */
body.quiet-performance.qp-current .wrap{max-width:700px!important}
body.quiet-performance.qp-current header{padding-bottom:14px}
body.quiet-performance.qp-current .training-brain{margin:2px 0 22px}
body.quiet-performance.qp-current .brain-today{
  padding:18px 18px 16px;
  background:#FFFFFF;
  border-color:#DEE1DD;
  border-radius:12px;
  box-shadow:inset 2px 0 0 var(--qp-accent);
}
body.quiet-performance.qp-current .brain-topline{margin-bottom:10px}
body.quiet-performance.qp-current .brain-kicker{
  color:var(--qp-tertiary);
  font-size:.69rem;
  font-weight:650;
  letter-spacing:.075em;
  text-transform:uppercase;
}
body.quiet-performance.qp-current .brain-headline{font-size:1.22rem;font-weight:650}
body.quiet-performance.qp-current .brain-subline{margin-top:4px;font-size:.82rem}
body.quiet-performance.qp-current .brain-next{
  display:grid;
  grid-template-columns:88px minmax(0,1fr);
  column-gap:12px;
  row-gap:2px;
  margin-top:15px;
  padding-top:12px;
}
body.quiet-performance.qp-current .brain-next-label{
  grid-row:1 / span 2;
  align-self:start;
  margin:2px 0 0;
  font-size:.67rem;
  letter-spacing:.06em;
  text-transform:uppercase;
}
body.quiet-performance.qp-current .brain-next strong{font-size:.91rem;font-weight:600}
body.quiet-performance.qp-current .brain-note{margin:0;font-size:.76rem;color:var(--qp-tertiary)}
body.quiet-performance.qp-current .brain-why-details>summary{color:var(--qp-tertiary);font-size:.73rem}

/* Strategy follows execution, as a quiet editorial note. */
body.quiet-performance.qp-current .hero.week-focus-card{
  margin:0 0 24px;
  padding:0 0 0 13px;
  border-left-width:1px;
}
body.quiet-performance.qp-current .week-focus-title{font-size:.98rem;font-weight:600}
body.quiet-performance.qp-current .week-focus-mesocycle-meta{font-size:.69rem}
body.quiet-performance.qp-current .week-focus-details>summary{font-size:.71rem}

/* The overview is now a signal strip, not five more cards. */
body.quiet-performance.qp-current .dashboard{
  gap:0;
  margin:0 0 27px;
  padding:13px 0 15px;
  border-top:1px solid var(--qp-line);
  border-bottom:1px solid var(--qp-line);
}
body.quiet-performance.qp-current .metrics{
  display:flex;
  gap:0;
  align-items:baseline;
  margin:0;
}
body.quiet-performance.qp-current .metric{
  display:flex;
  align-items:baseline;
  gap:5px;
  min-width:0;
  padding:0 14px;
  border:0;
  border-left:1px solid var(--qp-line-soft);
  border-radius:0;
  background:transparent;
}
body.quiet-performance.qp-current .metric:first-child{padding-left:0;border-left:0}
body.quiet-performance.qp-current .metric strong{display:inline;font-size:.94rem;font-weight:650}
body.quiet-performance.qp-current .metric span{display:inline;margin:0;font-size:.7rem;white-space:nowrap}
body.quiet-performance.qp-current .dashboard-grid{
  display:grid;
  grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  gap:22px;
  margin-top:13px;
}
body.quiet-performance.qp-current .dashboard-card{
  padding:0;
  border:0;
  border-radius:0;
  background:transparent;
}
body.quiet-performance.qp-current .dashboard-title{margin-bottom:8px;font-size:.64rem}
body.quiet-performance.qp-current .sport-row+.sport-row{margin-top:7px}
body.quiet-performance.qp-current .sport-head{font-size:.76rem}
body.quiet-performance.qp-current .sport-head strong{font-size:.72rem}
body.quiet-performance.qp-current .sport-track{height:3px;margin-top:3px}
body.quiet-performance.qp-current .week-day{padding:2px 1px}
body.quiet-performance.qp-current .week-day.today{background:transparent}
body.quiet-performance.qp-current .week-day-label{font-size:.61rem}
body.quiet-performance.qp-current .week-day-dot{width:23px;height:23px;font-size:.68rem}
body.quiet-performance.qp-current .dashboard-legend{margin-top:7px;font-size:.64rem;line-height:1.38}
body.quiet-performance.qp-current .dashboard-legend small{color:var(--qp-tertiary)}

/* Day list is a hierarchy: actionable cards > contextual rows. */
body.quiet-performance.qp-current .section{margin:27px 0 9px;font-size:1.03rem}
body.quiet-performance.qp-current .day.workout-card-v2{margin:9px 0}
body.quiet-performance.qp-current .day.workout-card-v2.past-completed,
body.quiet-performance.qp-current .day.workout-card-v2.future-compact{
  margin:0;
  padding:11px 2px;
  border:0;
  border-top:1px solid var(--qp-line-soft);
  border-radius:0;
  background:transparent;
}
body.quiet-performance.qp-current .day.workout-card-v2.past-completed:first-of-type,
body.quiet-performance.qp-current .day.workout-card-v2.future-compact:first-of-type{border-top-color:transparent}
body.quiet-performance.qp-current .past-completed .session,
body.quiet-performance.qp-current .future-compact .session{font-size:.96rem}
body.quiet-performance.qp-current .past-completed .dow,
body.quiet-performance.qp-current .future-compact .dow{font-size:.72rem}
body.quiet-performance.qp-current .past-completed .date,
body.quiet-performance.qp-current .future-compact .date{font-size:.74rem}

/* Quiet statuses: background colour is reserved for a state that needs attention. */
body.quiet-performance.qp-current .badge.planned,
body.quiet-performance.qp-current .badge.open{
  padding-left:0;
  padding-right:0;
  background:transparent;
  color:var(--qp-tertiary);
}
body.quiet-performance.qp-current .badge.fixed{background:var(--qp-green-soft);color:var(--qp-green)}
body.quiet-performance.qp-current .badge.conditional{background:var(--qp-amber-soft);color:var(--qp-amber)}

/* Secondary coach/history surfaces should read like annotations, not cards. */
body.quiet-performance.qp-current .coach,
body.quiet-performance.qp-current .coach.yoda-v2,
body.quiet-performance.qp-current .week-activity-insight{
  border-left:1px solid var(--qp-line);
  border-right:0;
  border-top:0;
  border-bottom:0;
  border-radius:0;
  background:transparent;
  padding-left:12px;
}

/* Historical pages use the same progressive-disclosure principle. */
body.quiet-performance.qp-history .metric,
body.quiet-performance.qp-history .dashboard-card{box-shadow:none}
body.quiet-performance.qp-history .day.workout-card-v2.past-completed{
  box-shadow:none;
  background:transparent;
}

@media(max-width:620px){
  body.quiet-performance.qp-current .brain-today{padding:16px 15px 14px}
  body.quiet-performance.qp-current .brain-next{grid-template-columns:72px minmax(0,1fr);column-gap:9px}
  body.quiet-performance.qp-current .metrics{justify-content:space-between}
  body.quiet-performance.qp-current .metric{padding:0 9px;gap:4px}
  body.quiet-performance.qp-current .metric strong{font-size:.88rem}
  body.quiet-performance.qp-current .metric span{font-size:.64rem}
  body.quiet-performance.qp-current .dashboard-grid{grid-template-columns:1fr;gap:13px}
  body.quiet-performance.qp-current .dashboard-grid .dashboard-card:first-child{display:none}
  body.quiet-performance.qp-current .dashboard{padding:11px 0 13px}
}
'''.strip()


def balanced_div_end(text: str, start: int) -> int:
    depth = 0
    for match in DIV_TAG_RE.finditer(text, start):
        token = match.group(0).lower()
        if token.startswith("</div"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    raise RuntimeError("Quiet Performance v2: obalanserad div-struktur")


def add_body_class(page: str, class_name: str) -> str:
    match = BODY_RE.search(page)
    if not match:
        raise RuntimeError("Quiet Performance v2: body-taggen saknas")
    attrs = match.group("attrs") or ""
    class_match = CLASS_RE.search(attrs)
    if class_match:
        classes = [value for value in class_match.group("classes").split() if value]
        if class_name not in classes:
            classes.append(class_name)
        replacement = ' class="' + " ".join(classes) + '"'
        attrs = attrs[: class_match.start()] + replacement + attrs[class_match.end() :]
    else:
        attrs += f' class="{class_name}"'
    return page[: match.start()] + f"<body{attrs}>" + page[match.end() :]


def move_today_before_week_focus(page: str) -> str:
    brain_start = page.find(TRAINING_START)
    brain_end = page.find(TRAINING_END, brain_start + len(TRAINING_START)) if brain_start >= 0 else -1
    focus_marker = '<div class="hero week-focus-card">'
    focus_start = page.find(focus_marker)
    if brain_start < 0 or brain_end < 0 or focus_start < 0:
        return page
    brain_end += len(TRAINING_END)
    if brain_start < focus_start:
        return page

    section = page[brain_start:brain_end]
    without = page[:brain_start] + page[brain_end:]
    focus_start = without.find(focus_marker)
    if focus_start < 0:
        raise RuntimeError("Quiet Performance v2: veckofokus försvann vid omordning")
    return without[:focus_start] + section + "\n" + without[focus_start:]


def remove_duplicate_upcoming_card(page: str) -> str:
    title_pos = page.find(UPCOMING_TITLE)
    if title_pos < 0:
        return page
    card_start = page.rfind('<div class="dashboard-card">', 0, title_pos)
    if card_start < 0:
        raise RuntimeError("Quiet Performance v2: Kommande dagar saknar dashboard-card")
    card_end = balanced_div_end(page, card_start)
    return page[:card_start] + page[card_end:]


def add_css(page: str) -> str:
    block = f"{CSS_START}\n{CSS}\n{CSS_END}"
    has_start = CSS_START in page
    has_end = CSS_END in page
    if has_start != has_end:
        raise RuntimeError("Quiet Performance v2: ofullständigt CSS-block")
    if has_start:
        match = CSS_BLOCK_RE.search(page)
        if not match:
            raise RuntimeError("Quiet Performance v2: befintligt CSS-block kunde inte avgränsas")
        return page[: match.start()] + block + page[match.end() :]
    if "</style>" not in page:
        raise RuntimeError("Quiet Performance v2: </style> saknas")
    return page.replace("</style>", block + "\n</style>", 1)


def apply_v2(page: str, *, current: bool) -> str:
    if "quiet-performance" not in page:
        raise RuntimeError("Quiet Performance v2: v1 måste appliceras först")
    page = add_body_class(page, "qp-current" if current else "qp-history")
    if current:
        page = move_today_before_week_focus(page)
        page = remove_duplicate_upcoming_card(page)
    return add_css(page)


def validate_page(page: str, *, current: bool, label: str) -> None:
    required = [CSS_START, CSS_END, "quiet-performance"]
    required.append("qp-current" if current else "qp-history")
    missing = [marker for marker in required if marker not in page]
    if missing:
        raise RuntimeError(f"Quiet Performance v2: {label} saknar {missing!r}")
    if page.count(CSS_START) != 1 or page.count(CSS_END) != 1:
        raise RuntimeError(f"Quiet Performance v2: {label} har duplicerat CSS-block")
    if current:
        if UPCOMING_TITLE in page:
            raise RuntimeError("Quiet Performance v2: duplicerad Kommande dagar-ruta finns kvar")
        brain = page.find(TRAINING_START)
        focus = page.find('<div class="hero week-focus-card">')
        if brain >= 0 and focus >= 0 and brain > focus:
            raise RuntimeError("Quiet Performance v2: Idag ligger fortfarande efter veckofokus")


def page_paths() -> list[tuple[Path, bool]]:
    paths: list[tuple[Path, bool]] = []
    if INDEX_FILE.exists():
        paths.append((INDEX_FILE, True))
    if WEEK_DIR.exists():
        paths.extend((path, False) for path in sorted(WEEK_DIR.glob("*/index.html")))
    for path in (GOAL_PAGE, GOAL_PUBLIC_PAGE):
        if path.exists():
            paths.append((path, False))
    return paths


def main() -> int:
    paths = page_paths()
    if not paths:
        raise RuntimeError("Quiet Performance v2: inga träningssidor hittades")
    for path, current in paths:
        rendered = apply_v2(path.read_text(encoding="utf-8"), current=current)
        validate_page(rendered, current=current, label=str(path.relative_to(ROOT)))
        path.write_text(rendered, encoding="utf-8")
    print(f"Quiet Performance v2 OK: hierarki och visuell densitet uppdaterade på {len(paths)} sidor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
