#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "index.html"
ARCHIVE_ROOT = ROOT / "vecka"
CSS_MARKER = "/* week-header-layout-v2 */"
CSS = """
/* week-header-layout-v2 */
.header-meta{display:flex;align-items:baseline;gap:10px 14px;flex-wrap:wrap;margin-bottom:6px}
.header-meta .eyebrow{margin-bottom:0}
.header-updated{color:#64748b;font-size:.76rem;font-weight:500;line-height:1.35}
.week-period{font-weight:800;color:#334155;white-space:nowrap}
@media (max-width:520px){.header-meta{display:block}.header-updated{margin-top:2px;font-size:.72rem}.week-period{font-size:.92rem}}
""".strip()

HEADER_RE = re.compile(
    r'<header><div class="eyebrow">(?P<eyebrow>.*?)</div>'
    r'<h1>(?P<title>.*?)</h1>'
    r'<div class="sub">(?P<period>\d{4}-\d{2}-\d{2})(?:–| till )(?P<end>\d{4}-\d{2}-\d{2})'
    r'\s*·\s*(?P<meta>.*?)</div></header>'
)


def update_page(path):
    page = path.read_text(encoding="utf-8")

    match = HEADER_RE.search(page)
    if not match:
        raise RuntimeError(f"Header UI: kunde inte tolka header i {path}")

    eyebrow = match.group("eyebrow")
    title = match.group("title")
    period = f'{match.group("period")} till {match.group("end")}'
    meta = match.group("meta")

    replacement = (
        '<header>'
        '<div class="header-meta">'
        f'<div class="eyebrow">{eyebrow}</div>'
        f'<div class="header-updated">{meta}</div>'
        '</div>'
        f'<h1>{title}</h1>'
        f'<div class="sub"><strong class="week-period">{period}</strong></div>'
        '</header>'
    )
    page = page[:match.start()] + replacement + page[match.end():]

    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError(f"Header UI: kunde inte hitta </style> i {path}")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    required = [
        'class="header-meta"',
        'class="header-updated"',
        'class="week-period"',
        " till ",
        CSS_MARKER,
    ]
    missing = [snippet for snippet in required if snippet not in page]
    if missing:
        raise RuntimeError(f"Header UI-validering misslyckades för {path}: {missing!r}")

    path.write_text(page, encoding="utf-8")


def main():
    pages = [CURRENT]
    if ARCHIVE_ROOT.exists():
        pages.extend(sorted(ARCHIVE_ROOT.glob("*/index.html")))

    existing = [path for path in pages if path.exists()]
    if not existing:
        raise RuntimeError("Header UI: inga träningssidor hittades")

    for path in existing:
        update_page(path)

    print(f"Header UI OK: period och uppdateringsmetadata formaterade på {len(existing)} sida/sidor.")


if __name__ == "__main__":
    main()
