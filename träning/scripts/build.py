#!/usr/bin/env python3
import json, html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))
acts = json.loads((ROOT / "data" / "activities.json").read_text(encoding="utf-8"))
coach_file = ROOT / "data" / "coach.json"
coach = json.loads(coach_file.read_text(encoding="utf-8")) if coach_file.exists() else {"analyses": []}
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
action_labels = {
    "keep": "Behåll planen",
    "reduce": "Skala ned",
    "rest": "Vila / mycket lätt",
    "review": "Behöver bedömas",
}
day_short = {
    "Måndag": "Må",
    "Tisdag": "Ti",
    "Onsdag": "On",
    "Torsdag": "To",
    "Fredag": "Fr",
    "Lördag": "Lö",
    "Söndag": "Sö",
}
sport_groups = {
    "Run": "Löpning",
    "TrailRun": "Löpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "MountainBikeRide": "MTB/XC",
    "Ride": "Cykel",
    "VirtualRide": "Cykel",
    "WeightTraining": "Styrka",
}

acts_by_date = {}
for a in acts.get("activities", []):
    local = a.get("start_date_local") or ""
    if len(local) >= 10:
        acts_by_date.setdefault(local[:10], []).append(a)

coach_by_date = {}
for c in coach.get("analyses", []):
    date = c.get("activity_date") or ""
    if date and date not in coach_by_date:
        coach_by_date[date] = c


def fmt_duration(sec):
    if sec is None:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_compact_duration(sec):
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600)
    m = rem // 60
    return f"{h} h {m:02d} min" if h else f"{m} min"


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


def coach_html(c):
    if not c:
        return ""
    assessment = c.get("assessment", {})
    action = c.get("plan_action", {})
    facts = assessment.get("facts", [])
    interpretations = assessment.get("interpretations", [])
    unknowns = assessment.get("unknowns", [])

    facts_html = "".join(f"<li>{html.escape(x)}</li>" for x in facts)
    interp_html = "".join(f"<li>{html.escape(x)}</li>" for x in interpretations)
    unknown_html = "".join(f"<li>{html.escape(x)}</li>" for x in unknowns)
    action_name = action_labels.get(action.get("action"), action.get("action", ""))
    target = action.get("target_date") or "ingen specifik dag"
    applied = c.get("auto_apply", {}).get("applied", False)
    apply_text = "Automatiskt applicerad konservativ ändring." if applied else "Ingen automatisk ändring applicerad."

    return f'''<div class="coach">
  <div class="coach-title">AI-coach · bedömning</div>
  <div class="coach-summary">{html.escape(assessment.get("summary", ""))}</div>
  <div class="coach-load">{html.escape(assessment.get("load_interpretation", ""))}</div>
  <details class="coach-details"><summary>Fakta, tolkning och osäkerhet</summary>
    <div class="coach-grid">
      <div><strong>Fakta</strong><ul>{facts_html}</ul></div>
      <div><strong>Tolkning</strong><ul>{interp_html}</ul></div>
      <div><strong>Osäkert/saknas</strong><ul>{unknown_html}</ul></div>
    </div>
  </details>
  <div class="coach-action"><strong>{html.escape(action_name)}</strong> · {html.escape(target)}<br>{html.escape(action.get("reason", ""))}<br><span>{html.escape(action.get("recommendation", ""))}</span><br><small>{apply_text}</small></div>
</div>'''


cards = []
for d in plan["days"]:
    raw = acts_by_date.get(d["date"], [])
    st = "completed" if raw else d.get("status", "open")
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
    adjustment = (
        f'<div class="decision coach-adjust"><strong>Coachjustering</strong>{html.escape(d["coach_adjustment"])}</div>'
        if d.get("coach_adjustment")
        else ""
    )
    coach_block = coach_html(coach_by_date.get(d["date"]))
    cards.append(
        f'''<div class="day">
  <div class="daytop">
    <div><div class="dow">{html.escape(d["label"])}</div><div class="date">{html.escape(d["date"])}</div></div>
    <div class="badge {status_classes.get(st, "open")}">{status_labels.get(st, st.upper())}</div>
  </div>
  <div class="session">{html.escape(d["session"])}</div>
  <div class="reason">{html.escape(d.get("reason", ""))}</div>
  {ref}{adjustment}{auto}{coach_block}
</div>'''
    )

now = datetime.now(tz)
today = now.date().isoformat()
week_start = plan["meta"]["week_start"]
week_end = plan["meta"]["week_end"]

week_acts = []
for date, day_acts in acts_by_date.items():
    if week_start <= date <= week_end:
        week_acts.extend(day_acts)

week_active_seconds = sum(int(a.get("moving_time_s") or a.get("elapsed_time_s") or 0) for a in week_acts)
week_training_days = len({(a.get("start_date_local") or "")[:10] for a in week_acts if len(a.get("start_date_local") or "") >= 10})

sport_seconds = {}
for a in week_acts:
    group = sport_groups.get(a.get("sport_type"), a.get("sport_type") or "Övrigt")
    sec = int(a.get("moving_time_s") or a.get("elapsed_time_s") or 0)
    sport_seconds[group] = sport_seconds.get(group, 0) + sec

