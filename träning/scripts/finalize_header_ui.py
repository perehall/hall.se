#!/usr/bin/env python3
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "index.html"
ARCHIVE_ROOT = ROOT / "vecka"
CSS_MARKER = "/* week-header-layout-v8 */"
CSS = """
/* week-header-layout-v8 */
.header-meta-line{display:flex;flex-wrap:wrap;gap:4px;color:#94a3b8;font-size:.76rem;line-height:1.4}.header-updated,.header-status{color:#94a3b8;font-size:inherit;font-weight:500}.week-period{font-weight:600;color:#64748b;white-space:nowrap}
.hero.week-focus-card{padding:16px 18px}.week-focus-title{margin:0!important;font-size:1.06rem;line-height:1.35;letter-spacing:-.01em;font-weight:700}.week-focus-details{margin-top:8px}.week-focus-details>summary{cursor:pointer;list-style:none;color:#94a3b8;font-size:.76rem;font-weight:600}.week-focus-details>summary::-webkit-details-marker{display:none}.week-focus-details>summary:after{content:" +"}.week-focus-details[open]>summary:after{content:" −"}.week-focus-details p{margin:8px 0 0!important;color:#cbd5e1!important;font-size:.88rem;line-height:1.5}
@media (max-width:520px){.header-meta-line{font-size:.72rem}.hero.week-focus-card{padding:14px 16px}.week-focus-title{font-size:1rem}.week-focus-details p{font-size:.84rem}}
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

MONTH_SHORT = {1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "maj", 6: "jun", 7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec"}

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
OLD_HEADER_MARKER_RE = re.compile(r'/\* week-header-layout-v[2-6] \*/')


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
    text = f'uppdaterad {int(match.group("day"))} {MONTH_SHORT[month]} {match.group("time")}'
    return "header-updated", text


def compact_period(start_value, end_value):
    from datetime import date
    start = date.fromisoformat(start_value)
    end = date.fromisoformat(end_value)
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.day}–{end.day} {MONTH_SHORT[start.month]}"
        return f"{start.day} {MONTH_SHORT[start.month]}–{end.day} {MONTH_SHORT[end.month]}"
    return f"{start.day} {MONTH_SHORT[start.month]} {start.year}–{end.day} {MONTH_SHORT[end.month]} {end.year}"



def extract_focus(page):
    match = HERO_RE.search(page)
    if not match:
        raise RuntimeError("Header UI: veckofokus saknas i hero")
    focus = html.unescape(re.sub(r"\s+", " ", match.group("focus"))).strip()
    principle = html.unescape(re.sub(r"\s+", " ", match.group("principle"))).strip()
    if not focus:
        raise RuntimeError("Header UI: tomt veckofokus")
    if not principle:
        raise RuntimeError("Header UI: tom planidé")
    return focus, principle, match


def update_page(path):
    page = path.read_text(encoding="utf-8")

    match = HEADER_RE.search(page)
    if not match:
        # Historical snapshots already finalized by an older layout remain stable.
        # build.py emits a fresh raw header for the active page on every render.
        if CSS_MARKER in page or OLD_HEADER_MARKER_RE.search(page):
            return
        raise RuntimeError(f"Header UI: kunde inte tolka header i {path}")

    focus, principle, _ = extract_focus(page)
    eyebrow = "Träningsplan"
    title = match.group("title")
    period = compact_period(match.group("period"), match.group("end"))
    meta_class, meta = format_meta(match.group("meta"))

    replacement = (
        '<header>'
        f'<div class="eyebrow">{eyebrow}</div>'
        f'<h1>{title}</h1>'
        f'<div class="sub header-meta-line"><span class="week-period">{period}</span><span>·</span><span class="{meta_class}">{meta}</span></div>'
        '</header>'
    )
    page = page[:match.start()] + replacement + page[match.end():]

    hero_match = HERO_RE.search(page)
    if not hero_match:
        raise RuntimeError(f"Header UI: hero försvann efter headerbyte i {path}")
    hero_replacement = (
        '<div class="hero week-focus-card">'
        f'<h2 class="week-focus-title">{html.escape(focus)}</h2>'
        '<details class="week-focus-details">'
        '<summary>Planidé</summary>'
        f'<p>{html.escape(principle)}</p>'
        '</details>'
        '</div>'
    )
    page = page[:hero_match.start()] + hero_replacement + page[hero_match.end():]

    # Remove obsolete current-page header layouts before adding the current rule set.
    page = re.sub(
        r'/\* week-header-layout-v[234567] \*/.*?(?=(?:/\*|</style>))',
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
        '<h1>',
        '<div class="sub header-meta-line"><span class="week-period">',
        f'class="{meta_class}"',
        '<div class="hero week-focus-card">',
        html.escape(focus),
        '<summary>Planidé</summary>',
        html.escape(principle),
        meta,
        CSS_MARKER,
    ]
    missing = [snippet for snippet in required if snippet not in page]
    if missing:
        raise RuntimeError(f"Header UI-validering misslyckades för {path}: {missing!r}")

    if 'class="week-focus"' in page or 'class="week-heading-row"' in page:
        raise RuntimeError(f"Header UI: veckofokus ligger fortfarande i rubrikraden i {path}")
    if '<details class="week-focus-details" open' in page:
        raise RuntimeError(f"Header UI: planidén är inte stängd som standard i {path}")
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

    print(f"Header UI OK: veckofokus i hero och planidé infälld på aktiv sida.")


if __name__ == "__main__":
    main()
