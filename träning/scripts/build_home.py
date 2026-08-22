#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INDEX = ROOT / "index.html"
GOAL = DATA / "goal.json"
GOAL_DIR = ROOT / "malbild"
GOAL_PAGE = GOAL_DIR / "index.html"

COLORS = {
    "run": ("#22a06b", "#e7f7ef", "↗"),
    "mtb": ("#8b5cf6", "#f1ebff", "◇"),
    "swim": ("#4f86f7", "#eaf2ff", "≈"),
    "strength": ("#f2a33b", "#fff2df", "＋"),
}

LINK_CSS_MARKER = "/* goal-page-link-v2 */"
LINK_CSS = r'''
/* goal-page-link-v2 */
.goal-page-link{display:flex;justify-content:flex-end;margin:0 0 8px}.goal-page-link a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #ddd6fe;border-radius:12px;background:#faf5ff;color:#5b21b6;text-decoration:none;font-size:.78rem;font-weight:900;box-shadow:0 5px 14px rgba(76,29,149,.05)}
'''.strip()

PHASE_POINTS = [
    (18.5, 81.5),
    (39.5, 73.0),
    (58.5, 57.0),
    (68.5, 35.0),
    (84.0, 13.5),
]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value):
    return html.escape(str(value))


def progress(level, color):
    level = max(0, min(5, int(level)))
    return '<div class="progress" aria-label="Kvalitativ utvecklingsstatus">' + ''.join(
        f'<span style="background:{color if i < level else "#e7ebf2"}"></span>'
        for i in range(5)
    ) + '</div>'


def inject_goal_link():
    page = INDEX.read_text(encoding="utf-8")
    page = re.sub(r'<div class="goal-home-link">.*?</div>', '', page, flags=re.S)
    page = re.sub(r'<div class="goal-page-link">.*?</div>', '', page, flags=re.S)
    if LINK_CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Målbildslänk: kunde inte hitta </style>")
        page = page.replace("</style>", LINK_CSS + "\n</style>", 1)

    link = '<div class="goal-page-link"><a href="/träning/malbild/">Målbild 2027 <span>→</span></a></div>'
    nav = page.find('<nav class="week-nav"')
    if nav < 0:
        raise RuntimeError("Målbildslänk: veckonavigering saknas")
    page = page[:nav] + link + "\n" + page[nav:]
    INDEX.write_text(page, encoding="utf-8")


def mountain_phase_links(phases, current_phase):
    if len(phases) != len(PHASE_POINTS):
        raise RuntimeError(
            f"Målbild: bergsvisualiseringen har {len(PHASE_POINTS)} punkter men periodiseringen har {len(phases)} faser"
        )
    links = []
    for phase, (x, y) in zip(phases, PHASE_POINTS):
        number = int(phase["number"])
        state = "current" if number == current_phase else "done" if number < current_phase else "future"
        name = esc(phase["name"])
        description = esc(phase["description"])
        current_note = '<span class="phase-point-current">Du är här</span>' if state == "current" else ""
        links.append(
            f'''<a class="mountain-phase-point {state}" href="#fas-{number}" style="--x:{x}%;--y:{y}%" data-phase="{number}" aria-label="Fas {number}: {name}. {description}">
              <span class="phase-point-dot"><span>{number}</span></span>
              {current_note}
              <span class="mountain-tooltip" role="tooltip"><strong>Fas {number} · {name}</strong><span>{description}</span><small>Klicka för att gå till fasen</small></span>
            </a>'''
        )
    return "".join(links)


