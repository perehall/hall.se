#!/usr/bin/env python3
import html
import json
import re
from datetime import date, timedelta
from pathlib import Path

from finalize_signal_ui import strength_sheet

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CURRENT_PLAN_FILE = DATA_DIR / "plan.json"
UPCOMING_FILE = DATA_DIR / "upcoming_week.json"
MANIFEST_FILE = DATA_DIR / "weeks" / "index.json"
PAGES_DIR = ROOT / "vecka"
CURRENT_INDEX = ROOT / "index.html"

NAV_CSS_MARKER = "/* weekly-history-v1 */"
NAV_CSS = r'''
/* weekly-history-v1 */
.week-nav{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;margin:-4px 0 16px;padding:9px 10px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;box-shadow:0 6px 18px rgba(15,23,42,.04)}
.week-nav a{color:#1d4ed8;text-decoration:none;font-size:.82rem;font-weight:800}.week-nav .next{text-align:right}.week-nav-center{text-align:center;line-height:1.15}.week-nav-center strong{display:block;font-size:.86rem}.week-nav-center span{display:block;margin-top:3px;color:#64748b;font-size:.59rem;font-weight:900;letter-spacing:.1em}.week-nav-spacer{display:block}
@media (max-width:520px){.week-nav{grid-template-columns:1fr auto 1fr;padding:8px}.week-nav a{font-size:.75rem}.week-nav-center strong{font-size:.8rem}}
'''

PREVIEW_CSS_MARKER = "/* upcoming-week-preview-v3 */"
PREVIEW_CSS = r'''
/* upcoming-week-preview-v3 */
.preview-metrics{grid-template-columns:repeat(4,1fr)}
.preview-focus{color:#334155;font-size:.94rem;line-height:1.5}
.preview-note{margin-top:8px;color:#64748b;font-size:.82rem}
.swim-equipment-line{margin:6px 0 0;color:#475569;font-size:.82rem}.swim-equipment-line strong{color:#334155}
.reference-tools{display:flex;justify-content:flex-start;margin:12px 0 8px}.reference-chip{appearance:none;border:1px solid #cbd5e1;background:#fff;color:#334155;border-radius:999px;padding:9px 13px;font:inherit;font-size:.82rem;font-weight:800;cursor:pointer;box-shadow:0 3px 10px rgba(15,23,42,.04)}
.strength-window{position:fixed;inset:auto;width:min(520px,calc(100vw - 32px));max-height:calc(100vh - 32px);left:50%;top:50%;transform:translate(-50%,-50%);margin:0;border:1px solid #e2e8f0;border-radius:18px;padding:0;background:#fff;color:#0f172a;box-shadow:0 24px 70px rgba(15,23,42,.28);overflow:auto}.strength-window::backdrop{background:rgba(15,23,42,.38)}.sheet-inner{padding:0 18px 18px}.sheet-head{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0 -18px 8px;padding:14px 18px 10px;background:#fff;border-bottom:1px solid #f1f5f9;cursor:move;touch-action:none;user-select:none}.sheet-head h2{font-size:1.1rem;margin:0}.sheet-close{appearance:none;border:0;background:#f1f5f9;color:#334155;border-radius:999px;padding:7px 10px;font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}.sheet-note{margin:0 0 10px;color:#64748b;font-size:.8rem}.strength-list{margin:0;padding:0;list-style:none;display:grid;gap:0}.strength-list li{padding:10px 0;border-top:1px solid #e2e8f0;font-size:.9rem;line-height:1.38}.strength-list li:first-child{border-top:0}
@media (max-width:620px){.preview-metrics{grid-template-columns:repeat(2,1fr)}.reference-tools{margin-top:10px}.strength-window{width:min(100% - 16px,720px);max-height:min(78vh,680px);left:50%!important;top:auto!important;bottom:0;transform:translateX(-50%)!important;border:0;border-radius:22px 22px 0 0}.sheet-inner{padding:0 18px calc(20px + env(safe-area-inset-bottom))}.sheet-head{cursor:default;touch-action:auto}}
'''

STATUS_UI = {
    "fixed": ("fixed", "FAST"),
    "planned": ("planned", "PLANERAT"),
    "preliminary": ("conditional", "PRELIMINÄRT"),
    "open": ("open", "ÖPPET"),
}

EQUIPMENT_LABELS = {
    "paddles": "paddlar",
    "paddlar": "paddlar",
    "pull_buoy": "dolme",
    "dolme": "dolme",
    "fins": "fenor",
    "fenor": "fenor",
    "snorkel": "snorkel",
    "kickboard": "platta",
    "platta": "platta",
}


def load_json(path, fallback=None):
    if not path.exists():
        return {} if fallback is None else fallback
    return json.loads(path.read_text(encoding="utf-8"))


