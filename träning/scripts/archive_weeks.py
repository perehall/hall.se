#!/usr/bin/env python3
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
WEEKS_DIR = DATA_DIR / "weeks"
PAGES_DIR = ROOT / "vecka"
PLAN_FILE = DATA_DIR / "plan.json"
ACTIVITIES_FILE = DATA_DIR / "activities.json"
COACH_FILE = DATA_DIR / "coach.json"
MANIFEST_FILE = WEEKS_DIR / "index.json"

BUILD_CHAIN = (
    "build.py",
    "finalize_dashboard.py",
    "finalize_dashboard_ui.py",
    "finalize_yoda_ui.py",
    "finalize_workout_history.py",
)

WEATHER_FOOTER = (
    ' · Väderprognos: <a href="https://www.smhi.se/" target="_blank" rel="noopener" '
    'style="color:inherit">SMHI</a> · standardplats Oxelösund om inget annat anges.'
)

HISTORY_CSS_MARKER = "/* weekly-history-v1 */"
HISTORY_CSS = r'''
/* weekly-history-v1 */
.week-nav{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;margin:-4px 0 16px;padding:9px 10px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;box-shadow:0 6px 18px rgba(15,23,42,.04)}
.week-nav a{color:#1d4ed8;text-decoration:none;font-size:.82rem;font-weight:800}.week-nav .next{text-align:right}.week-nav-center{text-align:center;line-height:1.15}.week-nav-center strong{display:block;font-size:.86rem}.week-nav-center span{display:block;margin-top:3px;color:#64748b;font-size:.59rem;font-weight:900;letter-spacing:.1em}.week-nav-spacer{display:block}.history-summary{color:#475569;font-size:.9rem;line-height:1.5}
@media (max-width:520px){.week-nav{grid-template-columns:1fr auto 1fr;padding:8px}.week-nav a{font-size:.75rem}.week-nav-center strong{font-size:.8rem}}
'''


def load_json(path, fallback=None):
    if not path.exists():
        return {} if fallback is None else fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def activity_date(activity):
    value = activity.get("start_date_local") or ""
    return value[:10] if len(value) >= 10 else ""


def plan_week(plan):
    meta = plan.get("meta") or {}
    start_text = meta.get("week_start")
    end_text = meta.get("week_end")
    if not start_text or not end_text:
        raise RuntimeError("Veckoarkiv: plan.meta saknar week_start/week_end")
    start = date.fromisoformat(start_text)
    end = date.fromisoformat(end_text)
    if (end - start).days != 6:
        raise RuntimeError("Veckoarkiv: aktuell plan omfattar inte exakt sju dagar")
    iso_start = start.isocalendar()
    iso_end = end.isocalendar()
    if (iso_start.year, iso_start.week) != (iso_end.year, iso_end.week):
        raise RuntimeError("Veckoarkiv: week_start och week_end ligger inte i samma ISO-vecka")
    declared_week = meta.get("week")
    if declared_week is not None and int(declared_week) != iso_start.week:
        raise RuntimeError(f"Veckoarkiv: planens vecka {declared_week} matchar inte ISO-vecka {iso_start.week}")
    key = f"{iso_start.year}-W{iso_start.week:02d}"
    return key, start_text, end_text


def snapshot_current_week(plan, activities_state, coach_state):
    key, week_start, week_end = plan_week(plan)
    WEEKS_DIR.mkdir(parents=True, exist_ok=True)
    path = WEEKS_DIR / f"{key}.json"
    previous = load_json(path, {})
    now = datetime.now(timezone.utc).isoformat()
    week_activities = [a for a in activities_state.get("activities", []) if activity_date(a) and week_start <= activity_date(a) <= week_end]
    week_analyses = [a for a in coach_state.get("analyses", []) if week_start <= (a.get("activity_date") or "") <= week_end]
    snapshot = {
        "schema_version": 1,
        "week_key": key,
        "week_start": week_start,
        "week_end": week_end,
        "created_at_utc": previous.get("created_at_utc") or now,
        "updated_at_utc": now,
        "plan": plan,
        "activities": week_activities,
        "coach_analyses": week_analyses,
    }
    write_json(path, snapshot)
    return snapshot