sport_rows = []
for group, sec in sorted(sport_seconds.items(), key=lambda item: item[1], reverse=True):
    pct = round(sec / week_active_seconds * 100) if week_active_seconds else 0
    sport_rows.append(
        f'''<div class="sport-row">
  <div class="sport-head"><span>{html.escape(group)}</span><strong>{fmt_compact_duration(sec)}</strong></div>
  <div class="sport-track"><div class="sport-fill" style="width:{pct}%"></div></div>
</div>'''
    )
sport_distribution = "".join(sport_rows) or '<div class="dashboard-empty">Ingen registrerad aktivitet denna vecka ännu.</div>'

day_markers = []
marker_symbols = {
    "completed": "✓",
    "planned": "●",
    "preliminary": "◐",
    "conditional": "◐",
    "open": "·",
}
for d in plan["days"]:
    raw = acts_by_date.get(d["date"], [])
    st = "completed" if raw else d.get("status", "open")
    today_class = " today" if d["date"] == today else ""
    day_markers.append(
        f'''<div class="week-day{today_class}">
  <div class="week-day-label">{day_short.get(d["label"], html.escape(d["label"][:2]))}</div>
  <div class="week-day-dot {status_classes.get(st, "open")}">{marker_symbols.get(st, "·")}</div>
</div>'''
    )

next_items = []
for d in plan["days"]:
    raw = acts_by_date.get(d["date"], [])
    if d["date"] < today or raw:
        continue
    st = d.get("status", "open")
    adjustment = d.get("coach_adjustment", "")
    adjustment_short = ""
    if adjustment:
        first_sentence = adjustment.split(". ", 1)[0].rstrip(".") + "."
        adjustment_short = f'<div class="next-coach">Coach: {html.escape(first_sentence)}</div>'
    next_items.append(
        f'''<div class="next-item">
  <div class="next-top"><strong>{html.escape(d["label"])}</strong><span class="badge {status_classes.get(st, "open")}">{status_labels.get(st, st.upper())}</span></div>
  <div>{html.escape(d["session"])}</div>
  {adjustment_short}
</div>'''
    )
    if len(next_items) == 3:
        break
next_html = "".join(next_items) or '<div class="dashboard-empty">Inga fler planerade dagar i aktuell vecka.</div>'

dashboard = f'''<section class="dashboard" aria-label="Veckoöversikt">
  <div class="metrics">
    <div class="metric"><strong>{len(week_acts)}</strong><span>pass</span></div>
    <div class="metric"><strong>{fmt_compact_duration(week_active_seconds)}</strong><span>aktiv tid</span></div>
    <div class="metric"><strong>{week_training_days}</strong><span>träningsdagar</span></div>
  </div>
  <div class="dashboard-grid">
    <div class="dashboard-card">
      <div class="dashboard-title">Grenfördelning · aktiv tid</div>
      {sport_distribution}
    </div>
    <div class="dashboard-card">
      <div class="dashboard-title">Plan → utfall</div>
      <div class="week-status">{''.join(day_markers)}</div>
      <div class="dashboard-legend">✓ genomfört · ● planerat · ◐ preliminärt/villkorat · · öppet</div>
    </div>
  </div>
  <div class="dashboard-card">
    <div class="dashboard-title">Nästa dagar</div>
    {next_html}
  </div>
</section>'''

