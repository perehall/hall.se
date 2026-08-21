#!/usr/bin/env python3
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CURRENT_PLAN_FILE = DATA_DIR / "plan.json"
UPCOMING_FILE = DATA_DIR / "upcoming_week.json"
MANIFEST_FILE = DATA_DIR / "weeks" / "index.json"
PAGES_DIR = ROOT / "vecka"
CURRENT_INDEX = ROOT / "index.html"

BUILD_CHAIN = (
    "build.py",
    "finalize_dashboard.py",
    "finalize_dashboard_ui.py",
    "finalize_yoda_ui.py",
    "finalize_header_ui.py",
    "finalize_navigation_ui.py",
    "finalize_sport_icons.py",
)

NAV_CSS_MARKER = "/* weekly-history-v1 */"
NAV_CSS = r'''
/* weekly-history-v1 */
.week-nav{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;margin:-4px 0 16px;padding:9px 10px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;box-shadow:0 6px 18px rgba(15,23,42,.04)}
.week-nav a{color:#1d4ed8;text-decoration:none;font-size:.82rem;font-weight:800}.week-nav .next{text-align:right}.week-nav-center{text-align:center;line-height:1.15}.week-nav-center strong{display:block;font-size:.86rem}.week-nav-center span{display:block;margin-top:3px;color:#64748b;font-size:.59rem;font-weight:900;letter-spacing:.1em}.week-nav-spacer{display:block}
@media (max-width:520px){.week-nav{grid-template-columns:1fr auto 1fr;padding:8px}.week-nav a{font-size:.75rem}.week-nav-center strong{font-size:.8rem}}
'''

PREVIEW_CSS_MARKER = "/* upcoming-week-preview-v1 */"
PREVIEW_CSS = r'''
/* upcoming-week-preview-v1 */
.preview-metrics{grid-template-columns:repeat(4,1fr)}
.preview-focus{color:#334155;font-size:.94rem;line-height:1.5}
.preview-note{margin-top:8px;color:#64748b;font-size:.82rem}
@media (max-width:620px){.preview-metrics{grid-template-columns:repeat(2,1fr)}}
'''


def load_json(path, fallback=None):
    if not path.exists():
        return {} if fallback is None else fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def week_key_from_meta(meta):
    start = date.fromisoformat(meta["week_start"])
    iso = start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_number(key):
    return int(key.split("-W", 1)[1])


def archive_url(key):
    return f"/träning/vecka/{key}/"


def ensure_css(page, marker, css):
    if marker in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Kommande vecka: kunde inte hitta </style>")
    return page.replace("</style>", css + "\n</style>", 1)


def replace_dashboard_with_preview(page, upcoming):
    statuses = {"fixed": 0, "planned": 0, "preliminary": 0, "open": 0}
    for day in upcoming.get("days", []):
        status = day.get("planning_status") or day.get("status") or "open"
        if status in statuses:
            statuses[status] += 1

    summary = (upcoming.get("meta") or {}).get("preview_summary", "")
    dashboard = f'''<section class="dashboard" aria-label="Planöversikt nästa vecka">
  <div class="metrics preview-metrics">
    <div class="metric"><strong>{statuses["fixed"]}</strong><span>fast</span></div>
    <div class="metric"><strong>{statuses["planned"]}</strong><span>planerat</span></div>
    <div class="metric"><strong>{statuses["preliminary"]}</strong><span>preliminärt</span></div>
    <div class="metric"><strong>{statuses["open"]}</strong><span>öppet</span></div>
  </div>
  <div class="dashboard-card">
    <div class="dashboard-title">Veckans fokus</div>
    <div class="preview-focus">{summary}</div>
    <div class="preview-note">Preliminär plan: detaljer och belastning får ändras när faktisk träning och återhämtning från föregående dagar är kända.</div>
  </div>
</section>'''

    start = page.find('<section class="dashboard"')
    if start < 0:
        raise RuntimeError("Kommande vecka: dashboard saknas")
    end = page.find("</section>", start)
    if end < 0:
        raise RuntimeError("Kommande vecka: dashboard kunde inte avgränsas")
    end += len("</section>")
    return page[:start] + dashboard + page[end:]


def patch_fixed_badges(page, upcoming):
    for day in upcoming.get("days", []):
        if day.get("planning_status") != "fixed":
            continue
        anchor = f'id="dag-{day["date"]}"'
        start = page.find(anchor)
        if start < 0:
            raise RuntimeError(f"Kommande vecka: dagankare saknas för {day['date']}")
        next_start = page.find('<div class="day"', start + len(anchor))
        end = next_start if next_start >= 0 else len(page)
        segment = page[start:end]
        old = '<div class="badge planned">PLANERAT</div>'
        if old not in segment:
            raise RuntimeError(f"Kommande vecka: planerad badge saknas för fast dag {day['date']}")
        segment = segment.replace(old, '<div class="badge fixed">FAST</div>', 1)
        page = page[:start] + segment + page[end:]
    return page


