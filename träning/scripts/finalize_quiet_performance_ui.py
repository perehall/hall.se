#!/usr/bin/env python3
"""Apply the final Quiet Performance visual system to all training surfaces.

This is deliberately the last presentation-layer pass. Earlier renderers own
information architecture and component semantics; this module owns only the
shared visual language so the design survives every deterministic rebuild.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
WEEK_DIR = ROOT / "vecka"
GOAL_PAGE = ROOT / "malbild" / "index.html"
GOAL_PUBLIC_PAGE = ROOT / "malbild-2027" / "index.html"

THEME_COLOR = "#F6F7F5"
CSS_START = "/* quiet-performance-v1:start */"
CSS_END = "/* quiet-performance-v1:end */"
CSS_BLOCK_RE = re.compile(re.escape(CSS_START) + r".*?" + re.escape(CSS_END), re.S)
THEME_RE = re.compile(
    r'<meta\s+name=["\']theme-color["\']\s+content=["\'][^"\']*["\']\s*/?>',
    re.I,
)
BODY_RE = re.compile(r"<body(?P<attrs>[^>]*)>", re.I)
CLASS_RE = re.compile(r'\sclass="(?P<classes>[^"]*)"', re.I)

CSS = r'''
:root{
  --qp-canvas:#F6F7F5;
  --qp-surface:#FCFCFB;
  --qp-elevated:#FFFFFF;
  --qp-text:#171918;
  --qp-secondary:#6C716D;
  --qp-tertiary:#979C98;
  --qp-line:#E4E7E3;
  --qp-line-soft:#ECEEEB;
  --qp-accent:#5964E8;
  --qp-accent-soft:#F1F2FD;
  --qp-green:#287A54;
  --qp-green-soft:#EDF7F1;
  --qp-amber:#946200;
  --qp-amber-soft:#FFF6DD;
  --qp-red:#B54747;
  --qp-red-soft:#FFF1F0;
  --bg:var(--qp-canvas);
  --card:var(--qp-surface);
  --text:var(--qp-text);
  --muted:var(--qp-secondary);
  --line:var(--qp-line);
  --accent:var(--qp-accent);
  --green:var(--qp-green);
  --green-soft:var(--qp-green-soft);
  --amber:var(--qp-amber);
  --amber-soft:var(--qp-amber-soft);
  --purple:var(--qp-accent);
  --purple-soft:var(--qp-accent-soft);
  --shadow:none;
  color-scheme:light;
}
body.quiet-performance{
  background:var(--qp-canvas);
  color:var(--qp-text);
  font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
  letter-spacing:-.005em;
}
body.quiet-performance ::selection{background:var(--qp-accent-soft)}
body.quiet-performance :focus-visible{outline:2px solid var(--qp-accent);outline-offset:2px}
body.quiet-performance .wrap{padding-top:24px;padding-bottom:64px}
body.quiet-performance header{padding-bottom:20px}
body.quiet-performance .eyebrow{color:var(--qp-tertiary);font-weight:650;letter-spacing:.09em}
body.quiet-performance h1{font-size:clamp(1.9rem,7vw,2.75rem);font-weight:650;letter-spacing:-.045em}
body.quiet-performance .sub,
body.quiet-performance .header-meta-line,
body.quiet-performance .header-updated,
body.quiet-performance .header-status{color:var(--qp-tertiary)}
body.quiet-performance .week-period{color:var(--qp-secondary)}
body.quiet-performance .section{font-size:1.12rem;font-weight:650;letter-spacing:-.018em;margin-top:30px}

/* Editorial week focus: important, but not another floating card. */
body.quiet-performance .hero,
body.quiet-performance .hero.week-focus-card{
  margin:8px 0 22px;
  padding:3px 0 3px 15px;
  border:0;
  border-left:2px solid var(--qp-accent);
  border-radius:0;
  background:transparent;
  color:var(--qp-text);
  box-shadow:none;
}
body.quiet-performance .hero h2,
body.quiet-performance .week-focus-title{color:var(--qp-text);font-weight:600}
body.quiet-performance .hero p,
body.quiet-performance .week-focus-details p{color:var(--qp-secondary)!important}
body.quiet-performance .week-focus-details>summary{color:var(--qp-tertiary)}

/* Overview surfaces use hairlines and spacing instead of elevation. */
body.quiet-performance .dashboard{gap:10px;margin-bottom:26px}
body.quiet-performance .metrics{gap:8px}
body.quiet-performance .metric,
body.quiet-performance .dashboard-card{
  background:var(--qp-surface);
  border:1px solid var(--qp-line);
  border-radius:13px;
  box-shadow:none;
}
body.quiet-performance .metric{padding:12px 13px}
body.quiet-performance .metric strong{font-size:1.12rem;font-weight:650;letter-spacing:-.02em}
body.quiet-performance .metric span,
body.quiet-performance .dashboard-empty{color:var(--qp-tertiary)}
body.quiet-performance .dashboard-title{
  color:var(--qp-tertiary);
  font-size:.7rem;
  font-weight:650;
  letter-spacing:.075em;
}
body.quiet-performance .sport-head{color:var(--qp-secondary)}
body.quiet-performance .sport-head strong{color:var(--qp-text);font-weight:600}
body.quiet-performance .sport-track{height:5px;background:var(--qp-line-soft)}
body.quiet-performance .sport-fill{background:var(--qp-accent)}
body.quiet-performance .week-day.today{background:var(--qp-accent-soft)}
body.quiet-performance .week-day-label,
body.quiet-performance .dashboard-legend{color:var(--qp-tertiary)}
body.quiet-performance .next-item+.next-item{border-color:var(--qp-line-soft)}
body.quiet-performance .next-item:hover{background:var(--qp-canvas)}
body.quiet-performance .next-coach{color:var(--qp-secondary)}

/* Today / next: one subtle accent, never a blue panel. */
body.quiet-performance .brain-today{
  background:#FAFAFE;
  border:1px solid var(--qp-line);
  border-radius:14px;
  box-shadow:inset 2px 0 0 var(--qp-accent);
  padding:16px 17px;
}
body.quiet-performance .brain-kicker{color:var(--qp-secondary);font-weight:600}
body.quiet-performance .brain-headline{color:var(--qp-text);font-size:1.14rem;font-weight:650;letter-spacing:-.018em}
body.quiet-performance .brain-subline{color:var(--qp-secondary)}
body.quiet-performance .brain-weather,
body.quiet-performance .brain-extra{
  margin-top:11px;
  padding:9px 0 0;
  border:0;
  border-top:1px solid var(--qp-line-soft);
  border-radius:0;
  background:transparent;
}
body.quiet-performance .brain-weather-label,
body.quiet-performance .brain-next-label{color:var(--qp-tertiary);font-weight:650}
body.quiet-performance .brain-weather-note{color:var(--qp-secondary)}
body.quiet-performance .brain-next{border-color:var(--qp-line-soft)}
body.quiet-performance .brain-status{font-weight:650;letter-spacing:.01em}

/* Workout cards: flat, precise and dose-led. */
body.quiet-performance .day,
body.quiet-performance .day.workout-card-v2{
  background:var(--qp-surface);
  border:1px solid var(--qp-line);
  border-radius:14px;
  box-shadow:none;
}
body.quiet-performance .day.workout-card-v2.card-v2-today{
  background:#FAFAFE;
  border-color:var(--qp-line);
  box-shadow:inset 2px 0 0 var(--qp-accent);
}
body.quiet-performance .day.workout-card-v2.past-completed,
body.quiet-performance .day.workout-card-v2.future-compact{box-shadow:none}
body.quiet-performance .dow{color:var(--qp-secondary);font-weight:650;letter-spacing:.065em}
body.quiet-performance .date,
body.quiet-performance .session-meta{color:var(--qp-tertiary)}
body.quiet-performance .session,
body.quiet-performance .session-title,
body.quiet-performance .session-with-icon{color:var(--qp-text);font-weight:650}
body.quiet-performance .reason{color:var(--qp-secondary)}
body.quiet-performance .workout-card-v2 .workout-prescription-dose{color:var(--qp-text);font-weight:650}
body.quiet-performance .workout-card-v2 .workout-prescription-text{color:var(--qp-secondary);border-left-color:var(--qp-line)}
body.quiet-performance .workout-card-v2 .development-focus{border-top-color:var(--qp-line-soft)}
body.quiet-performance .workout-card-v2 .development-focus strong{
  margin-top:2px;
  padding:0;
  border-radius:0;
  background:transparent;
  color:var(--qp-tertiary);
  font-size:.65rem;
  font-weight:650;
  letter-spacing:.055em;
  text-transform:uppercase;
}
body.quiet-performance .workout-card-v2 .development-focus span{color:var(--qp-secondary)}
body.quiet-performance .card-v2-footer{border-top-color:var(--qp-line-soft)}
body.quiet-performance .card-v2-footer .day-why>summary,
body.quiet-performance .card-v2-footer .device-sync-state{color:var(--qp-tertiary);font-weight:600}
body.quiet-performance .workout-history,
body.quiet-performance .swim-workout{
  border-color:var(--qp-line);
  background:var(--qp-canvas);
  border-radius:12px;
}
body.quiet-performance .swim-dose{color:var(--qp-text);font-weight:650}
body.quiet-performance .swim-meta,
body.quiet-performance .workout-history-note,
body.quiet-performance .workout-equipment{color:var(--qp-secondary)}

/* Only genuine state remains pill-shaped and coloured. */
body.quiet-performance .badge{font-weight:650;letter-spacing:.015em}
body.quiet-performance .fixed{background:var(--qp-green-soft);color:var(--qp-green)}
body.quiet-performance .planned{background:var(--qp-accent-soft);color:#454FC7}
body.quiet-performance .conditional,
body.quiet-performance .brain-status{background:var(--qp-amber-soft);color:var(--qp-amber)}
body.quiet-performance .open{background:var(--qp-line-soft);color:var(--qp-secondary)}
body.quiet-performance .device-sync-state.error{color:var(--qp-red)}

/* Icons identify function; they do not create a second colour system. */
body.quiet-performance .sport-icon,
body.quiet-performance .watch-sync .watch-icon,
body.quiet-performance .completed-session-with-icon .sport-icon{color:var(--qp-secondary)}
body.quiet-performance .manual-activity{border-color:var(--qp-line);background:transparent}
body.quiet-performance .manual-activity-class{color:var(--qp-tertiary)}

/* Coach content is information, not a purple sub-product. */
body.quiet-performance .coach,
body.quiet-performance .coach.yoda-v2{
  background:var(--qp-surface);
  border:1px solid var(--qp-line);
  border-radius:12px;
  box-shadow:none;
}
body.quiet-performance .coach-title,
body.quiet-performance .coach-decision>span:first-child,
body.quiet-performance .coach-target,
body.quiet-performance .coach-next-label,
body.quiet-performance .coach-full-summary strong,
body.quiet-performance .coach-reason strong{color:var(--qp-tertiary);font-weight:650}
body.quiet-performance .coach-decision strong{color:var(--qp-text);font-weight:650}
body.quiet-performance .yoda-v2 .coach-summary,
body.quiet-performance .coach-full-summary,
body.quiet-performance .coach-reason{color:var(--qp-secondary)}
body.quiet-performance .coach-next,
body.quiet-performance .coach-why,
body.quiet-performance .yoda-v2 .coach-details,
body.quiet-performance .yoda-v2 .coach-load{
  background:var(--qp-canvas);
  border-color:var(--qp-line);
  color:var(--qp-secondary);
}
body.quiet-performance .coach-why>summary,
body.quiet-performance .yoda-v2 .coach-details summary,
body.quiet-performance .coach-apply{color:var(--qp-secondary)}

/* Navigation and utilities look like controls, not badges. */
body.quiet-performance .week-nav{
  background:transparent;
  border-color:var(--qp-line);
  border-radius:12px;
  box-shadow:none;
}
body.quiet-performance .week-nav a{color:var(--qp-accent);font-weight:600}
body.quiet-performance .week-nav-center span{color:var(--qp-tertiary)}
body.quiet-performance .reference-chip,
body.quiet-performance .goal-page-link a,
body.quiet-performance .goal-back-row a{
  background:var(--qp-surface);
  border-color:var(--qp-line);
  border-radius:10px;
  box-shadow:none;
  color:var(--qp-secondary);
  font-weight:600;
}
body.quiet-performance .reference-chip:hover,
body.quiet-performance .goal-page-link a:hover,
body.quiet-performance .goal-back-row a:hover{background:var(--qp-elevated);color:var(--qp-text)}

/* History / evaluation blocks inherit the same quiet hierarchy. */
body.quiet-performance .week-activity-insight,
body.quiet-performance .week-review,
body.quiet-performance .decision,
body.quiet-performance .feedback-loop{
  background:var(--qp-canvas);
  border-color:var(--qp-line);
  box-shadow:none;
}
body.quiet-performance .week-activity-insight-kicker,
body.quiet-performance .week-activity-user-report span{color:var(--qp-tertiary)}
body.quiet-performance .week-activity-user-report{border-top-color:var(--qp-line);color:var(--qp-secondary)}

/* Goal hierarchy: same product, same visual grammar. */
body.quiet-performance.goal-page .card{
  background:var(--qp-surface);
  border-color:var(--qp-line);
  border-radius:14px;
  box-shadow:none;
}
body.quiet-performance.goal-page .title,
body.quiet-performance.goal-page .current-path h2{color:var(--qp-text);font-weight:650}
body.quiet-performance.goal-page .goal p,
body.quiet-performance.goal-page .current-purpose,
body.quiet-performance.goal-page .mesocycle-why p{color:var(--qp-secondary)}
body.quiet-performance.goal-page .goal-note,
body.quiet-performance.goal-page .current-meta,
body.quiet-performance.goal-page .section-kicker,
body.quiet-performance.goal-page .role-row span,
body.quiet-performance.goal-page .calendar-note{color:var(--qp-tertiary)!important}
body.quiet-performance.goal-page .system-step,
body.quiet-performance.goal-page .role-list,
body.quiet-performance.goal-page .role-row,
body.quiet-performance.goal-page .decision-principle{border-color:var(--qp-line-soft)}
body.quiet-performance.goal-page .system-step-num{background:var(--qp-accent-soft);color:var(--qp-accent);font-weight:650}
body.quiet-performance.goal-page .system-step p,
body.quiet-performance.goal-page .decision-principle span{color:var(--qp-secondary)}
body.quiet-performance.goal-page .goal-change{
  background:transparent;
  color:var(--qp-text);
  border-left:2px solid var(--qp-accent);
}
body.quiet-performance.goal-page .goal-change p{color:var(--qp-secondary)}

/* Modal elevation is intentional: it is the only truly elevated surface. */
body.quiet-performance .system-window{
  background:var(--qp-elevated);
  color:var(--qp-text);
  border-color:var(--qp-line);
  border-radius:16px;
  box-shadow:0 24px 64px rgba(23,25,24,.14);
}
body.quiet-performance .system-window::backdrop{background:rgba(23,25,24,.32)}
body.quiet-performance .system-head{background:var(--qp-elevated);border-bottom-color:var(--qp-line-soft)}
body.quiet-performance .system-head h2{font-weight:650}
body.quiet-performance .system-close{background:var(--qp-canvas);color:var(--qp-secondary);font-weight:600}
body.quiet-performance .system-lead{color:var(--qp-secondary)}
body.quiet-performance .system-list li{border-top-color:var(--qp-line);color:var(--qp-secondary)}
body.quiet-performance .system-list strong{color:var(--qp-text)}
body.quiet-performance footer{color:var(--qp-tertiary)}

@media(max-width:620px){
  body.quiet-performance .wrap{padding-top:20px;padding-bottom:56px}
  body.quiet-performance h1{font-size:2rem}
  body.quiet-performance .day,
  body.quiet-performance .day.workout-card-v2{border-radius:13px}
  body.quiet-performance .brain-today{border-radius:13px}
  body.quiet-performance .metric,
  body.quiet-performance .dashboard-card{border-radius:12px}
}
'''.strip()


def set_theme_color(page: str) -> str:
    replacement = f'<meta name="theme-color" content="{THEME_COLOR}">'
    page, count = THEME_RE.subn(replacement, page, count=1)
    if count != 1:
        raise RuntimeError("Quiet Performance: theme-color meta saknas")
    return page


def add_body_class(page: str) -> str:
    match = BODY_RE.search(page)
    if not match:
        raise RuntimeError("Quiet Performance: body-taggen saknas")

    attrs = match.group("attrs") or ""
    class_match = CLASS_RE.search(attrs)
    if class_match:
        classes = [value for value in class_match.group("classes").split() if value]
        if "quiet-performance" not in classes:
            classes.append("quiet-performance")
        class_attr = ' class="' + " ".join(classes) + '"'
        attrs = attrs[: class_match.start()] + class_attr + attrs[class_match.end() :]
    else:
        attrs += ' class="quiet-performance"'
    return page[: match.start()] + f"<body{attrs}>" + page[match.end() :]


def add_css(page: str) -> str:
    block = f"{CSS_START}\n{CSS}\n{CSS_END}"
    has_start = CSS_START in page
    has_end = CSS_END in page
    if has_start != has_end:
        raise RuntimeError("Quiet Performance: ofullständigt befintligt CSS-block")
    if has_start:
        match = CSS_BLOCK_RE.search(page)
        if not match:
            raise RuntimeError("Quiet Performance: befintligt CSS-block kunde inte avgränsas")
        return page[: match.start()] + block + page[match.end() :]
    if "</style>" not in page:
        raise RuntimeError("Quiet Performance: </style> saknas")
    return page.replace("</style>", block + "\n</style>", 1)


def apply_quiet_performance(page: str) -> str:
    page = set_theme_color(page)
    page = add_body_class(page)
    return add_css(page)


def validate_page(page: str, label: str = "page") -> None:
    required = [
        f'content="{THEME_COLOR}"',
        "quiet-performance",
        CSS_START,
        CSS_END,
        "--qp-canvas:#F6F7F5",
        "--qp-accent:#5964E8",
        "box-shadow:inset 2px 0 0 var(--qp-accent)",
    ]
    missing = [value for value in required if value not in page]
    if missing:
        raise RuntimeError(f"Quiet Performance: {label} saknar {missing!r}")
    if page.count(CSS_START) != 1 or page.count(CSS_END) != 1:
        raise RuntimeError(f"Quiet Performance: {label} har duplicerat designsystem")


def page_paths() -> list[Path]:
    paths = [INDEX_FILE]
    if WEEK_DIR.exists():
        paths.extend(sorted(WEEK_DIR.glob("*/index.html")))
    paths.extend([GOAL_PAGE, GOAL_PUBLIC_PAGE])
    unique = []
    for path in paths:
        if path.exists() and path not in unique:
            unique.append(path)
    return unique


def main() -> int:
    paths = page_paths()
    if not paths:
        raise RuntimeError("Quiet Performance: inga träningssidor hittades")

    for path in paths:
        rendered = apply_quiet_performance(path.read_text(encoding="utf-8"))
        validate_page(rendered, str(path.relative_to(ROOT)))
        path.write_text(rendered, encoding="utf-8")

    print(f"Quiet Performance UI OK: {len(paths)} träningssidor använder gemensamt designsystem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
