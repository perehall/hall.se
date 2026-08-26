#!/usr/bin/env python3
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "index.html"
ARCHIVE_ROOT = ROOT / "vecka"
CSS_MARKER = "/* week-header-layout-v6 */"
CSS = """
/* week-header-layout-v6 */
.week-heading-row{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}.week-heading-row h1{flex:0 0 auto;margin-bottom:0}.week-focus{min-width:0;color:#334155;font-size:.92rem;font-weight:650;line-height:1.35}.week-focus strong{font-weight:900;color:#0f172a}.header-updated{margin-top:4px;color:#94a3b8;font-size:.74rem;font-weight:500;line-height:1.35}.header-status{margin-top:4px;color:#64748b;font-size:.76rem;font-weight:700;line-height:1.35}.week-period{font-weight:800;color:#334155;white-space:nowrap}.hero.focus-moved h2{display:none}
@media (max-width:620px){.week-heading-row{display:grid;gap:5px}.week-heading-row h1{margin-bottom:0}.week-focus{font-size:.86rem}.header-updated{font-size:.7rem}.header-status{font-size:.72rem}.week-period{font-size:.92rem}}
""".strip()

HEADER_RE = re.compile(
    r'<header><div class="eyebrow">(?P<eyebrow>.*?)</div>'
    r'<h1>(?P<title>.*?)</h1>'
    r'<div class="sub">(?P<period>\d{4}-\d{2}-\d{2})(?:–| till )(?P<end>\d{4}-\d{2}-\d{2})'
    r'\s*·\s*(?P<meta>.*?)</div></header>'
)
HERO_RE = re.compile(
    r'<div class="hero(?P<class_extra>[^"]*)"><h2>(?P<focus>.*?)</h2><p>(?P<principle>.*?)</p></div>',
    re.S,
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
HISTORY_RE = re.compile(
    r'historik\s*·\s*data sparad\s+(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{1,2}:\d{2})',
    re.I,
)
STATIC_META = {"preliminär plan"}


def format_meta(meta):
    value = meta.strip()
    if value.lower() in STATIC_META:
        return "header-status", value.capitalize()

    history = HISTORY_RE.fullmatch(value)
    if history:
        return "header-status", f'Historik · data sparad {history.group("date")} {history.group("time")}'

    match = UPDATED_RE.fullmatch(value)
    if not match:
        raise RuntimeError(f"Header UI: kunde inte tolka header-meta {meta!r}")
    month_name = match.group("month").lower()
    month = MONTHS.get(month_name)
    if month is None:
        raise RuntimeError(f"Header UI: okänd svensk månad {month_name!r}")
    text = f'Senast uppdaterad {int(match.group("day"))}/{month} {match.group("time")}'
    return "header-updated", text


def extract_focus(page):
    match = HERO_RE.search(page)
    if not match:
        raise RuntimeError("Header UI: veckofokus saknas i hero")
    focus = html.unescape(re.sub(r"\s+", " ", match.group("focus"))).strip()
    if not focus:
        raise RuntimeError("Header UI: tomt veckofokus")
    return focus, match


def update_page(path):
    page = path.read_text(encoding="utf-8")

    match = HEADER_RE.search(page)
    if not match:
        # Already finalized pages are left untouched; build.py emits a fresh raw
        # header for the current page on every pipeline run.
        if CSS_MARKER in page:
            return
        raise RuntimeError(f"Header UI: kunde inte tolka header i {path}")

    focus, hero_match = extract_focus(page)
    eyebrow = match.group("eyebrow")
    title = match.group("title")
    period = f'{match.group("period")} till {match.group("end")}'
    meta_class, meta = format_meta(match.group("meta"))

    replacement = (
        '<header>'
        f'<div class="eyebrow">{eyebrow}</div>'
        '<div class="week-heading-row">'
        f'<h1>{title}</h1>'
        f'<div class="week-focus"><strong>Veckofokus:</strong> {html.escape(focus)}</div>'
        '</div>'
        f'<div class="sub"><strong class="week-period">{period}</strong></div>'
        f'<div class="{meta_class}">{meta}</div>'
        '</header>'
    )
    page = page[:match.start()] + replacement + page[match.end():]

    # The focus now belongs to the heading row; keep the longer weekly principle
    # in the hero without repeating the title.
    hero_match = HERO_RE.search(page)
    if not hero_match:
        raise RuntimeError(f"Header UI: hero försvann efter headerbyte i {path}")
    extra = hero_match.group("class_extra") or ""
    classes = (extra + " focus-moved").strip()
    hero_replacement = f'<div class="hero {classes}"><p>{hero_match.group("principle")}</p></div>'
    page = page[:hero_match.start()] + hero_replacement + page[hero_match.end():]

    # Remove obsolete header layouts before adding the current rule set.
    page = re.sub(
        r'/\* week-header-layout-v[2345] \*/.*?(?=(?:/\*|</style>))',
        '',
        page,
        flags=re.S,
    )

    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError(f"Header UI: kunde inte hitta </style> i {path}")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    required = [
        '<div class="eyebrow">',
        '<div class="week-heading-row">',
        '<div class="week-focus"><strong>Veckofokus:</strong>',
        html.escape(focus),
        '<div class="sub"><strong class="week-period">',
        f'class="{meta_class}"',
        " till ",
        meta,
        CSS_MARKER,
        'focus-moved',
    ]
    missing = [snippet for snippet in required if snippet not in page]
    if missing:
        raise RuntimeError(f"Header UI-validering misslyckades för {path}: {missing!r}")

    if '<div class="hero"><h2>' in page or '<div class="hero focus-moved"><h2>' in page:
        raise RuntimeError(f"Header UI: veckofokus dupliceras fortfarande i hero i {path}")
    if 'class="header-meta"' in page:
        raise RuntimeError(f"Header UI: uppdateringstext ligger fortfarande bredvid eyebrow i {path}")
    if 'class="week-heading"' in page:
        raise RuntimeError(f"Header UI: perioden ligger fortfarande i H1 i {path}")

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

    print(f"Header UI OK: veckofokus i rubrikraden på {len(existing)} sida/sidor.")


if __name__ == "__main__":
    main()
