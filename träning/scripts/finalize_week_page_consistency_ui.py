#!/usr/bin/env python3
"""Normalize current, historical and upcoming week pages to one visual week shell."""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

from finalize_top_overview_ui import focus_title, strip_tags

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PLAN = ROOT / "data" / "plan.json"
UPCOMING = ROOT / "data" / "upcoming_week.json"
WEEKS = ROOT / "vecka"

CSS_MARKER = "/* unified-week-page-shell-v1 */"
NAV_RE = re.compile(r'<nav class="top-week-nav"[^>]*>.*?</nav>', re.S)
HEADER_RE = re.compile(r'<header>.*?</header>\s*', re.S)
HERO_RE = re.compile(r'<div class="hero week-focus-card">(.*?)</div>\s*', re.S)
DASHBOARD_RE = re.compile(r'<section class="dashboard" aria-label="(?P<label>[^"]+)">(?P<body>.*?)</section>\s*', re.S)
SECTION_RE = re.compile(r'<h2 class="section">(Aktuell vecka|Preliminär vecka)</h2>\s*', re.I)

CSS = r"""
/* unified-week-page-shell-v1 */
.week-context-header{
  margin-top:38px;
  padding:0 2px 2px;
}
.week-context-header .section{
  margin:0;
  font-size:1.24rem;
  letter-spacing:-.018em;
}
.week-context-focus{
  display:block;
  margin-top:6px;
  font-size:.94rem;
  font-weight:670;
  line-height:1.4;
  letter-spacing:-.008em;
}
.week-context-meta{
  margin-top:4px;
  color:var(--qp-tertiary,#64748b);
  font-size:.72rem;
  line-height:1.4;
}
.week-context-header .top-details{margin-top:8px}
.week-context-header + .week-status-expander{
  margin-top:2px;
  margin-bottom:20px;
}
.week-status-expander{
  margin:2px 0 20px;
}
.week-status-expander>summary{
  cursor:pointer;
  list-style:none;
  color:var(--qp-tertiary,#64748b);
  font-size:.7rem;
  font-weight:620;
  padding:3px 0;
  line-height:1.35;
}
.week-status-expander>summary::-webkit-details-marker{display:none}
.week-status-expander>summary:after{content:" +"}
.week-status-expander[open]>summary:after{content:" −"}
.week-status-body{margin-top:8px}
.week-status-expander .dashboard{margin:0}
.week-page-history>.week-review{margin-top:8px}
@media(max-width:620px){
  .week-context-header{margin-top:32px;padding:0 1px 2px}
  .week-context-header .section{font-size:1.16rem}
  .week-context-focus{font-size:.9rem}
}
""".strip()


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def current_week_key(plan: dict) -> str:
    start = date.fromisoformat(str((plan.get("meta") or {})["week_start"]))
    iso = start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def install_css(page: str) -> str:
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Week shell: </style> saknas")
    return page.replace("</style>", CSS + "\n</style>", 1)


def extract_hero(page: str) -> tuple[str, str, str]:
    match = HERO_RE.search(page)
    if not match:
        return page, "", ""
    body = match.group(1)
    title_match = re.search(r'class="week-focus-title">(.*?)</h2>', body, re.S | re.I)
    details_match = re.search(
        r'<details class="week-focus-details"><summary>Planidé</summary>(?P<body>.*?)</details>',
        body,
        re.S | re.I,
    )
    title = strip_tags(title_match.group(1)) if title_match else ""
    details = details_match.group("body").strip() if details_match else ""
    return page[:match.start()] + page[match.end():], title, details


def clean_focus(raw: str) -> tuple[str, str]:
    text = strip_tags(raw)
    micro = ""
    micro_match = re.search(r'·\s*(mikrocykel\s+\d+\s+av\s+\d+)\s*$', text, re.I)
    if micro_match:
        micro = micro_match.group(1)
        text = text[:micro_match.start()].strip(" ·")
    text = re.sub(r'^Fortsatt\s+byggblock\s*[—-]\s*prioritet\s+', "", text, flags=re.I)
    text = re.sub(r'^Mesocykel\s*·\s*', "", text, flags=re.I)
    return text or "Veckans utvecklingsfokus", micro


