#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from coach_rules import activity_local_date, planning_window
from strategy_contracts import validate_training_strategy
from training_brain import resolve_mesocycle, resolve_next_decision, resolve_today, resolve_weather_advice

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"
WEATHER_FILE = ROOT / "data" / "weather.json"
SETTINGS_FILE = ROOT / "data" / "settings.json"

CSS_MARKER = "/* training-brain-v3 */"
SECTION_START = "<!-- training-brain-v1:start -->"
SECTION_END = "<!-- training-brain-v1:end -->"
CSS = r'''
/* training-brain-v3 */
.training-brain{margin:0 0 18px}.brain-today{background:#fff;border:1px solid #bfdbfe;border-radius:20px;padding:17px 18px;box-shadow:var(--shadow)}
.brain-topline{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:7px}.brain-kicker{font-size:.76rem;font-weight:700;color:#334155}.brain-status{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;background:#fef3c7;color:#92400e;font-size:.68rem;font-weight:700;white-space:nowrap}
.brain-headline{font-size:1.12rem;font-weight:700;line-height:1.3;letter-spacing:-.012em}.brain-subline{margin-top:3px;color:#64748b;font-size:.84rem;line-height:1.4}
.brain-weather{margin-top:12px;padding:10px 12px;border:1px solid #bae6fd;border-radius:13px;background:#f0f9ff}.brain-weather-label{font-size:.7rem;font-weight:700;color:#0369a1;margin-bottom:3px}.brain-weather strong{display:block;font-size:.88rem;line-height:1.35}.brain-weather-note{margin-top:4px;color:#475569;font-size:.8rem;line-height:1.4}
.brain-extra{margin-top:12px;padding:10px 12px;border:1px solid #d1d5db;border-radius:13px;background:#f8fafc}.brain-extra-label{font-size:.7rem;font-weight:700;color:#475569;margin-bottom:3px}.brain-extra strong{display:block;font-size:.88rem;line-height:1.35}.brain-extra-note{margin-top:3px;color:#64748b;font-size:.78rem;line-height:1.35}
.brain-why-details{margin-top:9px}.brain-why-details>summary{cursor:pointer;list-style:none;color:#64748b;font-size:.78rem;font-weight:600}.brain-why-details>summary::-webkit-details-marker{display:none}.brain-why-details>summary:after{content:" +"}.brain-why-details[open]>summary:after{content:" −"}.brain-why{margin-top:7px;color:#475569;font-size:.86rem;line-height:1.45}
.brain-next{margin-top:14px;padding-top:12px;border-top:1px solid #e2e8f0}.brain-next-label{font-size:.76rem;font-weight:600;color:#64748b;margin-bottom:5px}.brain-next strong{display:block;font-size:.96rem;font-weight:700;line-height:1.35}.brain-note{margin-top:4px;color:#64748b;font-size:.82rem;line-height:1.4}
.week-focus-mesocycle-meta{margin-top:6px;color:#94a3b8;font-size:.76rem;font-weight:500;line-height:1.4}.week-focus-mesocycle-idea{margin-top:8px!important;padding-top:8px;border-top:1px solid rgba(148,163,184,.22)}.week-focus-mesocycle-idea strong{color:#fff}
@media (max-width:620px){.brain-today{padding:15px}.brain-headline{font-size:1.05rem}.brain-subline{font-size:.8rem}.brain-weather{padding:9px 10px}.week-focus-mesocycle-meta{font-size:.72rem}}
'''


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def compact_date(value):
    if not value:
        return "ej satt"
    try:
        year, month, day = [int(part) for part in value.split("-")]
    except (TypeError, ValueError):
        return value
    return f"{day}/{month}"


def session_display_parts(session):
    tokens = [token.strip() for token in str(session or "").split(" · ") if token.strip()]
    if not tokens:
        return str(session or ""), ""
    first = tokens[0]
    lower_first = first.lower()

    if lower_first.startswith("simning"):
        distance = next((t for t in tokens if re.fullmatch(r"\d[\d ]*\s*m", t)), "")
        quality = next((t for t in tokens[1:] if any(x in t.lower() for x in ("aerob", "teknik", "tröskel")) and not t.lower().startswith("alternativ:")), "")
        duration = next((t for t in tokens if re.search(r"\b(?:ca\s*)?\d+\s*min\b", t)), "")
        title = " ".join(x for x in ("Simning", distance, quality) if x)
        alt_index = next((i for i,t in enumerate(tokens) if t.lower().startswith("alternativ:")), None)
        meta = [duration] if duration else []
        if alt_index is not None:
            alt = tokens[alt_index:]
            first_alt = alt[0].split(":",1)[1].strip()
            rest = " ".join(alt[1:]).strip()
            text = f"alternativ: {first_alt}"
            if rest:
                text += f", {rest}"
            meta.append(text)
        return title or first, " · ".join(meta)

    if lower_first.startswith(("mtb", "cykel")):
        duration = next((t for t in tokens[1:] if re.search(r"\b\d+\s*min\b", t)), "")
        title = " ".join(x for x in (first, duration) if x)
        rest = [t for t in tokens[1:] if t != duration]
        return title, " · ".join(rest)

    if lower_first.startswith(("löpning", "trail")) and len(tokens) >= 2:
        return f"{first} · {tokens[1]}", " · ".join(tokens[2:])

    if lower_first.startswith("styrka"):
        duration = next((t for t in tokens[1:] if re.search(r"\b\d+\s*min\b", t)), "")
        title = " ".join(x for x in (first, duration) if x)
        return title, " · ".join(t for t in tokens[1:] if t != duration)

    return first, " · ".join(tokens[1:])


