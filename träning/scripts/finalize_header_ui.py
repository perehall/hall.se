#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "index.html"
ARCHIVE_ROOT = ROOT / "vecka"
CSS_MARKER = "/* week-header-layout-v3 */"
CSS = """
/* week-header-layout-v3 */
.header-meta{display:flex;align-items:baseline;gap:10px 14px;flex-wrap:wrap;margin-bottom:6px}
.header-meta .eyebrow{margin-bottom:0}
.header-updated{color:#64748b;font-size:.76rem;font-weight:500;line-height:1.35}
.week-heading{display:flex;align-items:baseline;gap:.28em;flex-wrap:wrap}
.week-period{font:inherit;font-weight:inherit;letter-spacing:inherit;color:inherit}
@media (max-width:520px){.header-meta{display:block}.header-updated{margin-top:2px;font-size:.72rem}}
""".strip()

HEADER_RE = re.compile(
    r'<header><div class="eyebrow">(?P<eyebrow>.*?)</div>'
    r'<h1>(?P<title>.*?)</h1>'
    r'<div class="sub">(?P<period>\d{4}-\d{2}-\d{2})(?:–| till )(?P<end>\d{4}-\d{2}-\d{2})'
    r'\s*·\s*(?P<meta>.*?)</div></header>'
)

MONTHS = {
    "januari": 1,
    "februari": 2,
    "mars": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "augusti": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}
UPDATED_RE = re.compile(
    r'(?:senast\s+)?uppdaterad\s+(?P<day>\d{1,2})\s+(?P<month>[a-zåäö]+)\s+\d{4}\s+·\s+(?P<time>\d{1,2}:\d{2})',
    re.I,
)


def compact_updated(meta):
    match = UPDATED_RE.fullmatch(meta.strip())
    if not match:
        raise RuntimeError(f"Header UI: kunde inte tolka uppdateringstid {meta!r}")
    month_name = match.group("month").lower()
    month = MONTHS.get(month_name)
    if month is None:
        raise RuntimeError(f"Header UI: okänd svensk månad {month_name!r}")
    return f'uppdaterad {int(match.group("day"))}/{month} {match.group("time")}'


def update_page(path):
    page = path.read_text(encoding="utf-8")

    match = HEADER_RE.search(page)
    if not match:
        raise RuntimeError(f"Header UI: kunde inte tolka header i {path}")

    eyebrow = match.group("eyebrow")
    title = match.group("title")
    period = f'{match.group("period")} till {match.group("end")}'
    meta = compact_updated(match.group("meta"))

    replacement = (
        '<header>'
        '<div class="header-meta">'
        f'<div class="eyebrow">{eyebrow}</div>'
        f'<div class="header-updated">{meta}</div>'
        '</div>'
        f'<h1 class="week-heading"><span>{title}</span><span aria-hidden="true">·</span>'
        f'<span class="week-period">{period}</span></h1>'
        '</header>'
    )
    page = page[:match.start()] + replacement + page[match.end():]

    # build.py emits fresh HTML every run, but archived pages may carry an older
    # header CSS marker. Keep only the current header rule set.
    page = re.sub(
        r'/\* week-header-layout-v2 \*/.*?(?=(?:/\*|</style>))',
        '',
        page,
        flags=re.S,
    )

    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError(f"Header UI: kunde inte hitta </style> i {path}")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    required = [
        'class="header-meta"',
        'class="header-updated"',
        'class="week-heading"',
        'class="week-period"',
        " till ",
        "uppdaterad ",
        CSS_MARKER,
    ]
    missing = [snippet for snippet in required if snippet not in page]
    if missing:
        raise RuntimeError(f"Header UI-validering misslyckades för {path}: {missing!r}")

    if "senast uppdaterad" in page:
        raise RuntimeError(f"Header UI: gammal lång uppdateringstext finns kvar i {path}")
    if '<div class="sub"><strong class="week-period">' in page:
        raise RuntimeError(f"Header UI: gammal separat periodrad finns kvar i {path}")

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

    print(f"Header UI OK: period infogad i veckorubriken och uppdateringstid komprimerad på {len(existing)} sida/sidor.")


if __name__ == "__main__":
    main()