def extract_dashboard(page: str) -> tuple[str, str, str]:
    match = DASHBOARD_RE.search(page)
    if not match:
        return page, "", ""
    full = match.group(0).strip()
    label = match.group("label")
    return page[:match.start()] + page[match.end():], full, label


def metrics_summary(dashboard: str) -> str:
    if not dashboard:
        return ""
    pairs = re.findall(
        r'<div class="metric"><strong>(.*?)</strong><span>(.*?)</span></div>',
        dashboard,
        re.S | re.I,
    )
    values = []
    for value, label in pairs:
        clean_value = strip_tags(value)
        clean_label = strip_tags(label)
        if clean_label in {"pass", "passtid", "träningsdagar"}:
            values.append(f"{clean_value} {clean_label}")
    return " · ".join(values)


def preview_summary(dashboard: str) -> str:
    match = re.search(r'class="preview-focus">(.*?)</div>', dashboard or "", re.S | re.I)
    return strip_tags(match.group(1)) if match else ""


def structured_future_focus(upcoming: dict) -> str:
    meta = upcoming.get("meta") or {}
    if not meta:
        return ""
    return focus_title(meta)


def context_header(title: str, focus: str, meta_bits: list[str], plan_body: str) -> str:
    details = ""
    if plan_body:
        details = (
            '<details class="top-details week-context-plan"><summary>Planidé</summary>'
            f'<div class="top-details-body">{plan_body}</div></details>'
        )
    return (
        '<section class="week-context-header">'
        f'<h2 class="section">{html.escape(title)}</h2>'
        f'<strong class="week-context-focus">{html.escape(focus)}</strong>'
        f'<div class="week-context-meta">{html.escape(" · ".join(bit for bit in meta_bits if bit))}</div>'
        + details
        + '</section>'
    )


def status_expander(dashboard: str, summary_label: str = "Veckostatus") -> str:
    if not dashboard:
        return ""
    return (
        f'<details class="week-status-expander"><summary>{html.escape(summary_label)}</summary>'
        f'<div class="week-status-body">{dashboard}</div></details>'
    )


def add_body_class(page: str, css_class: str) -> str:
    match = re.search(r'<body class="([^"]*)"', page)
    if match:
        classes = match.group(1).split()
        if css_class not in classes:
            classes.append(css_class)
        return page[:match.start(1)] + " ".join(classes) + page[match.end(1):]
    return page.replace("<body", f'<body class="{css_class}"', 1)


def normalize_current(page: str) -> str:
    page = page.replace(
        '<section class="current-week-header"',
        '<section class="week-context-header current-week-header"',
        1,
    )
    page = page.replace(
        'class="current-week-focus"',
        'class="week-context-focus current-week-focus"',
        1,
    )
    page = page.replace(
        'class="current-week-meta"',
        'class="week-context-meta current-week-meta"',
        1,
    )
    return add_body_class(page, "week-page-current")


def normalize_history(page: str) -> str:
    page = HEADER_RE.sub("", page, count=1)
    page, raw_focus, plan_body = extract_hero(page)
    focus, micro = clean_focus(raw_focus)
    page, dashboard, _ = extract_dashboard(page)
    metrics = metrics_summary(dashboard)
    page = SECTION_RE.sub("", page, count=1)

    nav = NAV_RE.search(page)
    if not nav:
        raise RuntimeError("Week shell history: navigation saknas")

    meta_bits = ["Historik"]
    if micro:
        meta_bits.append(micro)
    if metrics:
        meta_bits.append(metrics)

    header = context_header("Historisk vecka", focus, meta_bits, plan_body)
    status = status_expander(dashboard)
    insert = nav.end()
    page = page[:insert] + "\n" + header + "\n" + status + page[insert:]
    return add_body_class(page, "week-page-history")


