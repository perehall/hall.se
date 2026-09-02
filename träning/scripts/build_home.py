#!/usr/bin/env python3
import html
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from training_brain import resolve_mesocycle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INDEX = ROOT / "index.html"
GOAL = DATA / "goal.json"
STRATEGY = DATA / "training_strategy.json"
PLAN = DATA / "plan.json"
GOAL_DIR = ROOT / "malbild"
GOAL_PAGE = GOAL_DIR / "index.html"

LINK_CSS_MARKER = "/* goal-page-link-v3 */"
LINK_CSS = r'''
/* goal-page-link-v3 */
.goal-page-link{display:flex;justify-content:flex-end;margin:0 0 8px}
.goal-page-link a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;color:#475569;text-decoration:none;font-size:.78rem;font-weight:700;box-shadow:0 5px 14px rgba(15,23,42,.04)}
'''.strip()

MONTH_SHORT = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "maj", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec",
}

ROLE_LABELS = {
    "primary": "Prioriterat nu",
    "secondary": "Sekundärt",
    "maintenance": "Bibehåll / utveckla",
    "protected_capacity": "Skyddad kapacitet",
    "external_load": "Extern belastning",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value):
    return html.escape(str(value))


def compact_period(start_value, end_value):
    start = date.fromisoformat(start_value)
    end = date.fromisoformat(end_value)
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.day}–{end.day} {MONTH_SHORT[start.month]}"
        return f"{start.day} {MONTH_SHORT[start.month]}–{end.day} {MONTH_SHORT[end.month]}"
    return f"{start.day} {MONTH_SHORT[start.month]} {start.year}–{end.day} {MONTH_SHORT[end.month]} {end.year}"


def clean_mesocycle_title(value):
    title = re.sub(r"^Mesocykel\s*·\s*", "", str(value or ""), flags=re.I).strip()
    return title[:1].upper() + title[1:] if title else "Aktuell mesocykel"


def capability_labels(strategy):
    return {
        item.get("key"): item.get("label")
        for item in strategy.get("capability_portfolio") or []
        if item.get("key") and item.get("label")
    }


def hierarchy_rows(strategy):
    horizon = int((strategy.get("decision_policy") or {}).get("horizon_days") or 3)
    return [
        ("Målbild", "Anger vilken atlet och vilka förmågor som ska byggas över tid."),
        ("Mesocykel", "Väljer flerveckors utvecklingsfokus, skyddade stimuli och vad som ska utvärderas."),
        ("Mikrocykel", "Organiserar mesocykelns stimuli till en absorberbar följd av konkreta grundpass."),
        (f"Närtid · {horizon} dagar", "Kontrollerar grundplanen mot faktisk belastning, återhämtning och fasta åtaganden."),
        ("Pass", "Verkställer ett definierat stimulus eller en uttryckligen stödjande roll."),
    ]


def render_hierarchy(strategy):
    rows = []
    for index, (title, body) in enumerate(hierarchy_rows(strategy), start=1):
        rows.append(
            f'<div class="system-step"><span class="system-step-num">{index}</span>'
            f'<div><strong>{esc(title)}</strong><p>{esc(body)}</p></div></div>'
        )
    adaptation = (strategy.get("planning_hierarchy") or {}).get("adaptation_rule") or ""
    calendar = (strategy.get("planning_hierarchy") or {}).get("calendar_role") or ""
    return (
        '<section class="card system-map" data-goal-hierarchy="true">'
        '<div class="title">Så styr målbilden träningen</div>'
        '<div class="system-steps">' + "".join(rows) + '</div>'
        f'<div class="feedback-loop"><strong>Återkoppling</strong><span>{esc(adaptation)}</span></div>'
        f'<div class="calendar-note">{esc(calendar)}</div>'
        '</section>'
    )


def render_mesocycle(strategy, today):
    mesocycle = strategy.get("current_mesocycle") or {}
    state = resolve_mesocycle(strategy, today)
    labels = capability_labels(strategy)
    contract = mesocycle.get("contract") or {}

    rows = []
    for key in ("primary", "secondary", "maintenance", "protected_capacity", "external_load"):
        values = [labels.get(value, value) for value in contract.get(key) or []]
        if not values:
            continue
        rows.append(
            f'<div class="role-row"><span>{esc(ROLE_LABELS[key])}</span>'
            f'<strong>{esc(" · ".join(values))}</strong></div>'
        )

    period = compact_period(mesocycle["start_date"], mesocycle["end_date"])
    evaluation = date.fromisoformat(mesocycle["evaluation_date"])
    meta = (
        f'{period} · {state.get("state") or ""} · '
        f'utvärderas {evaluation.day} {MONTH_SHORT[evaluation.month]}'
    )
    hypothesis = str(mesocycle.get("hypothesis") or "").strip()

    details = ""
    if hypothesis:
        details = (
            '<details class="mesocycle-why"><summary>Varför denna mesocykel?</summary>'
            f'<p>{esc(hypothesis)}</p></details>'
        )

    return (
        '<section class="card current-path" data-current-mesocycle="true">'
        '<div class="section-kicker">Aktuell utvecklingsväg</div>'
        f'<h2>{esc(clean_mesocycle_title(mesocycle.get("title")))}</h2>'
        f'<div class="current-meta">{esc(meta)}</div>'
        f'<p class="current-purpose">{esc(mesocycle.get("goal_contribution") or "")}</p>'
        '<div class="role-list">' + "".join(rows) + '</div>'
        + details +
        '</section>'
    )