def short_status(day, resolved_status):
    if day and day.get("alternative_sports"):
        return "Alternativ finns"
    labels = {
        "GENOMFÖRT": "Genomfört",
        "PLANERAT": "Planerat",
        "PRELIMINÄRT": "Preliminärt",
        "VILLKORAT": "Villkorat",
        "ÖPPET": "Öppet",
    }
    return labels.get(str(resolved_status or ""), str(resolved_status or "").capitalize())


def focus_title(mesocycle):
    protected = [str(x).lower() for x in mesocycle.get("protected_stimuli") or []]
    if any("löptröskel" in x for x in protected) and any("back" in x for x in protected):
        return "Löpning prioriteras denna vecka"
    title = re.sub(r"^Mesocykel\s*·\s*", "", str(mesocycle.get("title") or ""), flags=re.I).strip()
    return title[:1].upper() + title[1:] if title else "Veckans utvecklingsfokus"


def focus_meta(mesocycle):
    title = re.sub(r"^Mesocykel\s*·\s*", "", str(mesocycle.get("title") or ""), flags=re.I).strip()
    if title.lower().startswith("löptröskel"):
        title = "Löptröskel" + title[len("löptröskel"):]
    return " · ".join(x for x in (title, str(mesocycle.get("state") or "")) if x)


def next_note(headline, original_note):
    _, meta = session_display_parts(headline)
    if meta:
        return "Grundplan: " + meta.rstrip(".") + "."
    return original_note


def _fmt_activity_distance(activity):
    meters = float(activity.get("distance_m") or 0)
    if meters <= 0:
        return ""
    if activity.get("sport_type") == "Swim":
        return f"{round(meters):,} m".replace(",", " ")
    return f"{meters / 1000:.2f} km".replace(".", ",")


def _separate_activity_block(activities, today_text):
    rows = [
        activity
        for activity in activities
        if activity_local_date(activity) == today_text
        and activity.get("plan_relation") == "separate"
    ]
    if not rows:
        return ""

    bits = []
    for activity in rows:
        label = activity.get("display_label") or activity.get("sport_type") or "Aktivitet"
        distance = _fmt_activity_distance(activity)
        bits.append(" · ".join(part for part in (str(label), distance) if part))

    return (
        '<div class="brain-extra" data-separate-workout="true">'
        '<div class="brain-extra-label">Spontant pass · registrerat separat</div>'
        f'<strong>{html.escape(" + ".join(bits))}</strong>'
        '<div class="brain-extra-note">Påverkar belastningsbedömningen, men markerar inte dagens planerade pass som genomfört.</div>'
        '</div>'
    )


def render_section(plan, activities_state, strategy, today_date, weather=None, settings=None):
    activities = activities_state.get("activities") or []
    today = resolve_today(plan, activities, strategy, today_date)
    decision = resolve_next_decision(plan, activities, strategy, today_date)
    advice = resolve_weather_advice(plan, activities, weather or {}, settings or {}, today_date)
    today_text = today_date.isoformat() if hasattr(today_date, "isoformat") else str(today_date)
    day = next((item for item in plan.get("days") or [] if item.get("date") == today_text), None)
    separate_block = _separate_activity_block(activities, today_text)
    weather_block = ""
    if advice:
        weather_block = (
            '<div class="brain-weather" data-weather-advice="true">'
            '<div class="brain-weather-label">Väder</div><strong>'
            + html.escape(advice["recommendation"])
            + '</strong><div class="brain-weather-note">'
            + html.escape(advice["note"])
            + '</div></div>'
        )

    today_title, today_meta = session_display_parts(today["headline"])
    decision_title, _ = session_display_parts(decision["headline"])
    decision_heading = decision_title
    if decision.get("label"):
        decision_heading = decision["label"] + " · " + decision_heading
    status = short_status(day, today["status"])

    return f'''{SECTION_START}
<section class="training-brain" aria-label="Träningsbeslut">
  <div class="brain-today">
    <div class="brain-topline"><span class="brain-kicker">Idag</span><span class="brain-status">{html.escape(status)}</span></div>
    <div class="brain-headline">{html.escape(today_title)}</div>
    {f'<div class="brain-subline">{html.escape(today_meta)}</div>' if today_meta else ''}
    {separate_block}
    {weather_block}
    <details class="brain-why-details"><summary>Motivering</summary><div class="brain-why">{html.escape(today["why"])}</div></details>
    <div class="brain-next">
      <div class="brain-next-label">Nästa</div>
      <strong>{html.escape(decision_heading)}</strong>
      <div class="brain-note">{html.escape(next_note(decision["headline"], decision["note"]))}</div>
    </div>
  </div>
</section>
{SECTION_END}'''


