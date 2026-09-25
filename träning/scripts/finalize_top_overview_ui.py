#!/usr/bin/env python3
"""Collapse the current-page top into one crisp overview.

The generated header/navigation/training-brain/week-focus components are useful
upstream inputs, but the final current page should expose only one hierarchy:

  orientation -> today -> week focus -> current week

The full workout prescription remains exclusively in "Aktuell vecka".
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from finalize_day_session_icons import SPORT_ICON_KEYS, icon
from finalize_upcoming_workout_shell_ui import split_session

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
ICON_FILE = ROOT / "data" / "sport_icons.json"
WEEK_DIR = ROOT / "vecka"

CSS_MARKER = "/* crisp-top-overview-v1 */"
CURRENT_WEEK_HEADING = '<h2 class="section">Aktuell vecka</h2>'
FLOATING_INPUT_RE = re.compile(
    r'<section class="training-input"[^>]*data-training-input[^>]*data-activity-id="(?P<id>\d+)"',
    re.I,
)

MONTH_SHORT = {
    1: "jan",
    2: "feb",
    3: "mar",
    4: "apr",
    5: "maj",
    6: "jun",
    7: "jul",
    8: "aug",
    9: "sep",
    10: "okt",
    11: "nov",
    12: "dec",
}
WEEKDAYS = (
    "måndag",
    "tisdag",
    "onsdag",
    "torsdag",
    "fredag",
    "lördag",
    "söndag",
)

CAPABILITY_LABELS = {
    "swim_threshold": "kontrollerad simtröskel",
    "run_threshold": "kontrollerad löptröskel",
    "run_easy_distance": "lugn löpdistans",
    "run_hill_quality": "backstyrka/löpekonomi",
    "mtb_aerobic": "MTB aerob",
    "mtb_technical": "MTB teknik",
    "strength_unilateral": "unilateral styrka",
    "strength_core": "core",
    "plyometric": "plyometri",
    "enduro_technical": "enduroteknik",
}

CSS = r"""
/* crisp-top-overview-v1 */
body.quiet-performance.qp-current .top-overview{margin:0 0 2px;color:var(--qp-text,#111827)}
body.quiet-performance.qp-current .top-week-nav{
  display:grid;
  grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);
  align-items:center;
  gap:14px;
  padding:2px 0 12px;
  border-bottom:1px solid var(--qp-line,#e2e8f0);
}
body.quiet-performance.qp-current .top-week-link{
  color:var(--qp-secondary,#59636f);
  font-size:.78rem;
  font-weight:650;
  text-decoration:none;
  white-space:nowrap;
}
body.quiet-performance.qp-current .top-week-link.next{text-align:right}
body.quiet-performance.qp-current .top-week-link:hover{color:var(--qp-text,#111827)}
body.quiet-performance.qp-current .top-week-current{
  display:flex;
  align-items:baseline;
  justify-content:center;
  gap:6px;
  min-width:0;
  text-align:center;
}
body.quiet-performance.qp-current .top-week-current strong{
  font-size:.92rem;
  font-weight:780;
  letter-spacing:-.01em;
}
body.quiet-performance.qp-current .top-week-current span{
  color:var(--qp-tertiary,#64748b);
  font-size:.73rem;
  white-space:nowrap;
}
body.quiet-performance.qp-current .top-meta{
  display:flex;
  justify-content:center;
  align-items:center;
  gap:8px;
  margin-top:7px;
  color:var(--qp-tertiary,#64748b);
  font-size:.68rem;
}
body.quiet-performance.qp-current .top-meta a{
  color:var(--qp-secondary,#59636f);
  font-weight:650;
  text-decoration:none;
}
body.quiet-performance.qp-current .top-meta-sep{color:var(--qp-line,#cbd5e1)}
body.quiet-performance.qp-current .top-today{
  padding:22px 0 20px;
  border-bottom:1px solid var(--qp-line,#e2e8f0);
}
body.quiet-performance.qp-current .top-today-kicker{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:8px;
}
body.quiet-performance.qp-current .top-kicker{
  color:var(--qp-tertiary,#64748b);
  font-size:.66rem;
  font-weight:800;
  letter-spacing:.075em;
  text-transform:uppercase;
}
body.quiet-performance.qp-current .top-status{
  color:var(--qp-tertiary,#64748b);
  font-size:.68rem;
  font-weight:650;
  white-space:nowrap;
}
body.quiet-performance.qp-current .top-today-title{
  display:flex;
  align-items:center;
  gap:8px;
  font-size:1.19rem;
  font-weight:720;
  line-height:1.3;
  letter-spacing:-.018em;
}
body.quiet-performance.qp-current .top-today-title .sport-icon{
  width:20px;
  height:20px;
  flex:0 0 auto;
  color:var(--qp-secondary,#59636f);
}
body.quiet-performance.qp-current .top-today-title .icon-swim,
body.quiet-performance.qp-current .top-today-title .icon-bike,
body.quiet-performance.qp-current .top-today-title .icon-enduro,
body.quiet-performance.qp-current .top-today-title .icon-strength{width:22px}
body.quiet-performance.qp-current .top-today-meta{
  margin:4px 0 0 30px;
  color:var(--qp-secondary,#64748b);
  font-size:.8rem;
  line-height:1.4;
}
body.quiet-performance.qp-current .top-next{
  margin-top:13px;
  color:var(--qp-secondary,#59636f);
  font-size:.78rem;
  line-height:1.4;
}
body.quiet-performance.qp-current .top-next strong{
  color:var(--qp-text,#111827);
  font-weight:680;
}
body.quiet-performance.qp-current .top-details{
  margin-top:8px;
}
body.quiet-performance.qp-current .top-details>summary{
  cursor:pointer;
  list-style:none;
  color:var(--qp-tertiary,#64748b);
  font-size:.72rem;
  font-weight:650;
}
body.quiet-performance.qp-current .top-details>summary::-webkit-details-marker{display:none}
body.quiet-performance.qp-current .top-details>summary:after{content:" +"}
body.quiet-performance.qp-current .top-details[open]>summary:after{content:" −"}
body.quiet-performance.qp-current .top-details-body{
  margin-top:8px;
  padding-left:12px;
  border-left:1px solid var(--qp-line,#e2e8f0);
  color:var(--qp-secondary,#475569);
  font-size:.78rem;
  line-height:1.5;
}
body.quiet-performance.qp-current .top-details-body p{margin:0}
body.quiet-performance.qp-current .top-details-body p+p{margin-top:8px}
body.quiet-performance.qp-current .top-week-focus{
  padding:18px 0 20px;
  border-bottom:1px solid var(--qp-line,#e2e8f0);
}
body.quiet-performance.qp-current .top-focus-title{
  display:block;
  margin-top:5px;
  font-size:1rem;
  font-weight:690;
  line-height:1.38;
  letter-spacing:-.012em;
}
body.quiet-performance.qp-current .top-focus-meta{
  margin-top:4px;
  color:var(--qp-tertiary,#64748b);
  font-size:.72rem;
}
body.quiet-performance.qp-current .top-week-focus .top-details{margin-top:9px}
body.quiet-performance.qp-current .top-overview + .section{margin-top:25px}
@media(max-width:620px){
  body.quiet-performance.qp-current .top-week-nav{gap:8px}
  body.quiet-performance.qp-current .top-week-link{font-size:.72rem}
  body.quiet-performance.qp-current .top-week-current{display:grid;gap:0}
  body.quiet-performance.qp-current .top-week-current strong{font-size:.86rem}
  body.quiet-performance.qp-current .top-week-current span{font-size:.67rem}
  body.quiet-performance.qp-current .top-meta{font-size:.64rem}
  body.quiet-performance.qp-current .top-today{padding:19px 0 18px}
  body.quiet-performance.qp-current .top-today-title{font-size:1.1rem}
  body.quiet-performance.qp-current .top-today-meta{margin-left:29px;font-size:.76rem}
  body.quiet-performance.qp-current .top-week-focus{padding:16px 0 18px}
}
""".strip()


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or ""))).strip()


def iso_week_key(value: date) -> str:
    iso = value.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def compact_period(start_value: str, end_value: str) -> str:
    start = date.fromisoformat(start_value)
    end = date.fromisoformat(end_value)
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {MONTH_SHORT[start.month]}"
    if start.year == end.year:
        return f"{start.day} {MONTH_SHORT[start.month]}–{end.day} {MONTH_SHORT[end.month]}"
    return (
        f"{start.day} {MONTH_SHORT[start.month]} {start.year}–"
        f"{end.day} {MONTH_SHORT[end.month]} {end.year}"
    )


def updated_label(page: str) -> str:
    match = re.search(r'<span class="header-updated">([^<]+)</span>', page, re.I)
    if not match:
        return ""
    value = strip_tags(match.group(1))
    return value[:1].upper() + value[1:] if value else ""


def status_label(day: dict, *, has_completed_activity: bool) -> str:
    status = str(day.get("status") or "").strip().lower()
    if status == "completed" or (has_completed_activity and day.get("activity_id")):
        return "Genomfört"
    if day.get("alternative_sports"):
        return "Alternativ finns"
    planning_status = str(day.get("planning_status") or "").strip().lower()
    if planning_status == "fixed" or day.get("manual_lock"):
        return "Fast"
    return {
        "planned": "Planerat",
        "preliminary": "Kan ändras",
        "conditional": "Kan ändras",
        "open": "Inte bestämt",
    }.get(status, status.capitalize() if status else "")


def clean_reason(value: str) -> str:
    plain = strip_tags(value)
    if not plain:
        return ""
    cut_markers = (
        " Valet utgår från",
        " Veckobeslut:",
        " materialiserad relation:",
        " Katalogen innehåller",
    )
    for marker in cut_markers:
        if marker in plain:
            plain = plain.split(marker, 1)[0].strip()
    return plain


def today_icon(day: dict, registry: dict) -> str:
    sport = str(day.get("sport") or "").strip().lower()
    key = SPORT_ICON_KEYS.get(sport)
    return icon(key, registry) if key else ""


def next_day_copy(plan: dict, current_date: date) -> tuple[str, str]:
    tomorrow = current_date + timedelta(days=1)
    days = {
        date.fromisoformat(str(day.get("date"))): day
        for day in plan.get("days") or []
        if day.get("date")
    }
    target = days.get(tomorrow)
    prefix = "Imorgon"
    if target is None:
        later = sorted(day_date for day_date in days if day_date > current_date)
        if not later:
            return "", ""
        target_date = later[0]
        target = days[target_date]
        prefix = WEEKDAYS[target_date.weekday()].capitalize()

    session = str(target.get("session") or "").strip()
    if session.lower() in {"ingen planerad träning", "vilodag"} or str(target.get("sport") or "").lower() in {"open", "rest"}:
        return prefix, "Vilodag"

    title, meta = split_session(target)
    value = title
    if meta:
        value += f" · {meta}"
    return prefix, value


def focus_title(meta: dict) -> str:
    contract = meta.get("mesocycle_contract") or {}
    primary = list(contract.get("primary") or [])
    remaining = set(primary)
    labels: list[str] = []

    if "swim_aerobic" in remaining and "swim_technique" in remaining:
        labels.append("Sim aerob/teknik")
        remaining.discard("swim_aerobic")
        remaining.discard("swim_technique")
    elif "swim_aerobic" in remaining:
        labels.append("Sim aerob")
        remaining.discard("swim_aerobic")
    elif "swim_technique" in remaining:
        labels.append("Simteknik")
        remaining.discard("swim_technique")

    if "mtb_aerobic" in remaining and "mtb_technical" in remaining:
        labels.append("MTB aerob/teknik")
        remaining.discard("mtb_aerobic")
        remaining.discard("mtb_technical")

    if "strength_unilateral" in remaining and "strength_core" in remaining:
        labels.append("styrka/core")
        remaining.discard("strength_unilateral")
        remaining.discard("strength_core")

    for capability in primary:
        if capability not in remaining:
            continue
        labels.append(CAPABILITY_LABELS.get(capability, capability.replace("_", " ")))
        remaining.discard(capability)

    if labels:
        return " + ".join(labels)

    raw = str(meta.get("title") or "").strip()
    raw = re.sub(r"^Fortsatt\s+byggblock\s*[—-]\s*prioritet\s+", "", raw, flags=re.I)
    raw = re.sub(r"\s*·\s*mikrocykel\s+\d+\s+av\s+\d+\s*$", "", raw, flags=re.I)
    return raw or "Veckans utvecklingsfokus"


def block_label(meta: dict) -> str:
    title = str(meta.get("title") or "").lower()
    return "Byggblock" if "byggblock" in title else "Mesocykel"


def capability_list(values: list[str]) -> str:
    labels = []
    seen = set()
    for value in values:
        label = CAPABILITY_LABELS.get(value, value.replace("_", " "))
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return ", ".join(labels)


def focus_details(plan_meta: dict, strategy: dict) -> str:
    current = strategy.get("current_mesocycle") or {}
    parts = []
    principle = strip_tags(str(plan_meta.get("principle") or current.get("goal_contribution") or ""))
    if principle:
        parts.append(f"<p>{html.escape(principle)}</p>")
    hypothesis = strip_tags(str(current.get("hypothesis") or ""))
    if hypothesis:
        parts.append(
            '<p><strong>Mesocykelhypotes:</strong> '
            + html.escape(hypothesis)
            + "</p>"
        )
    contract = plan_meta.get("mesocycle_contract") or current.get("contract") or {}
    taxonomy = []
    for label, key in (
        ("Primärt", "primary"),
        ("Sekundärt", "secondary"),
        ("Underhåll", "maintenance"),
        ("Skyddat", "protected_capacity"),
    ):
        values = list(contract.get(key) or [])
        if values:
            taxonomy.append(f"<strong>{label}:</strong> {html.escape(capability_list(values))}")
    if taxonomy:
        parts.append("<p>" + " · ".join(taxonomy) + "</p>")
    return "".join(parts)


def verify_floating_feedback_can_be_dropped(top_region: str, week_region: str) -> None:
    ids = FLOATING_INPUT_RE.findall(top_region)
    for activity_id in ids:
        tokens = (
            f'data-feedback-activity-id="{activity_id}"',
            f'data-activity-id="{activity_id}"',
        )
        if not any(token in week_region for token in tokens):
            raise RuntimeError(
                "Crisp top: fristående feedback kan inte tas bort säkert; "
                f"aktivitet {activity_id} saknas i Aktuell vecka."
            )


def build_top(
    page: str,
    plan: dict,
    strategy: dict,
    activities: dict,
    registry: dict,
    *,
    today: date,
) -> str:
    meta = plan.get("meta") or {}
    week = int(meta.get("week") or today.isocalendar().week)
    week_start = date.fromisoformat(str(meta.get("week_start") or today.isoformat()))
    week_end = date.fromisoformat(str(meta.get("week_end") or week_start.isoformat()))
    period = compact_period(week_start.isoformat(), week_end.isoformat())

    prev_start = week_start - timedelta(days=7)
    next_start = week_start + timedelta(days=7)
    prev_key = iso_week_key(prev_start)
    next_key = iso_week_key(next_start)
    prev_link = f"/träning/vecka/{prev_key}/" if (WEEK_DIR / prev_key / "index.html").exists() else ""
    next_link = f"/träning/vecka/{next_key}/" if (WEEK_DIR / next_key / "index.html").exists() else ""

    prev_html = (
        f'<a class="top-week-link prev" href="{html.escape(prev_link)}">‹ Vecka {prev_start.isocalendar().week}</a>'
        if prev_link
        else '<span></span>'
    )
    next_html = (
        f'<a class="top-week-link next" href="{html.escape(next_link)}">Vecka {next_start.isocalendar().week} ›</a>'
        if next_link
        else '<span></span>'
    )

    updated = updated_label(page)
    meta_parts = []
    if updated:
        meta_parts.append(f"<span>{html.escape(updated)}</span>")
    meta_parts.append('<a href="/träning/malbild-2027/">Målbild 2027 →</a>')
    meta_html = '<span class="top-meta-sep">·</span>'.join(meta_parts)

    plan_days = {
        str(day.get("date")): day
        for day in plan.get("days") or []
        if day.get("date")
    }
    today_key = today.isoformat()
    day = plan_days.get(today_key)
    if not day:
        raise RuntimeError(f"Crisp top: dagens planrad saknas för {today_key}")

    activity_dates = {
        str(activity.get("start_date_local") or activity.get("start_date") or "")[:10]
        for activity in activities.get("activities") or []
    }
    title, today_meta = split_session(day)
    status = status_label(day, has_completed_activity=today_key in activity_dates)
    reason = clean_reason(str(day.get("reason") or ""))
    override_note = clean_reason(str((day.get("manual_override") or {}).get("note") or ""))

    today_details_parts = []
    if reason:
        today_details_parts.append(f"<p>{html.escape(reason)}</p>")
    if override_note and override_note != reason:
        today_details_parts.append(f"<p>{html.escape(override_note)}</p>")
    today_details = ""
    if today_details_parts:
        today_details = (
            '<details class="top-details"><summary>Plan och motivering</summary>'
            '<div class="top-details-body">'
            + "".join(today_details_parts)
            + "</div></details>"
        )

    next_prefix, next_value = next_day_copy(plan, today)
    next_html_row = ""
    if next_prefix and next_value:
        next_html_row = (
            f'<div class="top-next">{html.escape(next_prefix)} · '
            f'<strong>{html.escape(next_value)}</strong></div>'
        )

    focus = focus_title(meta)
    micro_index = meta.get("microcycle_index")
    micro_total = meta.get("microcycle_total")
    focus_meta_bits = [block_label(meta)]
    if micro_index and micro_total:
        focus_meta_bits.append(f"mikrocykel {micro_index} av {micro_total}")
    focus_meta_text = " · ".join(focus_meta_bits)
    details_body = focus_details(meta, strategy)
    focus_details_html = ""
    if details_body:
        focus_details_html = (
            '<details class="top-details"><summary>Planidé</summary>'
            f'<div class="top-details-body">{details_body}</div></details>'
        )

    today_meta_html = (
        f'<div class="top-today-meta">{html.escape(today_meta)}</div>'
        if today_meta
        else ""
    )

    return (
        '<section class="top-overview" aria-label="Veckoöversikt">'
        '<nav class="top-week-nav" aria-label="Veckonavigering">'
        + prev_html
        + '<div class="top-week-current">'
        f'<strong>Vecka {week}</strong><span>{html.escape(period)}</span>'
        '</div>'
        + next_html
        + '</nav>'
        f'<div class="top-meta">{meta_html}</div>'
        '<section class="top-today" aria-label="Idag">'
        '<div class="top-today-kicker">'
        f'<span class="top-kicker">Idag · {WEEKDAYS[today.weekday()]} {today.day} {MONTH_SHORT[today.month]}</span>'
        f'<span class="top-status">{html.escape(status)}</span>'
        '</div>'
        '<div class="top-today-title">'
        + today_icon(day, registry)
        + f'<span>{html.escape(title)}</span></div>'
        + today_meta_html
        + next_html_row
        + today_details
        + '</section>'
        '<section class="top-week-focus" aria-label="Veckofokus">'
        '<span class="top-kicker">Veckofokus</span>'
        f'<strong class="top-focus-title">{html.escape(focus)}</strong>'
        f'<div class="top-focus-meta">{html.escape(focus_meta_text)}</div>'
        + focus_details_html
        + '</section>'
        '</section>'
    )


def add_css(page: str) -> str:
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Crisp top: </style> saknas.")
    return page.replace("</style>", CSS + "\n</style>", 1)


def apply_top_overview(
    page: str,
    plan: dict,
    strategy: dict,
    activities: dict,
    registry: dict,
    *,
    today: date,
) -> str:
    if 'class="top-overview"' in page:
        return add_css(page)

    header_start = page.find("<header>")
    week_start = page.find(CURRENT_WEEK_HEADING)
    if header_start < 0 or week_start < 0 or week_start <= header_start:
        raise RuntimeError("Crisp top: kunde inte avgränsa nuvarande toppregion.")

    top_region = page[header_start:week_start]
    week_region = page[week_start:]
    verify_floating_feedback_can_be_dropped(top_region, week_region)

    replacement = build_top(
        page,
        plan,
        strategy,
        activities,
        registry,
        today=today,
    )
    rendered = page[:header_start] + replacement + "\n\n" + page[week_start:]
    return add_css(rendered)


def validate_page(page: str) -> None:
    required = (
        CSS_MARKER,
        'class="top-overview"',
        'class="top-week-nav"',
        'class="top-today"',
        'class="top-week-focus"',
        CURRENT_WEEK_HEADING,
        ">Plan och motivering</summary>",
        ">Planidé</summary>",
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError(f"Crisp top: saknar obligatoriska element: {missing!r}")

    current_pos = page.find(CURRENT_WEEK_HEADING)
    prefix = page[:current_pos]
    forbidden = (
        "<header>",
        'class="week-nav"',
        'class="training-brain"',
        'class="hero week-focus-card"',
        'class="goal-page-link"',
        'data-training-input',
    )
    present = [token for token in forbidden if token in prefix]
    if present:
        raise RuntimeError(f"Crisp top: gamla parallella topplager finns kvar: {present!r}")

    if page.count('class="top-overview"') != 1:
        raise RuntimeError("Crisp top: top-overview måste finnas exakt en gång.")


def main() -> int:
    plan = load_json(PLAN_FILE, {"days": [], "meta": {}})
    strategy = load_json(STRATEGY_FILE, {})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    registry = load_json(ICON_FILE, {"icons": {}}).get("icons") or {}
    timezone = str((plan.get("meta") or {}).get("timezone") or "Europe/Stockholm")
    today = datetime.now(ZoneInfo(timezone)).date()

    page = INDEX_FILE.read_text(encoding="utf-8")
    rendered = apply_top_overview(
        page,
        plan,
        strategy,
        activities,
        registry,
        today=today,
    )
    validate_page(rendered)
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    print("Crisp top OK: orientering, Idag och veckofokus använder en gemensam topphierarki.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