def week_key_from_meta(meta):
    start = date.fromisoformat(meta["week_start"])
    iso = start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_number(key):
    return int(key.split("-W", 1)[1])


def archive_url(key):
    return f"/träning/vecka/{key}/"


def add_css(style_text):
    if NAV_CSS_MARKER not in style_text:
        style_text += "\n" + NAV_CSS
    if PREVIEW_CSS_MARKER not in style_text:
        style_text += "\n" + PREVIEW_CSS
    return style_text


def fmt_equipment(value):
    if value is None:
        return "ej registrerat"
    if value in ("none", "inga"):
        return "inga"
    if isinstance(value, str):
        if value in ("tbd", "to_be_determined"):
            return "fastställs med exakt pass"
        return EQUIPMENT_LABELS.get(value, value)
    if isinstance(value, list):
        if not value:
            return "inga"
        return " + ".join(EQUIPMENT_LABELS.get(str(item), str(item)) for item in value)
    raise RuntimeError(f"Kommande vecka: ogiltigt hjälpmedelsvärde {value!r}")


def swim_equipment_html(day):
    if day.get("sport") != "swim":
        return ""
    config = day.get("swim_equipment")
    if not isinstance(config, dict) or "planned" not in config:
        raise RuntimeError(
            f"Kommande vecka: simpass {day.get('date')} saknar swim_equipment.planned"
        )
    return (
        '<div class="swim-equipment-line"><strong>Hjälpmedel:</strong> '
        + html.escape(fmt_equipment(config.get("planned")))
        + '</div>'
    )


def previous_archive_key(current_key):
    manifest = load_json(MANIFEST_FILE, {})
    keys = sorted(record.get("key") for record in manifest.get("weeks", []) if record.get("key"))
    if current_key not in keys:
        return None
    index = keys.index(current_key)
    return keys[index - 1] if index > 0 else None


def current_nav(current_key, upcoming_key):
    previous_key = previous_archive_key(current_key)
    previous = (
        f'<a class="prev" href="{archive_url(previous_key)}">← Vecka {week_number(previous_key)}</a>'
        if previous_key
        else '<span class="week-nav-spacer"></span>'
    )
    return (
        '<nav class="week-nav" aria-label="Veckonavigering">'
        + previous
        + f'<div class="week-nav-center"><strong>Vecka {week_number(current_key)}</strong><span>AKTUELL</span></div>'
        + f'<a class="next" href="{archive_url(upcoming_key)}">Vecka {week_number(upcoming_key)} →</a>'
        + '</nav>'
    )


def preview_nav(current_key, upcoming_key):
    return (
        '<nav class="week-nav" aria-label="Veckonavigering">'
        f'<a class="prev" href="/träning/">← Vecka {week_number(current_key)}</a>'
        f'<div class="week-nav-center"><strong>Vecka {week_number(upcoming_key)}</strong><span>PRELIMINÄR</span></div>'
        '<span class="week-nav-spacer"></span>'
        '</nav>'
    )


def update_current_page(current_key, upcoming_key):
    page = CURRENT_INDEX.read_text(encoding="utf-8")
    nav = current_nav(current_key, upcoming_key)
    pattern = re.compile(r'<nav class="week-nav"[^>]*>.*?</nav>', re.S)
    if pattern.search(page):
        page = pattern.sub(nav, page, count=1)
    else:
        end = page.find("</header>")
        if end < 0:
            raise RuntimeError("Kommande vecka: aktuell sida saknar </header>")
        end += len("</header>")
        page = page[:end] + "\n" + nav + page[end:]
    CURRENT_INDEX.write_text(page, encoding="utf-8")