def render_decision_principles(strategy):
    policy = strategy.get("decision_policy") or {}
    items = []
    if policy.get("concrete_near_term_plan_by_default"):
        items.append(("Konkret grundplan", "De närmaste passen ska normalt vara konkreta, inte lämnas öppna utan skäl."))
    if policy.get("adjust_planned_session_only_when_new_evidence_justifies"):
        items.append(("Ändra på faktisk information", "Ett planerat pass ändras först när ny belastning, återhämtning eller andra omständigheter motiverar det."))
    if policy.get("prioritize_continuity_over_max_content"):
        items.append(("Kontinuitet före maxinnehåll", "Systemet prioriterar absorberbar belastning framför att fylla varje möjlig träningslucka."))
    if policy.get("protect_mesocycle_stimuli_before_optional_training"):
        items.append(("Skydda utvecklingsstimuli", "Prioriterade och skyddade förmågor går före valfri extra träning."))
    if policy.get("normal_variation_is_absorbed_by_plan"):
        items.append(("Normal variation absorberas", "En enskild seg eller ovanligt pigg dag ska inte automatiskt skriva om planen."))

    rows = "".join(
        f'<div class="decision-principle"><strong>{esc(title)}</strong><span>{esc(body)}</span></div>'
        for title, body in items
    )
    return (
        '<section class="card decision-rules">'
        '<div class="title">Beslutsprinciper</div>'
        f'<div class="decision-list">{rows}</div>'
        '</section>'
    )


