#!/usr/bin/env python3
import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
WEATHER_FILE = ROOT / "data" / "weather.json"
INDEX_FILE = ROOT / "index.html"
SUMMARY_FILE = ROOT / "data" / "dashboard_summary.json"

SPORT_GROUPS = {
    "Run": "Löpning",
    "TrailRun": "Löpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "MountainBikeRide": "MTB/XC",
    "Ride": "Cykel",
    "VirtualRide": "Cykel",
    "WeightTraining": "Styrka",
}

WEATHER_SYMBOLS = {
    1: "Klart",
    2: "Mest klart",
    3: "Växlande molnighet",
    4: "Halvklart",
    5: "Molnigt",
    6: "Mulet",
    7: "Dimma",
    8: "Lätta regnskurar",
    9: "Regnskurar",
    10: "Kraftiga regnskurar",
    11: "Åska",
    12: "Lätta snöblandade skurar",
    13: "Snöblandade skurar",
    14: "Kraftiga snöblandade skurar",
    15: "Lätta snöbyar",
    16: "Snöbyar",
    17: "Kraftiga snöbyar",
    18: "Lätt regn",
    19: "Regn",
    20: "Kraftigt regn",
    21: "Åska",
    22: "Lätt snöblandat regn",
    23: "Snöblandat regn",
    24: "Kraftigt snöblandat regn",
    25: "Lätt snöfall",
    26: "Snöfall",
    27: "Kraftigt snöfall",
}


def activity_duration_s(activity):
    # Canonical dashboard duration: full recorded session time.
    # Use elapsed_time so dashboard totals match the duration shown on the
    # activity/day cards. Fall back to moving_time only when elapsed is absent.
    elapsed = activity.get("elapsed_time_s")
    if elapsed is not None and int(elapsed) >= 0:
        return int(elapsed)
    moving = activity.get("moving_time_s")
    return int(moving or 0)


def fmt_exact_duration(seconds):
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def fmt_decimal(value):
    return f"{float(value):.1f}".replace(".", ",")


def local_date(activity):
    value = activity.get("start_date_local") or ""
    return value[:10] if len(value) >= 10 else ""


def replace_between(text, start_marker, end_marker, replacement):
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"Dashboard marker saknas: {start_marker!r}")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"Dashboard marker saknas: {end_marker!r}")
    return text[:start] + replacement + text[end:]