def normalize_future(page: str, upcoming: dict) -> str:
    page = HEADER_RE.sub("", page, count=1)
    page, raw_focus, plan_body = extract_hero(page)
    raw_clean, micro = clean_focus(raw_focus)
    focus = structured_future_focus(upcoming) or raw_clean
    page, dashboard, _ = extract_dashboard(page)
    page = SECTION_RE.sub("", page, count=1)

    nav = NAV_RE.search(page)
    if not nav:
        raise RuntimeError("Week shell future: navigation saknas")

    meta = upcoming.get("meta") or {}
    micro_index = meta.get("microcycle_index")
    micro_total = meta.get("microcycle_total")
    meta_bits = ["Preliminär"]
    if micro_index and micro_total:
        meta_bits.append(f"mikrocykel {micro_index} av {micro_total}")
    elif micro:
        meta_bits.append(micro)

    counts = re.findall(
        r'<div class="metric"><strong>(.*?)</strong><span>(fast|planerat|preliminärt|öppet)</span></div>',
        dashboard or "",
        re.S | re.I,
    )
    if counts:
        meta_bits.append(" · ".join(f"{strip_tags(value)} {strip_tags(label)}" for value, label in counts))

    if not plan_body:
        summary = preview_summary(dashboard)
        if summary:
            plan_body = f"<p>{html.escape(summary)}</p>"

    header = context_header("Kommande vecka", focus, meta_bits, plan_body)
    status = status_expander(dashboard, "Planstatus")
    insert = nav.end()
    page = page[:insert] + "\n" + header + "\n" + status + page[insert:]
    return add_body_class(page, "week-page-future")


def normalize_page(path: Path, key: str, current_key: str, upcoming: dict) -> None:
    page = path.read_text(encoding="utf-8")
    if key == current_key:
        page = normalize_current(page)
    elif key == str(upcoming.get("week_key") or ""):
        page = normalize_future(page, upcoming)
    else:
        page = normalize_history(page)
    page = install_css(page)
    path.write_text(page, encoding="utf-8")


def validate_page(page: str, state: str) -> None:
    required = (
        CSS_MARKER,
        'class="top-week-nav"',
        'class="week-context-header',
        'class="week-context-focus',
        'class="week-context-meta',
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError(f"Week shell {state}: saknar {missing!r}")

    if '<div class="hero week-focus-card">' in page:
        raise RuntimeError(f"Week shell {state}: gammal fokus-hero finns kvar")

    if state != "current" and "<header>" in page:
        raise RuntimeError(f"Week shell {state}: gammal stor header finns kvar")

    if state == "history" and "Aktuell vecka" in page:
        raise RuntimeError("Week shell history: felaktig rubrik Aktuell vecka finns kvar")
    if state == "future" and "Preliminär vecka" in page:
        raise RuntimeError("Week shell future: gammal rubrik Preliminär vecka finns kvar")


def main() -> int:
    plan = load_json(PLAN, {"meta": {}})
    upcoming = load_json(UPCOMING, {})
    current_key = current_week_key(plan)

    pages: list[tuple[Path, str, str]] = [(INDEX, current_key, "current")]
    if WEEKS.exists():
        for folder in sorted(WEEKS.iterdir()):
            if not folder.is_dir() or not re.fullmatch(r"\d{4}-W\d{2}", folder.name):
                continue
            page = folder / "index.html"
            if not page.exists():
                continue
            state = "future" if folder.name == str(upcoming.get("week_key") or "") else "history"
            pages.append((page, folder.name, state))

    for path, key, _ in pages:
        normalize_page(path, key, current_key, upcoming)

    for path, _, state in pages:
        validate_page(path.read_text(encoding="utf-8"), state)

    print(f"Week page shell OK: {len(pages)} vecka/sidor delar samma rubrikhierarki.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