def build_goal_page(goal, strategy, today):
    north_star = strategy.get("north_star") or goal.get("goal") or ""
    if north_star != goal.get("goal"):
        raise RuntimeError("Målbild: kanonisk goal och strategi.north_star avviker")

    hierarchy = render_hierarchy(strategy)
    current_path = render_mesocycle(strategy, today)
    decision_rules = render_decision_principles(strategy)

    page = f'''<!doctype html><html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f5f7fb"><title>{esc(goal["title"])} · Träningsplan</title>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#2563eb;--shadow:0 8px 24px rgba(15,23,42,.06)}}*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);line-height:1.45}}.wrap{{width:min(100%,720px);margin:auto;padding:20px 16px 56px}}.eyebrow{{font-size:.76rem;font-weight:700;color:#64748b;margin-bottom:6px}}h1{{font-size:clamp(2rem,8vw,3.2rem);line-height:1;margin:0 0 8px;letter-spacing:-.04em}}.sub{{color:#64748b;font-size:.94rem;line-height:1.45}}.goal-back-row{{display:flex;justify-content:flex-end;margin:12px 0 4px}}.goal-back-row a{{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;color:#475569;text-decoration:none;font-size:.78rem;font-weight:700;box-shadow:0 5px 14px rgba(15,23,42,.04)}}.card{{background:#fff;border:1px solid var(--line);box-shadow:var(--shadow);border-radius:20px;padding:17px;margin:12px 0}}.title{{font-size:1.06rem;font-weight:700;margin-bottom:12px}}.goal p{{margin:0;color:#334155;font-size:.96rem;line-height:1.5}}.goal-note{{margin-top:8px!important;color:#64748b!important;font-size:.8rem!important}}
.system-steps{{display:grid;gap:0}}.system-step{{display:grid;grid-template-columns:30px 1fr;gap:10px;padding:10px 0;border-top:1px solid #edf1f6}}.system-step:first-child{{border-top:0;padding-top:0}}.system-step-num{{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;background:#eff6ff;color:#1d4ed8;font-size:.72rem;font-weight:700}}.system-step strong{{display:block;font-size:.9rem}}.system-step p{{margin:2px 0 0;color:#64748b;font-size:.82rem;line-height:1.42}}.feedback-loop{{margin-top:11px;padding:10px 11px;border-radius:12px;background:#f8fafc;border:1px solid #e2e8f0}}.feedback-loop strong{{display:block;font-size:.75rem;color:#475569;margin-bottom:3px}}.feedback-loop span{{display:block;color:#475569;font-size:.8rem;line-height:1.42}}.calendar-note{{margin-top:8px;color:#94a3b8;font-size:.73rem;line-height:1.4}}
.section-kicker{{font-size:.74rem;color:#64748b;font-weight:600;margin-bottom:3px}}.current-path h2{{margin:0;font-size:1.12rem;line-height:1.3;letter-spacing:-.01em}}.current-meta{{margin-top:3px;color:#64748b;font-size:.8rem}}.current-purpose{{margin:10px 0 0;color:#334155;font-size:.9rem;line-height:1.48}}.role-list{{margin-top:11px;border-top:1px solid #edf1f6}}.role-row{{display:grid;grid-template-columns:120px 1fr;gap:12px;padding:9px 0;border-bottom:1px solid #edf1f6;align-items:start}}.role-row span{{color:#64748b;font-size:.76rem}}.role-row strong{{font-size:.8rem;line-height:1.42;font-weight:650}}.mesocycle-why{{margin-top:9px}}.mesocycle-why>summary{{cursor:pointer;list-style:none;color:#64748b;font-size:.78rem;font-weight:600}}.mesocycle-why>summary::-webkit-details-marker{{display:none}}.mesocycle-why>summary:after{{content:" +"}}.mesocycle-why[open]>summary:after{{content:" −"}}.mesocycle-why p{{margin:7px 0 0;color:#475569;font-size:.82rem;line-height:1.45}}
.decision-list{{display:grid;gap:0}}.decision-principle{{padding:9px 0;border-top:1px solid #edf1f6}}.decision-principle:first-child{{border-top:0;padding-top:0}}.decision-principle strong{{display:block;font-size:.86rem}}.decision-principle span{{display:block;margin-top:2px;color:#64748b;font-size:.8rem;line-height:1.42}}.goal-change{{background:#0f172a;color:#fff}}.goal-change .title{{margin-bottom:7px}}.goal-change p{{margin:0;color:#cbd5e1;font-size:.86rem;line-height:1.48}}footer{{color:#64748b;font-size:.78rem;padding-top:22px;text-align:center}}
@media(max-width:620px){{.wrap{{padding:20px 13px 56px}}.role-row{{grid-template-columns:1fr;gap:3px}}}}
</style></head><body><div class="wrap">
<header><div class="eyebrow">Träningsplan</div><h1>{esc(goal["title"])}</h1><div class="sub">Långsiktig riktning för hur systemet väljer mesocykel, mikrocykel och pass.</div></header>
<div class="goal-back-row"><a href="/träning/">← Veckoplan</a></div>
<section class="card goal"><div class="title">Riktningen</div><p>{esc(north_star)}</p><p class="goal-note">Målbilden är överordnad. Ändras den ska den aktuella utvecklingsvägen omprövas.</p></section>
{hierarchy}
{current_path}
{decision_rules}
<section class="card goal-change"><div class="title">När målbilden ändras</div><p>{esc((strategy.get("goal_contract") or {}).get("principle") or "")}</p></section>
<footer>Målbilden är kanonisk riktning, inte ett prestationsbetyg. · <a href="/cdn-cgi/access/logout" style="color:inherit">Logga ut</a></footer></div></body></html>'''

    GOAL_DIR.mkdir(parents=True, exist_ok=True)
    GOAL_PAGE.write_text(page, encoding="utf-8")

    rendered = GOAL_PAGE.read_text(encoding="utf-8")
    required = [
        goal["title"],
        'data-goal-hierarchy="true"',
        'data-current-mesocycle="true"',
        "Så styr målbilden träningen",
        "Aktuell utvecklingsväg",
        "Beslutsprinciper",
        "När målbilden ändras",
        "← Veckoplan",
        clean_mesocycle_title((strategy.get("current_mesocycle") or {}).get("title")),
    ]
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError("Målbild: validering misslyckades: " + repr(missing))
    forbidden = ["mountain-phase-point", "Faser och periodisering", "Kvalitativ utvecklingsstatus"]
    leaked = [item for item in forbidden if item in rendered]
    if leaked:
        raise RuntimeError("Målbild: gammal fas/status-UX finns kvar: " + repr(leaked))


def inject_goal_link():
    page = INDEX.read_text(encoding="utf-8")
    page = re.sub(r'<div class="goal-home-link">.*?</div>', '', page, flags=re.S)
    page = re.sub(r'<div class="goal-page-link">.*?</div>', '', page, flags=re.S)
    page = re.sub(r'/\* goal-page-link-v[12] \*/.*?(?=(?:/\*|</style>))', '', page, flags=re.S)
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


def main():
    goal = load(GOAL)
    strategy = load(STRATEGY)
    plan = load(PLAN)
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today = datetime.now(ZoneInfo(timezone_name)).date()
    build_goal_page(goal, strategy, today)
    inject_goal_link()
    print("Målbild OK: sidan speglar faktisk planeringshierarki och aktuell mesocykel.")


if __name__ == "__main__":
    main()