def build_goal_page(goal):
    disciplines = []
    for item in goal.get("disciplines", []):
        key = item["key"]
        color, soft, icon = COLORS.get(key, ("#4f46e5", "#eef2ff", "•"))
        disciplines.append(f'''<div class="status-row">
          <div class="sport-icon" style="background:{soft};color:{color}">{icon}</div>
          <div class="sport-name">{esc(item["label"])}</div>
          {progress(item.get("level", 0), color)}
          <div class="status-note" style="color:{color}">{esc(item["status"])}</div>
        </div>''')

    phases_data = goal.get("phases", [])
    current_phase = int(goal.get("current_phase", 1))
    phases = []
    for phase in phases_data:
        number = int(phase["number"])
        cls = "phase active" if number == current_phase else "phase done" if number < current_phase else "phase"
        tag = '<div class="you-are-here">Du är här</div>' if number == current_phase else ''
        phases.append(f'''<article class="{cls}" id="fas-{number}" tabindex="-1" data-phase-card="{number}">{tag}<div class="phase-num">{number}</div>
          <strong>{esc(phase["name"])}</strong><span>{esc(phase["description"])}</span></article>''')

    mountain_links = mountain_phase_links(phases_data, current_phase)
    principles = ''.join(
        f'<div class="principle"><div class="picon">{i+1}</div><span>{esc(text)}</span></div>'
        for i, text in enumerate(goal.get("principles", []))
    )
    steps = ''.join(
        f'<div class="next-row"><span class="step-dot">{i+1}</span><span>{esc(text)}</span></div>'
        for i, text in enumerate(goal.get("next_steps", []))
    )

    page = f'''<!doctype html><html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f5f7fb"><title>{esc(goal["title"])} · Adaptiv träningsplanering</title>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#4938ee;--shadow:0 10px 28px rgba(15,23,42,.06)}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth;scroll-padding-top:18px}}body{{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);line-height:1.45}}.wrap{{width:min(100%,920px);margin:auto;padding:28px 18px 60px}}.top{{display:flex;align-items:center;gap:14px}}.eyebrow{{font-size:.78rem;font-weight:900;letter-spacing:.13em;text-transform:uppercase;color:var(--accent)}}h1{{font-size:clamp(3rem,9vw,5rem);line-height:.98;letter-spacing:-.055em;margin:20px 0 8px}}.sub{{color:var(--muted);font-weight:650;font-size:1rem}}.goal-back-row{{display:flex;justify-content:flex-end;margin:12px 0 4px}}.goal-back-row a{{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;color:#475569;text-decoration:none;font-size:.78rem;font-weight:900;box-shadow:0 5px 14px rgba(15,23,42,.04)}}.card{{background:#fff;border:1px solid var(--line);box-shadow:var(--shadow);border-radius:22px;padding:22px;margin:18px 0}}.title{{font-size:1.18rem;font-weight:900;margin-bottom:16px}}.goal{{display:grid;grid-template-columns:1.02fr .98fr;gap:20px;align-items:stretch;overflow:visible}}.goal-copy{{padding:4px 0}}.goal p{{font-size:1.02rem;color:#334155;margin:0}}
.mountain{{min-height:300px;position:relative;isolation:isolate}}.mountain-art{{position:absolute;inset:0;overflow:hidden;border-radius:18px;background:radial-gradient(circle at 82% 18%,rgba(99,102,241,.11),transparent 22%),linear-gradient(180deg,#fcfdff,#f4f6fd)}}.mountain-art svg{{position:absolute;inset:0;width:100%;height:100%}}.mountain-caption{{position:absolute;left:14px;bottom:11px;color:#64748b;font-size:.68rem;font-weight:750;z-index:3;pointer-events:none}}
.mountain-phase-point{{position:absolute;left:var(--x);top:var(--y);z-index:8;width:34px;height:34px;transform:translate(-50%,-50%);display:grid;place-items:center;text-decoration:none;outline:none}}.phase-point-dot{{width:19px;height:19px;border-radius:50%;display:grid;place-items:center;background:#fff;border:2.5px solid #6d63ed;box-shadow:0 3px 10px rgba(67,56,202,.18);transition:transform .16s ease,box-shadow .16s ease,background .16s ease,border-color .16s ease}}.phase-point-dot span{{font-size:.52rem;font-weight:950;color:#5148d8;line-height:1}}.mountain-phase-point.done .phase-point-dot{{border-color:#63a984;background:#f6fffa}}.mountain-phase-point.done .phase-point-dot span{{color:#34805a}}.mountain-phase-point.current .phase-point-dot{{width:25px;height:25px;background:#5146e5;border-color:#fff;box-shadow:0 0 0 5px rgba(81,70,229,.15),0 8px 20px rgba(81,70,229,.3)}}.mountain-phase-point.current .phase-point-dot span{{color:#fff;font-size:.62rem}}.mountain-phase-point.future .phase-point-dot{{border-color:#847bf1;background:#fff}}.mountain-phase-point:hover .phase-point-dot,.mountain-phase-point:focus-visible .phase-point-dot{{transform:scale(1.22);box-shadow:0 0 0 5px rgba(81,70,229,.12),0 8px 20px rgba(81,70,229,.25)}}.mountain-phase-point:focus-visible{{outline:2px solid #4338ca;outline-offset:4px;border-radius:50%}}.phase-point-current{{position:absolute;left:50%;bottom:29px;transform:translateX(-50%);white-space:nowrap;background:#5146e5;color:#fff;border-radius:999px;padding:3px 7px;font-size:.57rem;font-weight:900;box-shadow:0 5px 14px rgba(81,70,229,.22)}}
.mountain-tooltip{{position:absolute;left:50%;bottom:37px;width:210px;transform:translate(-50%,6px);padding:10px 11px;border-radius:12px;background:rgba(15,23,42,.96);color:#fff;box-shadow:0 12px 28px rgba(15,23,42,.22);opacity:0;visibility:hidden;pointer-events:none;transition:opacity .14s ease,transform .14s ease;text-align:left;line-height:1.25}}.mountain-tooltip strong,.mountain-tooltip span,.mountain-tooltip small{{display:block}}.mountain-tooltip strong{{font-size:.75rem;margin-bottom:4px}}.mountain-tooltip span{{font-size:.69rem;color:#dbe4f4}}.mountain-tooltip small{{font-size:.59rem;color:#a5b4fc;margin-top:6px;font-weight:750}}.mountain-phase-point:hover .mountain-tooltip,.mountain-phase-point:focus-visible .mountain-tooltip{{opacity:1;visibility:visible;transform:translate(-50%,0)}}.mountain-phase-point:nth-of-type(1) .mountain-tooltip{{left:-10px;transform:translate(0,6px)}}.mountain-phase-point:nth-of-type(1):hover .mountain-tooltip,.mountain-phase-point:nth-of-type(1):focus-visible .mountain-tooltip{{transform:translate(0,0)}}.mountain-phase-point:nth-of-type(5) .mountain-tooltip{{left:auto;right:-10px;transform:translate(0,6px)}}.mountain-phase-point:nth-of-type(5):hover .mountain-tooltip,.mountain-phase-point:nth-of-type(5):focus-visible .mountain-tooltip{{transform:translate(0,0)}}
.status-head{{display:flex;justify-content:space-between;align-items:center;gap:12px}}.pill{{padding:9px 13px;border-radius:13px;background:#e7f7ef;color:#198754;border:1px solid #a7dfc4;font-weight:900}}.qualitative{{color:#94a3b8;font-size:.72rem;margin:-7px 0 10px}}.status-row{{display:grid;grid-template-columns:48px minmax(145px,1fr) minmax(180px,1.25fr) 150px;gap:14px;align-items:center;padding:11px 0;border-top:1px solid #edf1f6}}.sport-icon{{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;font-size:1.25rem;font-weight:900}}.sport-name{{font-weight:800}}.progress{{display:grid;grid-template-columns:repeat(5,1fr);gap:4px}}.progress span{{height:8px;border-radius:99px}}.status-note{{font-weight:850;font-size:.9rem}}.phases{{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid #edf1f6;border-radius:18px;overflow:visible;margin-top:34px}}.phase{{position:relative;min-height:174px;padding:24px 12px 16px;text-align:center;border-right:1px solid #edf1f6;background:#fff;transition:box-shadow .18s ease,transform .18s ease}}.phase:last-child{{border-right:0}}.phase.done{{background:linear-gradient(180deg,#f1fbf5,#f8fcfa)}}.phase.active{{background:linear-gradient(180deg,#eef4ff,#f8faff)}}.phase.phase-pulse{{box-shadow:inset 0 0 0 3px rgba(79,70,229,.32),0 12px 28px rgba(79,70,229,.12);transform:translateY(-2px)}}.phase:focus{{outline:3px solid rgba(79,70,229,.25);outline-offset:3px}}.phase-num{{width:40px;height:40px;margin:0 auto 14px;border:2px solid #d5dce8;border-radius:50%;display:grid;place-items:center;font-weight:900;background:#fff}}.phase.done .phase-num{{border-color:#22a06b;color:#168354}}.phase.active .phase-num{{background:#4f74ef;border-color:#4f74ef;color:#fff;box-shadow:0 8px 18px #d8e1ff}}.phase strong{{display:block;font-size:.92rem;margin-bottom:6px}}.phase span{{display:block;color:#475569;font-size:.82rem;line-height:1.3}}.you-are-here{{position:absolute;top:-25px;left:50%;transform:translateX(-50%);white-space:nowrap;background:#fff;color:#3765ec;border:1.5px solid #6c91f7;border-radius:8px;padding:3px 8px;font-size:.72rem;font-weight:900}}.principles{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}}.principle{{min-height:124px;border:1px solid var(--line);border-radius:16px;padding:14px 10px;text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px}}.picon{{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#f0edff;color:var(--accent);font-weight:900}}.principle span{{font-size:.78rem;font-weight:800;line-height:1.25}}.next-row{{display:grid;grid-template-columns:38px 1fr;gap:12px;align-items:center;padding:14px 0;border-top:1px solid #edf1f6;font-weight:760}}.next-row:first-child{{border-top:0}}.step-dot{{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#eef2ff;color:#4f46e5;font-weight:900}}footer{{color:var(--muted);font-size:.8rem;padding-top:22px;text-align:center}}
@media(max-width:700px){{.wrap{{padding:22px 14px 54px}}.goal{{grid-template-columns:1fr}}.mountain{{min-height:270px;margin-top:2px}}.mountain-tooltip{{display:none}}.mountain-phase-point{{width:42px;height:42px}}.phase-point-dot{{width:21px;height:21px}}.mountain-phase-point.current .phase-point-dot{{width:27px;height:27px}}.status-row{{grid-template-columns:44px 1fr}}.status-row .progress,.status-row .status-note{{grid-column:2}}.phases{{grid-template-columns:1fr;margin-top:18px;overflow:hidden}}.phase{{min-height:auto;text-align:left;display:grid;grid-template-columns:46px 1fr;column-gap:12px;align-items:center;border-right:0;border-bottom:1px solid #edf1f6;padding:14px}}.phase-num{{grid-row:1/3;margin:0}}.phase strong{{margin:0}}.you-are-here{{position:static;transform:none;grid-column:2;width:max-content;margin-bottom:5px}}.principles{{grid-template-columns:1fr 1fr}}}}@media(max-width:430px){{.principles{{grid-template-columns:1fr 1fr}}}}@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}.phase,.phase-point-dot,.mountain-tooltip{{transition:none!important}}}}
</style></head><body><div class="wrap"><div class="top"><div class="eyebrow">ADAPTIV TRÄNINGSPLANERING</div></div><h1>{esc(goal["title"])}</h1><div class="sub">{esc(goal["subtitle"])}</div>
<div class="goal-back-row"><a href="/träning/">← Veckoplan</a></div>
<section class="card goal"><div class="goal-copy"><div class="title">✦ Övergripande mål</div><p>{esc(goal["goal"])}</p></div><div class="mountain" aria-label="Interaktiv visualisering av periodiseringens fem faser"><div class="mountain-art" aria-hidden="true"><svg viewBox="0 0 560 300" preserveAspectRatio="none">
<defs><linearGradient id="ridge1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4f5fb"/><stop offset="1" stop-color="#e9edf8"/></linearGradient><linearGradient id="ridge2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ebeff9"/><stop offset="1" stop-color="#dce4f6"/></linearGradient><linearGradient id="ridge3" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e1e7f6"/><stop offset="1" stop-color="#ced9f2"/></linearGradient><linearGradient id="trail" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#6960e9"/><stop offset="1" stop-color="#4938ee"/></linearGradient></defs>
<path d="M-20 250 C45 238 77 214 118 207 C153 201 174 162 204 158 C237 154 248 181 278 154 C308 128 329 104 353 111 C378 117 391 82 418 74 C448 65 456 82 482 54 C504 31 530 34 580 8 L580 320 L-20 320Z" fill="url(#ridge1)"/>
<path d="M-20 274 C52 256 89 237 132 223 C170 211 188 189 220 190 C249 191 269 167 294 155 C320 143 336 163 362 142 C389 120 403 104 428 109 C456 114 474 89 502 80 C525 73 547 78 580 62 L580 320 L-20 320Z" fill="url(#ridge2)"/>
<path d="M-20 300 C50 286 91 267 139 251 C180 237 205 225 239 222 C278 219 295 196 326 188 C360 179 381 186 408 168 C441 146 466 143 493 132 C522 120 546 121 580 109 L580 320 L-20 320Z" fill="url(#ridge3)"/>
<path d="M104 250 C157 246 203 236 245 219 C286 202 310 186 328 166 C345 147 367 150 383 132 C400 113 389 96 372 90 C357 85 360 70 378 61 C401 50 425 42 470 28" fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round" opacity=".85"/>
<path d="M104 250 C157 246 203 236 245 219 C286 202 310 186 328 166 C345 147 367 150 383 132 C400 113 389 96 372 90 C357 85 360 70 378 61 C401 50 425 42 470 28" fill="none" stroke="url(#trail)" stroke-width="3.4" stroke-linecap="round" stroke-dasharray="8 9"/>
<circle cx="470" cy="28" r="22" fill="#eeecff" opacity=".72"/><line x1="470" y1="18" x2="470" y2="49" stroke="#4938ee" stroke-width="3"/><path d="M470 18 L496 26 L470 35Z" fill="#4938ee"/>
</svg></div>{mountain_links}<div class="mountain-caption">Faserna följer samma data som periodiseringen nedan</div></div></section>
<section class="card"><div class="status-head"><div class="title">Nuvarande läge</div><div class="pill">✓ {esc(goal["overall_status"])}</div></div><div class="qualitative">Kvalitativ riktning – inte ett exakt prestationsindex.</div>{''.join(disciplines)}</section>
<section class="card" id="periodisering"><div class="title">Faser och periodisering</div><div class="phases">{''.join(phases)}</div></section>
<section class="card"><div class="title">Vad som styr planen</div><div class="principles">{principles}</div></section>
<section class="card"><div class="title">Nästa steg</div>{steps}</section>
<footer>Målbilden är kvalitativ och uppdateras när faktisk träning motiverar det. · <a href="/cdn-cgi/access/logout" style="color:inherit">Logga ut</a></footer></div>
<script>
(() => {{
  const points = Array.from(document.querySelectorAll('.mountain-phase-point'));
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  points.forEach(point => {{
    point.addEventListener('click', event => {{
      const target = document.getElementById(`fas-${{point.dataset.phase}}`);
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({{behavior: reducedMotion ? 'auto' : 'smooth', block: 'center'}});
      window.history.replaceState(null, '', `#fas-${{point.dataset.phase}}`);
      target.focus({{preventScroll:true}});
      target.classList.remove('phase-pulse');
      void target.offsetWidth;
      target.classList.add('phase-pulse');
      window.setTimeout(() => target.classList.remove('phase-pulse'), 1400);
    }});
  }});
}})();
</script></body></html>'''

    GOAL_DIR.mkdir(parents=True, exist_ok=True)
    GOAL_PAGE.write_text(page, encoding="utf-8")

    rendered = GOAL_PAGE.read_text(encoding="utf-8")
    required = [
        goal["title"], "Nuvarande läge", "Faser och periodisering",
        "mountain-phase-point", "mountain-tooltip", "data-phase-card", "← Veckoplan",
    ]
    for phase in phases_data:
        number = int(phase["number"])
        required.extend([f'id="fas-{number}"', f'data-phase="{number}"', esc(phase["name"])])
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError("Målbild: validering misslyckades: " + repr(missing))


def main():
    goal = load(GOAL)
    build_goal_page(goal)
    inject_goal_link()
    print("Målbild OK: interaktiv fasvisualisering byggd från samma periodiseringsdata och länkad från veckoplanen.")


if __name__ == "__main__":
    main()