def weather_icon_svg(symbol):
    if symbol is None:
        return ""
    try:
        code = int(symbol)
    except (TypeError, ValueError):
        return ""

    sun = (
        '<circle cx="12" cy="12" r="3.5" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
    )
    cloud = (
        '<path d="M6.7 18h10.1a3.7 3.7 0 0 0 .3-7.4A5.3 5.3 0 0 0 7 9.8 4.1 4.1 0 0 0 6.7 18Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    partly_cloudy = (
        '<circle cx="8" cy="8" r="2.8" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '<path d="M8 3V1.8M8 13v-1.2M3 8H1.8M12.2 8H11M4.5 4.5l-.9-.9M11.5 4.5l.9-.9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'
        '<path d="M7.2 19h10a3.6 3.6 0 0 0 .2-7.2 5 5 0 0 0-9.5-.7A4 4 0 0 0 7.2 19Z" fill="white" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    rain = cloud + '<path d="M8.5 20.2l-.7 1.3M12.5 20.2l-.7 1.3M16.5 20.2l-.7 1.3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
    snow = cloud + '<path d="M9 20v2M8 21h2M14 20v2M13 21h2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
    sleet = cloud + '<path d="M8.5 20.2l-.7 1.3M13 20v2M12 21h2M17 20.2l-.7 1.3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'
    thunder = cloud + '<path d="M13 18.7l-2 3.1h2l-1 2.2 3-3.7h-2l1-1.6" fill="currentColor"/>'
    fog = '<path d="M4 8h16M2.5 12h15M6 16h15M3 20h12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'

    if code == 1:
        body = sun
    elif code in (2, 3, 4):
        body = partly_cloudy
    elif code in (5, 6):
        body = cloud
    elif code == 7:
        body = fog
    elif code in (8, 9, 10, 18, 19, 20):
        body = rain
    elif code in (11, 21):
        body = thunder
    elif code in (12, 13, 14, 22, 23, 24):
        body = sleet
    elif code in (15, 16, 17, 25, 26, 27):
        body = snow
    else:
        body = cloud

    return (
        '<svg class="weather-icon" aria-hidden="true" viewBox="0 0 24 24" '
        'style="width:18px;height:18px;vertical-align:-4px;margin-right:5px;color:#475569;overflow:visible">'
        + body
        + '</svg>'
    )


def weather_html(date, forecast, weather_status):
    location = (forecast.get("location") or {}).get("name") or "Oxelösund"
    parts = []

    symbol = forecast.get("symbol_code")
    icon = weather_icon_svg(symbol)
    if symbol is not None:
        parts.append(WEATHER_SYMBOLS.get(int(symbol), f"Vädersymbol {int(symbol)}"))

    temp_min = forecast.get("temperature_min_c")
    temp_max = forecast.get("temperature_max_c")
    if temp_min is not None and temp_max is not None:
        if round(float(temp_min), 1) == round(float(temp_max), 1):
            parts.append(f"{fmt_decimal(temp_min)} °C")
        else:
            parts.append(f"{fmt_decimal(temp_min)}–{fmt_decimal(temp_max)} °C")

    precip = forecast.get("precip_probability_max_pct")
    if precip is not None:
        parts.append(f"nederbördsrisk max {int(round(float(precip)))} %")

    wind = forecast.get("wind_max_ms")
    if wind is not None:
        parts.append(f"vind max {fmt_decimal(wind)} m/s")

    if weather_status != "ok":
        parts.append("äldre väderdata")

    if not parts:
        return ""

    detail = " · ".join(parts)
    return (
        f'  <div class="next-weather" data-weather-date="{html.escape(date)}" '
        f'style="color:#475569;font-size:.82rem;margin-top:5px">'
        f'<strong>Väder · {html.escape(location)}</strong> · {icon}{html.escape(detail)}</div>\n'
    )


plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
weather = json.loads(WEATHER_FILE.read_text(encoding="utf-8")) if WEATHER_FILE.exists() else {}
page = INDEX_FILE.read_text(encoding="utf-8")

week_start = plan["meta"]["week_start"]
week_end = plan["meta"]["week_end"]
activities = state.get("activities", [])

ids = [int(a["id"]) for a in activities if a.get("id") is not None]
if len(ids) != len(set(ids)):
    raise RuntimeError("Dashboardvalidering: dubbla aktivitets-ID i activities.json")

week_activities = [
    a for a in activities
    if local_date(a) and week_start <= local_date(a) <= week_end
]

pass_count = len(week_activities)
training_days = len({local_date(a) for a in week_activities})
total_seconds = sum(activity_duration_s(a) for a in week_activities)

sport_seconds = {}
for activity in week_activities:
    group = SPORT_GROUPS.get(
        activity.get("sport_type"), activity.get("sport_type") or "Övrigt"
    )
    sport_seconds[group] = sport_seconds.get(group, 0) + activity_duration_s(activity)

# Independent arithmetic invariant: sport breakdown must equal weekly total.
if sum(sport_seconds.values()) != total_seconds:
    raise RuntimeError("Dashboardvalidering: grenfördelning summerar inte till total passtid")

summary = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "week_start": week_start,
    "week_end": week_end,
    "duration_definition": "elapsed_time_s; moving_time_s endast som fallback",
    "display_duration_format": "H:MM:SS eller M:SS utan avrundning",
    "pass_count": pass_count,
    "training_days": training_days,
    "session_time_s": total_seconds,
    "by_sport_s": dict(sorted(sport_seconds.items())),
    "activity_ids": [a.get("id") for a in week_activities],
}
SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

