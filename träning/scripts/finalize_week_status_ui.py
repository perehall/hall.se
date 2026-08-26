#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"

CSS_MARKER = "/* week-status-ui-v2 */"
CSS = r'''
/* week-status-ui-v2 */
.week-status-expander{margin:8px 0 16px}
.week-status-expander>summary{cursor:pointer;list-style:none;color:#334155;font-size:.84rem;font-weight:850;padding:7px 0;line-height:1.35}
.week-status-expander>summary::-webkit-details-marker{display:none}
.week-status-expander>summary:after{content:" +"}
.week-status-expander[open]>summary:after{content:" −"}
.week-status-body{margin-top:8px}
.week-status-expander .dashboard{margin:0}
.week-status-expander .dashboard>.dashboard-card:last-child{display:none}
.week-status-expander .metrics{margin-bottom:12px}
.week-status-expander .dashboard-grid{grid-template-columns:1fr 1fr}
@media (max-width:620px){.week-status-expander .dashboard-grid{grid-template-columns:1fr}}
'''


def compact_duration(value):
    value = (value or "").strip()
    parts = value.split(":")
    if len(parts) == 3 and parts[-1] == "00":
        return ":".join(parts[:-1])
    return value


def extract_summary(dashboard):
    metrics = {}
    for value, label in re.findall(
        r'<div class="metric"><strong>(.*?)</strong><span>(pass|passtid|träningsdagar)</span></div>',
        dashboard,
        flags=re.S,
    ):
        metrics[label] = re.sub(r"<[^>]+>", "", value).strip()

    missing = [label for label in ("pass", "passtid", "träningsdagar") if label not in metrics]
    if missing:
        raise RuntimeError("Veckostatus-UI: nyckeltal saknas: " + repr(missing))

    pass_count = int(metrics["pass"])
    day_count = int(metrics["träningsdagar"])
    day_word = "dag" if day_count == 1 else "dagar"
    duration = compact_duration(metrics["passtid"])
    return f"Veckostatus · {pass_count} pass · {duration} · {day_count} {day_word}"


def promote_week_status(page):
    if 'class="week-status-expander"' in page:
        return page

    pattern = re.compile(
        r'<details class="week-state"><summary>Veckoläge</summary>'
        r'(?P<dashboard><section class="dashboard" aria-label="Veckoöversikt">.*?</section>)'
        r'</details>\s*',
        re.S,
    )
    match = pattern.search(page)
    if not match:
        raise RuntimeError("Veckostatus-UI: Veckoläge saknas")

    dashboard = match.group("dashboard")
    summary = extract_summary(dashboard)
    page = page[: match.start()] + page[match.end() :]

    heading = '<h2 class="section">Aktuell vecka</h2>'
    if heading not in page:
        raise RuntimeError("Veckostatus-UI: rubriken Aktuell vecka saknas")

    overview = (
        f'{heading}\n<details class="week-status-expander"><summary>{summary}</summary>'
        f'<div class="week-status-body">{dashboard}</div></details>'
    )
    page = page.replace(heading, overview, 1)

    page = re.sub(r'/\* week-status-ui-v1 \*/.*?(?=(?:/\*|</style>))', '', page, flags=re.S)
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Veckostatus-UI: index.html saknar </style>")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    return page


def main():
    page = INDEX_FILE.read_text(encoding="utf-8")
    rendered = promote_week_status(page)
    INDEX_FILE.write_text(rendered, encoding="utf-8")

    verify = INDEX_FILE.read_text(encoding="utf-8")
    heading_pos = verify.find('<h2 class="section">Aktuell vecka</h2>')
    status_pos = verify.find('class="week-status-expander"')
    day_pos = verify.find('<div class="day', status_pos)

    required = [
        CSS_MARKER,
        'class="week-status-expander"',
        '<summary>Veckostatus · ',
        '<section class="dashboard" aria-label="Veckoöversikt">',
        '.week-status-expander .dashboard>.dashboard-card:last-child{display:none}',
        '.week-status-expander>summary:after{content:" +"}',
    ]
    missing = [marker for marker in required if marker not in verify]
    if missing:
        raise RuntimeError("Veckostatus-UI: renderad sida saknar " + repr(missing))
    if 'class="week-state"' in verify or '<summary>Veckoläge</summary>' in verify:
        raise RuntimeError("Veckostatus-UI: gammalt Veckoläge finns kvar")
    if 'class="week-overview"' in verify:
        raise RuntimeError("Veckostatus-UI: gammal alltid öppen veckostatus finns kvar")
    if heading_pos < 0 or status_pos < heading_pos or day_pos < status_pos:
        raise RuntimeError("Veckostatus-UI: veckostatus ligger inte direkt före dagkorten")

    print("Veckostatus UI OK: kompakt expander direkt under Aktuell vecka.")


if __name__ == "__main__":
    main()