def render_preview(upcoming, current_key, upcoming_key):
    current_page = CURRENT_INDEX.read_text(encoding="utf-8")
    style_match = re.search(r"<style>(.*?)</style>", current_page, re.S)
    if not style_match:
        raise RuntimeError("Kommande vecka: kunde inte återanvända sidans CSS")
    styles = add_css(style_match.group(1))

    meta = upcoming["meta"]
    days = upcoming.get("days", [])
    counts = {"fixed": 0, "planned": 0, "preliminary": 0, "open": 0}
    cards = []
    used_statuses = set()
    for day in days:
        planning_status = day.get("planning_status") or day.get("status") or "open"
        if planning_status not in STATUS_UI:
            raise RuntimeError(f"Kommande vecka: okänd planstatus {planning_status!r}")
        used_statuses.add(planning_status)
        counts[planning_status] += 1
        css_class, label = STATUS_UI[planning_status]
        equipment = swim_equipment_html(day)
        cards.append(
            f'''<div class="day" id="dag-{html.escape(day["date"])}">
  <div class="daytop">
    <div><div class="dow">{html.escape(day["label"])}</div><div class="date">{html.escape(day["date"])}</div></div>
    <div class="badge {css_class}">{label}</div>
  </div>
  <div class="session">{html.escape(day["session"])}</div>
  {equipment}
  <div class="reason">{html.escape(day.get("reason", ""))}</div>
</div>'''
        )

    strength_reference = strength_sheet(upcoming.get("strength_template", []))

    summary = html.escape(meta.get("preview_summary", ""))
    dashboard = f'''<section class="dashboard" aria-label="Planöversikt nästa vecka">
  <div class="metrics preview-metrics">
    <div class="metric"><strong>{counts["fixed"]}</strong><span>fast</span></div>
    <div class="metric"><strong>{counts["planned"]}</strong><span>planerat</span></div>
    <div class="metric"><strong>{counts["preliminary"]}</strong><span>preliminärt</span></div>
    <div class="metric"><strong>{counts["open"]}</strong><span>öppet</span></div>
  </div>
  <div class="dashboard-card">
    <div class="dashboard-title">Veckans fokus</div>
    <div class="preview-focus">{summary}</div>
    <div class="preview-note">Preliminär plan: detaljer och belastning ändras när faktisk träning och återhämtning från föregående dagar är kända.</div>
  </div>
</section>'''

    page = f'''<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0f172a">
<title>Träningsplan · vecka {week_number(upcoming_key)} · preliminär</title>
<style>{styles}</style>
</head>
<body><div class="wrap">
<header><div class="eyebrow">ADAPTIV TRÄNINGSPLANERING</div><h1>Vecka {meta["week"]}</h1><div class="sub">{html.escape(meta["week_start"])} till {html.escape(meta["week_end"])} · preliminär plan</div></header>
{preview_nav(current_key, upcoming_key)}
<div class="hero"><h2>{html.escape(meta["title"])}</h2><p>{html.escape(meta["principle"])}</p></div>
{dashboard}
<h2 class="section">Preliminär vecka</h2>{''.join(cards)}
{strength_reference}
<footer>Preliminär framtidsplan. Faktisk belastning och återhämtning styr kommande justeringar. · <a href="/cdn-cgi/access/logout" style="color:inherit">Logga ut</a></footer>
</div></body></html>'''

    output_dir = PAGES_DIR / upcoming_key
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "index.html"
    output.write_text(page, encoding="utf-8")

    rendered = output.read_text(encoding="utf-8")
    required = [
        f"Vecka {week_number(upcoming_key)}",
        "PRELIMINÄR",
        "Veckans fokus",
        f'href="/träning/">← Vecka {week_number(current_key)}</a>',
    ]
    required.extend(STATUS_UI[status][1] for status in sorted(used_statuses))
    for day in days:
        required.append(f'id="dag-{day["date"]}"')
        if day.get("sport") == "swim":
            required.append("Hjälpmedel:")
    required.extend([
        'class="reference-chip"',
        'id="strengthSheet"',
        'class="strength-window"',
        'function openStrengthWindow()',
    ])
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError("Kommande vecka: previewvalidering misslyckades: " + repr(missing))
    if "Styrkemall framåt" in rendered:
        raise RuntimeError("Kommande vecka: styrkemallen exponeras fortfarande som öppet block")


def main():
    if not UPCOMING_FILE.exists():
        print("Kommande vecka: ingen upcoming_week.json; hoppar över.")
        return

    current_plan = load_json(CURRENT_PLAN_FILE)
    upcoming = load_json(UPCOMING_FILE)
    current_meta = current_plan.get("meta") or {}
    upcoming_meta = upcoming.get("meta") or {}
    current_key = week_key_from_meta(current_meta)
    upcoming_key = upcoming.get("week_key") or week_key_from_meta(upcoming_meta)

    current_end = date.fromisoformat(current_meta["week_end"])
    upcoming_start = date.fromisoformat(upcoming_meta["week_start"])
    upcoming_end = date.fromisoformat(upcoming_meta["week_end"])
    if upcoming_start != current_end + timedelta(days=1):
        raise RuntimeError("Kommande vecka: preview börjar inte dagen efter aktuell vecka")
    if (upcoming_end - upcoming_start).days != 6:
        raise RuntimeError("Kommande vecka: preview omfattar inte exakt sju dagar")
    if upcoming_key != week_key_from_meta(upcoming_meta):
        raise RuntimeError("Kommande vecka: week_key matchar inte ISO-veckan")
    if len(upcoming.get("days", [])) != 7:
        raise RuntimeError("Kommande vecka: planen måste innehålla sju dagar")

    render_preview(upcoming, current_key, upcoming_key)
    update_current_page(current_key, upcoming_key)
    print(f"Kommande vecka OK: {upcoming_key} publicerad som preliminär och länkad från {current_key}.")


if __name__ == "__main__":
    main()