metrics_html = f'''<div class="metrics">
    <div class="metric"><strong>{pass_count}</strong><span>pass</span></div>
    <div class="metric"><strong>{fmt_exact_duration(total_seconds)}</strong><span>passtid</span></div>
    <div class="metric"><strong>{training_days}</strong><span>träningsdagar</span></div>
  </div>
  '''
page = replace_between(
    page,
    '<div class="metrics">',
    '<div class="dashboard-grid">',
    metrics_html,
)

sport_rows = []
for group, seconds in sorted(sport_seconds.items(), key=lambda item: item[1], reverse=True):
    pct = round(seconds / total_seconds * 100) if total_seconds else 0
    sport_rows.append(
        f'''<div class="sport-row">
  <div class="sport-head"><span>{html.escape(group)}</span><strong>{fmt_exact_duration(seconds)}</strong></div>
  <div class="sport-track"><div class="sport-fill" style="width:{pct}%"></div></div>
</div>'''
    )
sport_distribution = "".join(sport_rows) or '<div class="dashboard-empty">Ingen registrerad aktivitet denna vecka ännu.</div>'

sport_card = f'''<div class="dashboard-card">
      <div class="dashboard-title">Grenfördelning · passtid</div>
      {sport_distribution}
    </div>
    '''
page = replace_between(
    page,
    '<div class="dashboard-card">\n      <div class="dashboard-title">Grenfördelning',
    '<div class="dashboard-card">\n      <div class="dashboard-title">Plan → utfall',
    sport_card,
)

weather_by_date = weather.get("daily", {})
weather_status = weather.get("status", "unavailable")
for day in plan.get("days", []):
    date = day.get("date")
    forecast = weather_by_date.get(date)
    if not forecast:
        continue
    marker = f'data-weather-date="{date}"'
    if marker in page:
        continue
    session_line = f'  <div>{html.escape(day.get("session", ""))}</div>\n'
    forecast_html = weather_html(date, forecast, weather_status)
    if forecast_html and session_line in page:
        page = page.replace(session_line, session_line + forecast_html, 1)

footer_weather = (
    ' · Väderprognos: <a href="https://www.smhi.se/" target="_blank" rel="noopener" '
    'style="color:inherit">SMHI</a> · standardplats Oxelösund om inget annat anges.'
)
logout_marker = ' · <a href="/cdn-cgi/access/logout"'
if "standardplats Oxelösund om inget annat anges." not in page and logout_marker in page:
    page = page.replace(logout_marker, footer_weather + logout_marker, 1)

INDEX_FILE.write_text(page, encoding="utf-8")

# Fail closed: never publish if the rendered dashboard cannot be proven to
# contain the exact independently calculated aggregates.
rendered = INDEX_FILE.read_text(encoding="utf-8")
required = [
    f'<div class="metric"><strong>{pass_count}</strong><span>pass</span></div>',
    f'<div class="metric"><strong>{fmt_exact_duration(total_seconds)}</strong><span>passtid</span></div>',
    f'<div class="metric"><strong>{training_days}</strong><span>träningsdagar</span></div>',
    '<div class="dashboard-title">Grenfördelning · passtid</div>',
    'standardplats Oxelösund om inget annat anges.',
]
if any(
    f'data-weather-date="{date}"' in rendered
    and isinstance(forecast, dict)
    and forecast.get("symbol_code") is not None
    for date, forecast in weather_by_date.items()
):
    required.append('class="weather-icon"')
for group, seconds in sport_seconds.items():
    required.append(
        f'<div class="sport-head"><span>{html.escape(group)}</span><strong>{fmt_exact_duration(seconds)}</strong></div>'
    )

missing = [snippet for snippet in required if snippet not in rendered]
if missing:
    raise RuntimeError("Dashboardvalidering misslyckades; publicering stoppas: " + repr(missing))

print(
    f"Dashboard OK: {pass_count} pass, {fmt_exact_duration(total_seconds)} passtid, "
    f"{training_days} träningsdagar."
)
