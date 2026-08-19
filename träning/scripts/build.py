#!/usr/bin/env python3
import json, html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))
acts = json.loads((ROOT / "data" / "activities.json").read_text(encoding="utf-8"))
tz = ZoneInfo(plan["meta"].get("timezone", "Europe/Stockholm"))

status_labels = {
    "completed": "GENOMFÖRT",
    "planned": "PLANERAT",
    "preliminary": "PRELIMINÄRT",
    "conditional": "VILLKORAT",
    "open": "ÖPPET",
}
status_classes = {
    "completed": "fixed",
    "planned": "planned",
    "preliminary": "conditional",
    "conditional": "conditional",
    "open": "open",
}

acts_by_date = {}
for a in acts.get("activities", []):
    local = a.get("start_date_local") or ""
    if len(local) >= 10:
        acts_by_date.setdefault(local[:10], []).append(a)


def fmt_duration(sec):
    if sec is None:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_activity(a):
    bits = []
    if a.get("distance_m"):
        bits.append(f'{a["distance_m"] / 1000:.2f} km'.replace(".", ","))
    if a.get("elapsed_time_s"):
        bits.append(fmt_duration(a["elapsed_time_s"]))
    if a.get("average_heartrate"):
        bits.append(f'snittpuls {round(a["average_heartrate"])}')
    if a.get("max_heartrate"):
        bits.append(f'max {round(a["max_heartrate"])}')
    return " · ".join(bits)


cards = []
for d in plan["days"]:
    st = d.get("status", "open")
    raw = acts_by_date.get(d["date"], [])
    auto = ""
    if raw:
        lines = "".join(
            f'<div><strong>{html.escape(a.get("sport_type") or "Aktivitet")}</strong> · {html.escape(fmt_activity(a))}</div>'
            for a in raw
        )
        auto = f'<div class="pass"><div class="pass-title">Automatiskt från Strava</div>{lines}</div>'
    ref = (
        f'<div class="decision"><strong>Referens</strong>{html.escape(d["reference"])}</div>'
        if d.get("reference")
        else ""
    )
    cards.append(
        f'''<div class="day">
  <div class="daytop">
    <div><div class="dow">{html.escape(d["label"])}</div><div class="date">{html.escape(d["date"])}</div></div>
    <div class="badge {status_classes.get(st, "open")}">{status_labels.get(st, st.upper())}</div>
  </div>
  <div class="session">{html.escape(d["session"])}</div>
  <div class="reason">{html.escape(d.get("reason", ""))}</div>
  {ref}{auto}
</div>'''
    )

updated = datetime.now(tz).strftime("%-d %B %Y · %H:%M")
months = {
    "January": "januari",
    "February": "februari",
    "March": "mars",
    "April": "april",
    "May": "maj",
    "June": "juni",
    "July": "juli",
    "August": "augusti",
    "September": "september",
    "October": "oktober",
    "November": "november",
    "December": "december",
}
for en, sv in months.items():
    updated = updated.replace(en, sv)

strength = "".join(
    f'<div class="principle">{html.escape(x)}</div>'
    for x in plan.get("strength_template", [])
)

doc = f'''<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0f172a">
<title>Träningsplan</title>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#2563eb;--green:#15803d;--green-soft:#dcfce7;--amber:#a16207;--amber-soft:#fef3c7;--shadow:0 8px 24px rgba(15,23,42,.06)}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);line-height:1.45}}
.wrap{{width:min(100%,760px);margin:auto;padding:20px 16px 56px}}header{{padding:8px 2px 18px}}
.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:.76rem;font-weight:800;color:var(--accent);margin-bottom:6px}}
h1{{font-size:clamp(2rem,8vw,3.2rem);line-height:1;margin:0 0 8px;letter-spacing:-.04em}}.sub{{color:var(--muted);font-size:.96rem}}
.hero{{background:#0f172a;color:#fff;border-radius:20px;padding:18px 20px;margin:8px 0 22px;box-shadow:var(--shadow)}}.hero h2{{margin:4px 0 5px}}.hero p{{margin:0;color:#cbd5e1}}
.section{{font-size:1.22rem;margin:28px 0 12px}}.day{{background:#fff;border:1px solid var(--line);border-radius:20px;padding:18px;margin:12px 0;box-shadow:var(--shadow)}}
.daytop{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}}.dow{{font-size:.82rem;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}.date{{color:var(--muted);font-size:.85rem}}
.session{{font-size:1.2rem;font-weight:800;margin:4px 0 6px}}.reason{{color:#334155;font-size:.95rem}}.badge{{border-radius:999px;padding:5px 9px;font-size:.7rem;font-weight:800;white-space:nowrap}}
.fixed{{background:var(--green-soft);color:var(--green)}}.planned{{background:#dbeafe;color:#1d4ed8}}.conditional{{background:var(--amber-soft);color:var(--amber)}}.open{{background:#e2e8f0;color:#475569}}
.pass{{margin-top:14px;padding-top:14px;border-top:1px solid var(--line);display:grid;gap:7px}}.pass-title{{font-weight:800}}.decision{{margin-top:13px;padding:12px 13px;background:#f8fafc;border-radius:13px;border:1px solid var(--line)}}.decision strong{{display:block;margin-bottom:4px}}
.principles{{display:grid;gap:10px}}.principle{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px 16px}}footer{{color:var(--muted);font-size:.82rem;padding-top:26px}}
</style>
</head>
<body><div class="wrap">
<header><div class="eyebrow">Levande träningsplan</div><h1>Vecka {plan["meta"]["week"]}</h1><div class="sub">{plan["meta"]["week_start"]}–{plan["meta"]["week_end"]} · senast uppdaterad {updated}</div></header>
<div class="hero"><h2>{html.escape(plan["meta"]["title"])}</h2><p>{html.escape(plan["meta"]["principle"])}</p></div>
<h2 class="section">Aktuell vecka</h2>{''.join(cards)}
<h2 class="section">Styrkemall framåt</h2><div class="principles">{strength}</div>
<footer>Automatiskt byggd från plan.json + activities.json. Strava-data används som fakta; automatiken ökar aldrig träningsbelastningen.</footer>
</div></body></html>'''

(ROOT / "index.generated.html").write_text(doc, encoding="utf-8")
print(ROOT / "index.generated.html")