def snapshot_files():
    pattern = re.compile(r"^\d{4}-W\d{2}\.json$")
    return sorted(path for path in WEEKS_DIR.glob("*.json") if pattern.match(path.name))


def load_snapshots():
    snapshots = {}
    for path in snapshot_files():
        snapshot = load_json(path)
        key = snapshot.get("week_key")
        if key != path.stem:
            raise RuntimeError(f"Veckoarkiv: fel week_key i {path.name}")
        if not snapshot.get("plan"):
            raise RuntimeError(f"Veckoarkiv: plan saknas i {path.name}")
        snapshots[key] = snapshot
    return snapshots


def week_number(key):
    return int(key.split("-W", 1)[1])


def archive_url(key):
    return f"/träning/vecka/{key}/"


def nav_html(key, ordered_keys, current_key, is_current):
    index = ordered_keys.index(key)
    previous_key = ordered_keys[index - 1] if index > 0 else None
    next_key = ordered_keys[index + 1] if index + 1 < len(ordered_keys) else None
    previous = f'<a class="prev" href="{archive_url(previous_key)}">← Vecka {week_number(previous_key)}</a>' if previous_key else '<span class="week-nav-spacer"></span>'
    if is_current:
        next_link = '<span class="week-nav-spacer"></span>'
        state = "AKTUELL"
    else:
        if next_key:
            next_link = f'<a class="next" href="{archive_url(next_key)}">Vecka {week_number(next_key)} →</a>'
        else:
            next_link = f'<a class="next" href="{archive_url(current_key)}">Aktuell vecka →</a>'
        state = "HISTORIK"
    return '<nav class="week-nav" aria-label="Veckohistorik">' + previous + f'<div class="week-nav-center"><strong>Vecka {week_number(key)}</strong><span>{state}</span></div>' + next_link + '</nav>'


def add_history_css(page):
    if HISTORY_CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Veckoarkiv: kunde inte hitta </style>")
    return page.replace("</style>", HISTORY_CSS + "\n</style>", 1)


def insert_nav(page, navigation):
    page = add_history_css(page)
    end = page.find("</header>")
    if end < 0:
        raise RuntimeError("Veckoarkiv: kunde inte hitta </header>")
    end += len("</header>")
    return page[:end] + "\n" + navigation + page[end:]


def historical_stamp(snapshot):
    timezone_name = ((snapshot.get("plan") or {}).get("meta", {}).get("timezone") or "Europe/Stockholm")
    tz = ZoneInfo(timezone_name)
    value = snapshot.get("updated_at_utc")
    try:
        stamp = datetime.fromisoformat(value).astimezone(tz)
    except (TypeError, ValueError):
        return snapshot.get("week_end") or ""
    return stamp.strftime("%Y-%m-%d %H:%M")


def make_historical(page, snapshot, ordered_keys, current_key):
    key = snapshot["week_key"]
    page = page.replace(WEATHER_FOOTER, "")
    page = page.replace("<title>Träningsplan</title>", f"<title>Träningsplan · vecka {week_number(key)}</title>", 1)
    title = '<div class="dashboard-title">Kommande dagar</div>'
    title_pos = page.find(title)
    if title_pos < 0:
        raise RuntimeError(f"Veckoarkiv {key}: Kommande dagar saknas")
    card_start = page.rfind('<div class="dashboard-card">', 0, title_pos)
    section_end = page.find("</section>", title_pos)
    if card_start < 0 or section_end < 0:
        raise RuntimeError(f"Veckoarkiv {key}: dashboardkort kunde inte avgränsas")
    summary_card = '<div class="dashboard-card">\n    <div class="dashboard-title">Veckosummering</div>\n    <div class="history-summary">Avslutad vecka · plan, utfall, passupplägg och Tränings-Yodas bedömningar är bevarade.</div>\n  </div>\n'
    page = page[:card_start] + summary_card + page[section_end:]
    stamp = historical_stamp(snapshot)
    page = re.sub(r'(<div class="sub">[^<]*?) · senast uppdaterad [^<]*(</div>)', rf'\1 · historik · data sparad {stamp}\2', page, count=1)
    page = insert_nav(page, nav_html(key, ordered_keys, current_key, is_current=False))
    if "Kommande dagar" in page:
        raise RuntimeError(f"Veckoarkiv {key}: tidsberoende Kommande dagar finns kvar")
    return page


