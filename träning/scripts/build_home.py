#!/usr/bin/env python3
import html
import json
import re
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INDEX = ROOT / "index.html"
GOAL = DATA / "goal.json"
PLAN = DATA / "plan.json"
UPCOMING = DATA / "upcoming_week.json"
WEEK_DIR = ROOT / "vecka"

COLORS = {
    "run": ("#22a06b", "#e7f7ef"),
    "mtb": ("#8b5cf6", "#f1ebff"),
    "swim": ("#4f86f7", "#eaf2ff"),
    "strength": ("#f2a33b", "#fff2df"),
    "enduro": ("#6577a8", "#eef2fb"),
}
ICONS = {"run":"↗","mtb":"◇","swim":"≈","strength":"＋","enduro":"△"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def week_key(meta):
    d = date.fromisoformat(meta["week_start"])
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_num(key):
    return int(key.split("-W")[1])


def esc(value):
    return html.escape(str(value))


def progress(level, color):
    level = max(0, min(5, int(level)))
    return '<div class="progress">' + ''.join(
        f'<span style="background:{color if i < level else "#e7ebf2"}"></span>' for i in range(5)
    ) + '</div>'


def main():
    goal = load(GOAL)
    plan = load(PLAN)
    upcoming = load(UPCOMING) if UPCOMING.exists() else {}
    current_key = week_key(plan["meta"])
    upcoming_key = upcoming.get("week_key") or ""

    # Preserve the fully finalized current-week page before index becomes the goal homepage.
    current_dir = WEEK_DIR / current_key
    current_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(INDEX, current_dir / "index.html")

    # Fix the preliminary week's back navigation now that /träning/ is the goal homepage.
    if upcoming_key:
        preview = WEEK_DIR / upcoming_key / "index.html"
        if preview.exists():
            page = preview.read_text(encoding="utf-8")
            page = re.sub(
                rf'href="/träning/">← Vecka {week_num(current_key)}</a>',
                f'href="/träning/vecka/{current_key}/">← Vecka {week_num(current_key)}</a>',
                page,
            )
            preview.write_text(page, encoding="utf-8")

    disciplines = []
    for item in goal.get("disciplines", []):
        key = item["key"]
        color, soft = COLORS.get(key, ("#4f46e5", "#eef2ff"))
        disciplines.append(f'''<div class="status-row">
          <div class="sport-icon" style="background:{soft};color:{color}">{ICONS.get(key,"•")}</div>
          <div class="sport-name">{esc(item["label"])}</div>
          {progress(item.get("level",0), color)}
          <div class="status-note" style="color:{color}">{esc(item["status"])}</div>
        </div>''')

    phases = []
    current_phase = int(goal.get("current_phase", 1))
    for phase in goal.get("phases", []):
        number = int(phase["number"])
        cls = "phase active" if number == current_phase else "phase done" if number < current_phase else "phase"
        tag = '<div class="you-are-here">Du är här</div>' if number == current_phase else ''
        phases.append(f'''<div class="{cls}">{tag}<div class="phase-num">{number}</div>
          <strong>{esc(phase["name"])}</strong><span>{esc(phase["description"])}</span></div>''')

    principles = ''.join(f'<div class="principle"><div class="picon">{i+1}</div><span>{esc(p)}</span></div>' for i,p in enumerate(goal.get("principles", [])))
    steps = ''.join(f'<div class="next-row"><span class="step-dot">{i+1}</span><span>{esc(s)}</span><b>›</b></div>' for i,s in enumerate(goal.get("next_steps", [])))

    current_url = f"/träning/vecka/{current_key}/"
    upcoming_link = f'<a href="/träning/vecka/{upcoming_key}/">Nästa vecka <b>→</b></a>' if upcoming_key else ''

    page = f'''<!doctype html><html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f5f7fb"><title>{esc(goal["title"])} · Adaptiv träningsplanering</title>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#4938ee;--shadow:0 10px 28px rgba(15,23,42,.06)}}*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);line-height:1.45}}.wrap{{width:min(100%,920px);margin:auto;padding:28px 18px 60px}}.eyebrow{{font-size:.78rem;font-weight:900;letter-spacing:.13em;text-transform:uppercase;color:var(--accent)}}h1{{font-size:clamp(3rem,9vw,5rem);line-height:.98;letter-spacing:-.055em;margin:20px 0 8px}}.sub{{color:var(--muted);font-weight:650;font-size:1rem}}.quicknav{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:24px 0}}.quicknav a{{padding:14px 16px;border-radius:16px;background:#fff;border:1px solid var(--line);box-shadow:var(--shadow);text-decoration:none;color:#1e293b;font-weight:850;display:flex;justify-content:space-between}}.card{{background:#fff;border:1px solid var(--line);box-shadow:var(--shadow);border-radius:22px;padding:22px;margin:18px 0}}.title{{font-size:1.18rem;font-weight:900;margin-bottom:16px}}.goal{{display:grid;grid-template-columns:1.08fr .92fr;gap:24px;align-items:center}}.goal p{{font-size:1.02rem;color:#334155;margin:0}}.mountain{{min-height:240px;position:relative;overflow:hidden;border-radius:18px;background:linear-gradient(#fbfcff,#f0f4ff)}}.mountain svg{{position:absolute;inset:0;width:100%;height:100%}}.status-head{{display:flex;justify-content:space-between;align-items:center;gap:12px}}.pill{{padding:9px 13px;border-radius:13px;background:#e7f7ef;color:#198754;border:1px solid #a7dfc4;font-weight:900}}.status-row{{display:grid;grid-template-columns:48px minmax(145px,1fr) minmax(180px,1.25fr) 160px;gap:14px;align-items:center;padding:10px 0;border-top:1px solid #edf1f6}}.status-row:first-of-type{{border-top:0}}.sport-icon{{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;font-size:1.25rem;font-weight:900}}.sport-name{{font-weight:800}}.progress{{display:grid;grid-template-columns:repeat(5,1fr);gap:4px}}.progress span{{height:8px;border-radius:99px}}.status-note{{font-weight:850;font-size:.9rem}}.phases{{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid #edf1f6;border-radius:18px;overflow:visible;margin-top:34px}}.phase{{position:relative;min-height:170px;padding:24px 12px 16px;text-align:center;border-right:1px solid #edf1f6;background:#fff}}.phase:last-child{{border-right:0}}.phase.done{{background:#f2fbf6}}.phase.active{{background:#f1f5ff}}.phase-num{{width:40px;height:40px;margin:0 auto 14px;border:2px solid #d5dce8;border-radius:50%;display:grid;place-items:center;font-weight:900;background:#fff}}.phase.done .phase-num{{border-color:#22a06b;color:#168354}}.phase.active .phase-num{{background:#4f74ef;border-color:#4f74ef;color:#fff;box-shadow:0 8px 18px #d8e1ff}}.phase strong{{display:block;font-size:.92rem;margin-bottom:6px}}.phase span{{display:block;color:#475569;font-size:.82rem;line-height:1.3}}.you-are-here{{position:absolute;top:-25px;left:50%;transform:translateX(-50%);white-space:nowrap;background:#fff;color:#3765ec;border:1.5px solid #6c91f7;border-radius:8px;padding:3px 8px;font-size:.72rem;font-weight:900}}.principles{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}}.principle{{min-height:128px;border:1px solid var(--line);border-radius:16px;padding:14px 10px;text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px}}.picon{{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#f0edff;color:var(--accent);font-weight:900}}.principle span{{font-size:.78rem;font-weight:800;line-height:1.25}}.next-row{{display:grid;grid-template-columns:38px 1fr 20px;gap:12px;align-items:center;padding:14px 0;border-top:1px solid #edf1f6;font-weight:760}}.next-row:first-child{{border-top:0}}.step-dot{{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#eef2ff;color:#4f46e5;font-weight:900}}.next-row b{{font-size:1.35rem;color:#718096}}footer{{color:var(--muted);font-size:.8rem;padding-top:22px;text-align:center}}@media(max-width:700px){{.wrap{{padding:22px 14px 54px}}.goal{{grid-template-columns:1fr}}.mountain{{min-height:190px}}.status-row{{grid-template-columns:44px 1fr}}.status-row .progress,.status-row .status-note{{grid-column:2}}.phases{{grid-template-columns:1fr;margin-top:18px;overflow:hidden}}.phase{{min-height:auto;text-align:left;display:grid;grid-template-columns:46px 1fr;column-gap:12px;align-items:center;border-right:0;border-bottom:1px solid #edf1f6;padding:14px}}.phase-num{{grid-row:1/3;margin:0}}.phase strong{{margin:0}}.you-are-here{{position:static;transform:none;grid-column:2;width:max-content;margin-bottom:5px}}.principles{{grid-template-columns:1fr 1fr}}}}@media(max-width:430px){{.quicknav{{grid-template-columns:1fr}}.principles{{grid-template-columns:1fr 1fr}}}}
</style></head><body><div class="wrap"><div class="eyebrow">ADAPTIV TRÄNINGSPLANERING</div><h1>{esc(goal["title"])}</h1><div class="sub">{esc(goal["subtitle"])}</div>
<nav class="quicknav"><a href="{current_url}">Aktuell vecka <b>→</b></a>{upcoming_link}</nav>
<section class="card goal"><div><div class="title">✦ Övergripande mål</div><p>{esc(goal["goal"])}</p></div><div class="mountain"><svg viewBox="0 0 500 280" preserveAspectRatio="none"><path d="M0 255 C70 210 100 225 145 175 C185 130 220 180 260 125 C315 50 345 115 390 55 C425 20 455 55 500 22 L500 280 L0 280Z" fill="#e9eefb"/><path d="M0 280 C80 240 115 245 165 205 C220 160 250 205 300 155 C345 115 390 120 500 70 L500 280Z" fill="#d8e2f8"/><path d="M165 232 C220 220 255 220 292 188 C330 154 322 126 356 116 C390 105 372 82 404 60 C422 48 430 36 441 28" fill="none" stroke="#4938ee" stroke-width="4" stroke-dasharray="9 8"/><circle cx="221" cy="217" r="6" fill="#4938ee"/><circle cx="293" cy="187" r="6" fill="#4938ee"/><circle cx="357" cy="115" r="6" fill="#4938ee"/><line x1="441" y1="28" x2="441" y2="55" stroke="#4938ee" stroke-width="3"/><path d="M441 28 L464 36 L441 44Z" fill="#4938ee"/></svg></div></section>
<section class="card"><div class="status-head"><div class="title">Nuvarande läge</div><div class="pill">✓ {esc(goal["overall_status"])}</div></div>{''.join(disciplines)}</section>
<section class="card"><div class="title">Faser och periodisering</div><div class="phases">{''.join(phases)}</div></section>
<section class="card"><div class="title">Vad som styr planen</div><div class="principles">{principles}</div></section>
<section class="card"><div class="title">Nästa steg</div>{steps}</section>
<footer>Målbilden är kvalitativ och uppdateras när faktisk träning motiverar det. · <a href="/cdn-cgi/access/logout" style="color:inherit">Logga ut</a></footer></div></body></html>'''

    INDEX.write_text(page, encoding="utf-8")
    rendered = INDEX.read_text(encoding="utf-8")
    required = [goal["title"], "Nuvarande läge", "Faser och periodisering", "Du är här", current_url]
    missing = [x for x in required if x not in rendered]
    if missing:
        raise RuntimeError("Huvudsida: validering misslyckades: " + repr(missing))
    print(f"Huvudsida OK: {goal['title']} publicerad; aktuell vecka bevarad på {current_url}")


if __name__ == "__main__":
    main()