def insert_preview_nav(page, current_key, upcoming_key):
    page = ensure_css(page, NAV_CSS_MARKER, NAV_CSS)
    nav = (
        '<nav class="week-nav" aria-label="Veckonavigering">'
        f'<a class="prev" href="/träning/">← Vecka {week_number(current_key)}</a>'
        f'<div class="week-nav-center"><strong>Vecka {week_number(upcoming_key)}</strong><span>PRELIMINÄR</span></div>'
        '<span class="week-nav-spacer"></span>'
        '</nav>'
    )
    end = page.find("</header>")
    if end < 0:
        raise RuntimeError("Kommande vecka: </header> saknas")
    end += len("</header>")
    return page[:end] + "\n" + nav + page[end:]


def previous_archive_key(current_key):
    manifest = load_json(MANIFEST_FILE, {})
    keys = sorted(
        record.get("key")
        for record in manifest.get("weeks", [])
        if record.get("key")
    )
    if current_key not in keys:
        return None
    index = keys.index(current_key)
    return keys[index - 1] if index > 0 else None


def update_current_nav(current_key, upcoming_key):
    page = CURRENT_INDEX.read_text(encoding="utf-8")
    page = ensure_css(page, NAV_CSS_MARKER, NAV_CSS)
    previous_key = previous_archive_key(current_key)
    previous = (
        f'<a class="prev" href="{archive_url(previous_key)}">← Vecka {week_number(previous_key)}</a>'
        if previous_key
        else '<span class="week-nav-spacer"></span>'
    )
    nav = (
        '<nav class="week-nav" aria-label="Veckonavigering">'
        + previous
        + f'<div class="week-nav-center"><strong>Vecka {week_number(current_key)}</strong><span>AKTUELL</span></div>'
        + f'<a class="next" href="{archive_url(upcoming_key)}">Vecka {week_number(upcoming_key)} →</a>'
        + '</nav>'
    )
    pattern = re.compile(r'<nav class="week-nav"[^>]*>.*?</nav>', re.S)
    if pattern.search(page):
        page = pattern.sub(nav, page, count=1)
    else:
        end = page.find("</header>")
        if end < 0:
            raise RuntimeError("Kommande vecka: kunde inte lägga till navigation på aktuell sida")
        end += len("</header>")
        page = page[:end] + "\n" + nav + page[end:]
    CURRENT_INDEX.write_text(page, encoding="utf-8")


def build_preview(upcoming, current_key, upcoming_key):
    plan = {
        "meta": upcoming["meta"],
        "days": upcoming["days"],
        "strength_template": upcoming.get("strength_template", []),
    }
    with tempfile.TemporaryDirectory(prefix=f"training-preview-{upcoming_key}-") as tmp_name:
        tmp_root = Path(tmp_name)
        data_dir = tmp_root / "data"
        scripts_dir = tmp_root / "scripts"
        data_dir.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)

        write_json(data_dir / "plan.json", plan)
        write_json(data_dir / "activities.json", {"activities": []})
        write_json(data_dir / "coach.json", {"analyses": []})
        write_json(data_dir / "weather.json", {"status": "unavailable", "daily": {}})

        for script_name in BUILD_CHAIN:
            source = ROOT / "scripts" / script_name
            if not source.exists():
                raise RuntimeError(f"Kommande vecka: byggskript saknas: {script_name}")
            shutil.copy2(source, scripts_dir / script_name)

        for script_name in BUILD_CHAIN:
            subprocess.run([sys.executable, str(scripts_dir / script_name)], cwd=tmp_root, check=True)

        page = (tmp_root / "index.html").read_text(encoding="utf-8")

    page = ensure_css(page, PREVIEW_CSS_MARKER, PREVIEW_CSS)
    page = replace_dashboard_with_preview(page, upcoming)
    page = patch_fixed_badges(page, upcoming)
    page = insert_preview_nav(page, current_key, upcoming_key)
    page = page.replace(
        "<title>Träningsplan</title>",
        f"<title>Träningsplan · vecka {week_number(upcoming_key)} · preliminär</title>",
        1,
    )

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
    for day in upcoming.get("days", []):
        required.append(f'id="dag-{day["date"]}"')
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError("Kommande vecka: previewvalidering misslyckades: " + repr(missing))


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

    build_preview(upcoming, current_key, upcoming_key)
    update_current_nav(current_key, upcoming_key)
    print(f"Kommande vecka OK: {upcoming_key} publicerad som preliminär och länkad från {current_key}.")


if __name__ == "__main__":
    main()