def build_snapshot_page(snapshot, ordered_keys, current_key):
    key = snapshot["week_key"]
    with tempfile.TemporaryDirectory(prefix=f"training-{key}-") as tmp_name:
        tmp_root = Path(tmp_name)
        data_dir = tmp_root / "data"
        scripts_dir = tmp_root / "scripts"
        data_dir.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)
        write_json(data_dir / "plan.json", snapshot["plan"])
        write_json(data_dir / "activities.json", {"activities": snapshot.get("activities", [])})
        write_json(data_dir / "coach.json", {"analyses": snapshot.get("coach_analyses", [])})
        write_json(data_dir / "weather.json", {"status": "unavailable", "daily": {}})
        for script_name in BUILD_CHAIN:
            source = ROOT / "scripts" / script_name
            if not source.exists():
                raise RuntimeError(f"Veckoarkiv: byggskript saknas: {script_name}")
            shutil.copy2(source, scripts_dir / script_name)
        for script_name in BUILD_CHAIN:
            subprocess.run([sys.executable, str(scripts_dir / script_name)], cwd=tmp_root, check=True)
        page = (tmp_root / "index.html").read_text(encoding="utf-8")
    page = make_historical(page, snapshot, ordered_keys, current_key)
    output_dir = PAGES_DIR / key
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(page, encoding="utf-8")


def update_current_page(current_key, ordered_keys):
    index_file = ROOT / "index.html"
    page = index_file.read_text(encoding="utf-8")
    page = insert_nav(page, nav_html(current_key, ordered_keys, current_key, is_current=True))
    index_file.write_text(page, encoding="utf-8")


def write_manifest(snapshots, current_key):
    records = []
    for key in sorted(snapshots):
        snapshot = snapshots[key]
        plan_meta = (snapshot.get("plan") or {}).get("meta") or {}
        records.append({
            "key": key,
            "week": week_number(key),
            "week_start": snapshot.get("week_start"),
            "week_end": snapshot.get("week_end"),
            "title": plan_meta.get("title"),
            "updated_at_utc": snapshot.get("updated_at_utc"),
            "is_current": key == current_key,
            "url": archive_url(key),
        })
    write_json(MANIFEST_FILE, {"schema_version": 2, "current_week_key": current_key, "weeks": records})


def main():
    WEEKS_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    plan = load_json(PLAN_FILE)
    activities_state = load_json(ACTIVITIES_FILE, {"activities": []})
    coach_state = load_json(COACH_FILE, {"analyses": []})
    current_snapshot = snapshot_current_week(plan, activities_state, coach_state)
    snapshots = load_snapshots()
    current_key = current_snapshot["week_key"]
    ordered_keys = sorted(snapshots)
    for key in ordered_keys:
        if key == current_key:
            continue
        build_snapshot_page(snapshots[key], ordered_keys, current_key)
    update_current_page(current_key, ordered_keys)
    write_manifest(snapshots, current_key)
    print(f"Veckoarkiv OK: {len(snapshots)} vecka/veckor, aktuell {current_key} via {archive_url(current_key)}.")


if __name__ == "__main__":
    main()
