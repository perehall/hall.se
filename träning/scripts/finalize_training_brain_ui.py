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

CSS_MARKER = "/* training-brain-v2 */"
SECTION_START = "<!-- training-brain-v1:start -->"
SECTION_END = "<!-- training-brain-v1:end -->"
CSS = r'''
/* training-brain-v2 */
.training-brain{margin:0 0 18px}.brain-today{background:#fff;border:1px solid #bfdbfe;border-radius:20px;padding:17px 18px;box-shadow:var(--shadow)}.brain-kicker{font-size:.69rem;font-weight:900;letter-spacing:.09em;text-transform:uppercase;color:#1d4ed8;margin-bottom:6px}.brain-headline{font-size:1.28rem;font-weight:850;line-height:1.25;letter-spacing:-.015em}.brain-role{display:inline-block;margin-top:9px;padding:4px 8px;border-radius:999px;background:#e2e8f0;color:#334155;font-size:.68rem;font-weight:800}.brain-weather{margin-top:12px;padding:10px 12px;border:1px solid #bae6fd;border-radius:13px;background:#f0f9ff}.brain-weather-label{font-size:.65rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#0369a1;margin-bottom:3px}.brain-weather strong{display:block;font-size:.9rem;line-height:1.35}.brain-weather-note{margin-top:4px;color:#475569;font-size:.8rem;line-height:1.4}.brain-extra{margin-top:12px;padding:10px 12px;border:1px solid #d1d5db;border-radius:13px;background:#f8fafc}.brain-extra-label{font-size:.65rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#475569;margin-bottom:3px}.brain-extra strong{display:block;font-size:.9rem;line-height:1.35}.brain-extra-note{margin-top:3px;color:#64748b;font-size:.78rem;line-height:1.35}.brain-why{margin-top:8px;color:#334155;font-size:.88rem;line-height:1.43}.brain-next{margin-top:14px;padding-top:13px;border-top:1px solid #dbeafe}.brain-next-label{font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em;color:#64748b;margin-bottom:5px}.brain-next strong{display:block;font-size:.98rem;line-height:1.35}.brain-note{margin-top:5px;color:#475569;font-size:.84rem;line-height:1.42}.week-focus-mesocycle-meta{margin-top:9px;color:#94a3b8;font-size:.74rem;font-weight:750;line-height:1.35}.week-focus-mesocycle-idea{margin-top:8px!important;padding-top:8px;border-top:1px solid rgba(148,163,184,.22)}.week-focus-mesocycle-idea strong{color:#fff}
@media (max-width:620px){.brain-today{padding:15px}.brain-headline{font-size:1.16rem}.brain-weather{padding:9px 10px}.week-focus-mesocycle-meta{font-size:.7rem}}
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
    role = f'<span class="brain-role">{html.escape(today["role"])}</span>' if today.get("role") else ""
    today_text = today_date.isoformat() if hasattr(today_date, "isoformat") else str(today_date)
    separate_block = _separate_activity_block(activities, today_text)
    weather_block = ""
    if advice:
        weather_block = (
            '<div class="brain-weather" data-weather-advice="true">'
            '<div class="brain-weather-label">Väder-heads-up · '
            + html.escape(advice["title"])
            + '</div><strong>'
            + html.escape(advice["recommendation"])
            + '</strong><div class="brain-weather-note">'
            + html.escape(advice["note"])
            + '</div></div>'
        )
    decision_heading = html.escape(decision["headline"])
    if decision.get("label"):
        decision_heading = html.escape(decision["label"] + " · ") + decision_heading

    return f'''{SECTION_START}
<section class="training-brain" aria-label="Träningsbeslut">
  <div class="brain-today">
    <div class="brain-kicker">Idag · {html.escape(today["status"])}</div>
    <div class="brain-headline">{html.escape(today["headline"])}</div>
    {role}
    {separate_block}
    {weather_block}
    <div class="brain-why"><strong>Varför:</strong> {html.escape(today["why"])}</div>
    <div class="brain-next">
      <div class="brain-next-label">Nästa beslut</div>
      <strong>{decision_heading}</strong>
      <div class="brain-note">{html.escape(decision["note"])}</div>
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

    meta = (
        f'{html.escape(mesocycle.get("title") or "Aktuell mesocykel")} · '
        f'{html.escape(mesocycle.get("state") or "")} · '
        f'utvärdering {html.escape(compact_date(mesocycle.get("evaluation_date")))}'
    )
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
        page = page.replace(close_marker, extra + close_marker, 1)
    return page


def apply_ui(page, section):
    page = re.sub(
        re.escape(SECTION_START) + r".*?" + re.escape(SECTION_END),
        "",
        page,
        flags=re.S,
    )
    page = re.sub(r'/\* training-brain-v1 \*/.*?(?=(?:/\*|</style>))', '', page, flags=re.S)
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
    required = [SECTION_START, "Idag ·", "Nästa beslut", "week-focus-mesocycle-meta", "Mesocykelhypotes:", CSS_MARKER]
    missing = [marker for marker in required if marker not in verify]
    if missing:
        raise RuntimeError(f"Träningshjärna: renderad sida saknar {missing!r}")
    forbidden = ["Aktuellt block ·", "Blockhypotes:", "Prioritering just nu:", "brain-tags"]
    leaked = [marker for marker in forbidden if marker in verify]
    if leaked:
        raise RuntimeError(f"Träningshjärna: redundant information kvar i normalvyn: {leaked!r}")
    print("Träningshjärna OK: Veckofokus visar mesocykel + mikrocykel; Idag och Nästa beslut navigerar i närtid.")


if __name__ == "__main__":
    main()
