#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"

CSS_MARKER = "/* week-status-ui-v1 */"
CSS = r'''
/* week-status-ui-v1 */
.week-overview{margin:8px 0 16px}
.week-overview .dashboard{margin:0}
.week-overview .dashboard>.dashboard-card:last-child{display:none}
.week-overview .metrics{margin-bottom:12px}
.week-overview .dashboard-grid{grid-template-columns:1fr 1fr}
@media (max-width:620px){.week-overview .dashboard-grid{grid-template-columns:1fr}}
'''


def promote_week_status(page):
    if 'class="week-overview"' in page:
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
    page = page[: match.start()] + page[match.end() :]

    heading = '<h2 class="section">Aktuell vecka</h2>'
    if heading not in page:
        raise RuntimeError("Veckostatus-UI: rubriken Aktuell vecka saknas")

    overview = f'{heading}\n<div class="week-overview">{dashboard}</div>'
    page = page.replace(heading, overview, 1)

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
    overview_pos = verify.find('class="week-overview"')
    day_pos = verify.find('<div class="day', overview_pos)

    required = [
        CSS_MARKER,
        'class="week-overview"',
        '<section class="dashboard" aria-label="Veckoöversikt">',
        '.week-overview .dashboard>.dashboard-card:last-child{display:none}',
    ]
    missing = [marker for marker in required if marker not in verify]
    if missing:
        raise RuntimeError("Veckostatus-UI: renderad sida saknar " + repr(missing))
    if 'class="week-state"' in verify or '<summary>Veckoläge</summary>' in verify:
        raise RuntimeError("Veckostatus-UI: gammalt infällt Veckoläge finns kvar")
    if heading_pos < 0 or overview_pos < heading_pos or day_pos < overview_pos:
        raise RuntimeError("Veckostatus-UI: veckostatus ligger inte direkt före dagkorten")

    print("Veckostatus UI OK: statistik synlig direkt under Aktuell vecka.")


if __name__ == "__main__":
    main()