updated = now.strftime("%-d %B %Y · %H:%M")
months = {
    "January": "januari", "February": "februari", "March": "mars", "April": "april",
    "May": "maj", "June": "juni", "July": "juli", "August": "augusti",
    "September": "september", "October": "oktober", "November": "november", "December": "december",
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
:root{{--bg:#f5f7fb;--card:#fff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#2563eb;--green:#15803d;--green-soft:#dcfce7;--amber:#a16207;--amber-soft:#fef3c7;--purple:#6d28d9;--purple-soft:#f3e8ff;--shadow:0 8px 24px rgba(15,23,42,.06)}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);line-height:1.45}}
.wrap{{width:min(100%,760px);margin:auto;padding:20px 16px 56px}}header{{padding:8px 2px 18px}}
.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:.76rem;font-weight:800;color:var(--accent);margin-bottom:6px}}
h1{{font-size:clamp(2rem,8vw,3.2rem);line-height:1;margin:0 0 8px;letter-spacing:-.04em}}.sub{{color:var(--muted);font-size:.96rem}}
.hero{{background:#0f172a;color:#fff;border-radius:20px;padding:18px 20px;margin:8px 0 18px;box-shadow:var(--shadow)}}.hero h2{{margin:4px 0 5px}}.hero p{{margin:0;color:#cbd5e1}}
.dashboard{{display:grid;gap:12px;margin:0 0 24px}}.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.metric{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:13px 14px;box-shadow:var(--shadow)}}.metric strong{{display:block;font-size:1.22rem;line-height:1.15}}.metric span{{display:block;color:var(--muted);font-size:.78rem;margin-top:4px}}
.dashboard-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.dashboard-card{{background:#fff;border:1px solid var(--line);border-radius:18px;padding:15px 16px;box-shadow:var(--shadow)}}.dashboard-title{{font-size:.78rem;font-weight:900;text-transform:uppercase;letter-spacing:.07em;color:#475569;margin-bottom:12px}}.dashboard-empty{{color:var(--muted);font-size:.88rem}}
.sport-row+.sport-row{{margin-top:10px}}.sport-head{{display:flex;justify-content:space-between;gap:12px;font-size:.84rem}}.sport-head strong{{font-size:.8rem}}.sport-track{{height:7px;background:#e2e8f0;border-radius:999px;overflow:hidden;margin-top:5px}}.sport-fill{{height:100%;background:var(--accent);border-radius:999px}}
.week-status{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}}.week-day{{text-align:center;border-radius:10px;padding:5px 2px}}.week-day.today{{background:#eff6ff}}.week-day-label{{font-size:.68rem;font-weight:800;color:var(--muted);margin-bottom:4px}}.week-day-dot{{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;margin:auto;font-size:.78rem;font-weight:900}}.dashboard-legend{{color:var(--muted);font-size:.7rem;margin-top:10px;line-height:1.5}}
.next-item{{padding:10px 0}}.next-item+.next-item{{border-top:1px solid var(--line)}}.next-top{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:3px}}.next-coach{{color:var(--purple);font-size:.82rem;margin-top:4px}}
.section{{font-size:1.22rem;margin:28px 0 12px}}.day{{background:#fff;border:1px solid var(--line);border-radius:20px;padding:18px;margin:12px 0;box-shadow:var(--shadow)}}
.daytop{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}}.dow{{font-size:.82rem;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}.date{{color:var(--muted);font-size:.85rem}}
.session{{font-size:1.2rem;font-weight:800;margin:4px 0 6px}}.reason{{color:#334155;font-size:.95rem}}.badge{{border-radius:999px;padding:5px 9px;font-size:.7rem;font-weight:800;white-space:nowrap}}
.fixed{{background:var(--green-soft);color:var(--green)}}.planned{{background:#dbeafe;color:#1d4ed8}}.conditional{{background:var(--amber-soft);color:var(--amber)}}.open{{background:#e2e8f0;color:#475569}}
.pass{{margin-top:14px;padding-top:14px;border-top:1px solid var(--line);display:grid;gap:7px}}.pass-title{{font-weight:800}}.decision{{margin-top:13px;padding:12px 13px;background:#f8fafc;border-radius:13px;border:1px solid var(--line)}}.decision strong{{display:block;margin-bottom:4px}}.coach-adjust{{border-color:#ddd6fe;background:#faf5ff}}
.coach{{margin-top:16px;padding:14px;border-radius:16px;background:var(--purple-soft);border:1px solid #ddd6fe}}.coach-title{{font-size:.75rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em;color:var(--purple);margin-bottom:5px}}.coach-summary{{font-weight:800;margin-bottom:5px}}.coach-load{{color:#4c1d95;font-size:.92rem}}.coach-details{{margin-top:10px}}.coach-details summary{{cursor:pointer;font-weight:700}}.coach-grid{{display:grid;gap:8px;margin-top:8px;font-size:.88rem}}.coach-grid ul{{margin:4px 0 0;padding-left:18px}}.coach-action{{margin-top:10px;padding-top:10px;border-top:1px solid #ddd6fe;font-size:.9rem}}.coach-action span{{color:#4c1d95}}.coach-action small{{color:#6b21a8}}
.principles{{display:grid;gap:10px}}.principle{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px 16px}}footer{{color:var(--muted);font-size:.82rem;padding-top:26px}}
@media (max-width:620px){{.dashboard-grid{{grid-template-columns:1fr}}.metrics{{gap:7px}}.metric{{padding:12px 10px}}.metric strong{{font-size:1.05rem}}}}
</style>
</head>
<body><div class="wrap">
<header><div class="eyebrow">ADAPTIV TRÄNINGSPLANERING</div><h1>Vecka {plan["meta"]["week"]}</h1><div class="sub">{plan["meta"]["week_start"]}–{plan["meta"]["week_end"]} · senast uppdaterad {updated}</div></header>
<div class="hero"><h2>{html.escape(plan["meta"]["title"])}</h2><p>{html.escape(plan["meta"]["principle"])}</p></div>
{dashboard}
<h2 class="section">Aktuell vecka</h2>{''.join(cards)}
<h2 class="section">Styrkemall framåt</h2><div class="principles">{strength}</div>
<footer>Automatiskt byggd från plan.json + activities.json + coach.json. Strava-data används som fakta. AI-coachen får automatiskt endast behålla, minska eller ersätta belastning konservativt; belastningsökning kräver mänsklig bedömning. · <a href="/cdn-cgi/access/logout" style="color:inherit" onclick="window.location.replace(this.href); return false;">Logga ut</a></footer>
</div>
<script>
window.addEventListener("pageshow", (event) => {{
  if (event.persisted) {{
    window.location.reload();
  }}
}});
</script>
</body></html>'''

(ROOT / "index.html").write_text(doc, encoding="utf-8")
print(ROOT / "index.html")