def decorate_focus_card(page, mesocycle):
    marker = '<details class="week-focus-details">'
    if marker not in page:
        raise RuntimeError("Träningshjärna: Veckofokus-rutan saknas")
    if 'class="week-focus-mesocycle-meta"' in page:
        return page

    meta = html.escape(focus_meta(mesocycle))
    title_match = re.search(r'<h2(?: class="week-focus-title")?>.*?</h2>', page, flags=re.S)
    if not title_match:
        raise RuntimeError("Träningshjärna: veckofokus-rubrik saknas")
    page = page[:title_match.start()] + f'<h2 class="week-focus-title">{html.escape(focus_title(mesocycle))}</h2>' + page[title_match.end():]
    page = page.replace(
        marker,
        f'<div class="week-focus-mesocycle-meta">{meta}</div>' + marker,
        1,
    )

    hypothesis = (mesocycle.get("hypothesis") or "").strip()
    if hypothesis:
        close_marker = '</details></div>'
        if close_marker not in page:
            raise RuntimeError("Träningshjärna: kunde inte hitta slutet på Veckofokus-rutan")
        extra = (
            f'<p class="week-focus-mesocycle-idea"><strong>Mesocykelhypotes:</strong> '
            f'{html.escape(hypothesis)}</p>'
        )
        contract = mesocycle.get("contract") or {}
        role_parts = []
        for label, key in (
            ("Primärt", "primary"),
            ("Sekundärt", "secondary"),
            ("Underhåll", "maintenance"),
            ("Skyddad kapacitet", "protected_capacity"),
        ):
            values = contract.get(key) or []
            if values:
                role_parts.append(f"<strong>{label}:</strong> {html.escape(', '.join(values))}")
        if role_parts:
            extra += '<p class="week-focus-mesocycle-idea">' + " · ".join(role_parts) + "</p>"
        page = page.replace(close_marker, extra + close_marker, 1)
    return page


def apply_ui(page, section):
    page = re.sub(
        re.escape(SECTION_START) + r".*?" + re.escape(SECTION_END),
        "",
        page,
        flags=re.S,
    )
    page = re.sub(r'/\* training-brain-v[12] \*/.*?(?=(?:/\*|</style>))', '', page, flags=re.S)
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Träningshjärna: index.html saknar </style>")
        page = page.replace("</style>", CSS + "\n</style>", 1)
    dashboard_marker = '<section class="dashboard"'
    if dashboard_marker not in page:
        raise RuntimeError("Träningshjärna: dashboard-markör saknas")
    return page.replace(dashboard_marker, section + "\n" + dashboard_marker, 1)


def main():
    plan = load_json(PLAN_FILE)
    upcoming = load_json(UPCOMING_FILE) if UPCOMING_FILE.exists() else {}
    decision_plan = planning_window(plan, upcoming)
    activities = load_json(ACTIVITIES_FILE)
    strategy = load_json(STRATEGY_FILE)
    weather = load_json(WEATHER_FILE) if WEATHER_FILE.exists() else {}
    settings = load_json(SETTINGS_FILE) if SETTINGS_FILE.exists() else {}
    validate_training_strategy(strategy)
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today = datetime.now(ZoneInfo(timezone_name)).date()
    page = INDEX_FILE.read_text(encoding="utf-8")
    section = render_section(decision_plan, activities, strategy, today, weather=weather, settings=settings)
    mesocycle = resolve_mesocycle(strategy, today)
    rendered = decorate_focus_card(apply_ui(page, section), mesocycle)
    INDEX_FILE.write_text(rendered, encoding="utf-8")

    verify = INDEX_FILE.read_text(encoding="utf-8")
    required = [SECTION_START, 'class="brain-kicker">Idag</span>', "Nästa", "Motivering", "week-focus-mesocycle-meta", "Mesocykelhypotes:", CSS_MARKER]
    missing = [marker for marker in required if marker not in verify]
    if missing:
        raise RuntimeError(f"Träningshjärna: renderad sida saknar {missing!r}")
    forbidden = ["Aktuellt block ·", "Blockhypotes:", "Prioritering just nu:", "brain-tags"]
    leaked = [marker for marker in forbidden if marker in verify]
    if leaked:
        raise RuntimeError(f"Träningshjärna: redundant information kvar i normalvyn: {leaked!r}")
    print("Träningshjärna OK: ren veckofokus-, idag- och nästa-hierarki med träningsdetaljer på sekundär nivå.")


if __name__ == "__main__":
    main()
