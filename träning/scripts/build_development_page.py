#!/usr/bin/env python3
"""Render the separate Mål & utveckling transparency page."""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from development_roadmap import build_development_roadmap


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TARGET = ROOT / "utveckling" / "index.html"

MONTHS = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "maj", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec",
}

ROLE_ORDER = ("primary", "secondary", "maintenance", "protected_capacity", "external_load", "supporting")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def e(value):
    return html.escape(str(value or ""))


def fmt_date(value):
    if not value:
        return "Ej daterat"
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return f"{day.day} {MONTHS[day.month]} {day.year}"


def capability_lookup(roadmap):
    return {row["key"]: row["label"] for row in roadmap.get("capabilities") or []}


def goal_card(goal, contribution_lookup):
    target_date = goal.get("target_date")
    date_label = fmt_date(target_date) if target_date else "Pågående"
    meta = []
    if goal.get("target"):
        meta.append(str(goal["target"]))
    meta.append(date_label)
    contribution = goal.get("current_block_contribution")
    tradeoff = goal.get("current_block_tradeoff")
    details = ""
    if contribution:
        details += f'<div class="goal-link"><span>Aktuellt block bidrar genom</span><p>{e(contribution)}</p></div>'
    if tradeoff:
        details += f'<div class="goal-link muted"><span>Medveten avvägning</span><p>{e(tradeoff)}</p></div>'
    return (
        '<article class="goal-card">'
        f'<div class="eyebrow">{"Planeringsmål" if goal.get("source") == "planning_goal" else "Ditt mål"}</div>'
        f'<h3>{e(goal.get("label"))}</h3>'
        f'<p class="meta">{" · ".join(e(x) for x in meta)}</p>'
        f'{details}</article>'
    )


def declared_goal_card(goal):
    date_text = fmt_date(goal.get("target_date")) if goal.get("target_date") else "Ingen fast måldag"
    return (
        '<article class="declared-goal">'
        f'<p>{e(goal.get("label"))}</p>'
        f'<span>{e(date_text)}</span>'
        '</article>'
    )


def timeline_item(item):
    kind = item.get("kind")
    badge = {
        "active_block": "Aktivt",
        "checkpoint": "Checkpoint",
        "decision_window": "Preliminär beslutspunkt",
        "goal_event": "Fast måldag",
    }.get(kind, "Planerat")
    dates = fmt_date(item.get("date"))
    if item.get("end_date"):
        dates += " – " + fmt_date(item.get("end_date"))
    boundary = ""
    if kind == "decision_window":
        boundary = '<p class="boundary">Omprövning av specificitet – inte ett löfte om uppnådd kapacitet.</p>'
    return (
        f'<li class="timeline-item kind-{e(kind)}">'
        '<span class="timeline-dot" aria-hidden="true"></span>'
        '<div class="timeline-body">'
        f'<div class="timeline-top"><span class="badge">{e(badge)}</span><time>{e(dates)}</time></div>'
        f'<h3>{e(item.get("title"))}</h3>'
        f'<p>{e(item.get("description"))}</p>{boundary}'
        '</div></li>'
    )


def evidence_label(state):
    return {
        "absorbed": "Absorberad nivå dokumenterad",
        "tolerated": "Tolererad nivå dokumenterad",
        "demonstrated": "Genomförd nivå dokumenterad",
        "observed": "Observerad historik finns",
        "missing": "Baslinje saknas",
    }.get(state, "Underlag saknas")


def render_page(strategy, policy, athlete_state):
    roadmap = strategy.get("development_roadmap")
    if not isinstance(roadmap, dict) or roadmap.get("goal_basis_hash") != (strategy.get("goal_contract") or {}).get("goal_hash"):
        roadmap = build_development_roadmap(strategy, policy, athlete_state)

    labels = capability_lookup(roadmap)
    block = roadmap.get("active_block") or {}
    canonical_goals = roadmap.get("canonical_goals") or []
    declared_goals = roadmap.get("declared_profile_goals") or []

    goal_html = "".join(goal_card(goal, {}) for goal in canonical_goals)
    declared_html = "".join(declared_goal_card(goal) for goal in declared_goals)
    if not declared_html:
        declared_html = '<p class="empty">Inga separata fria mål finns sparade i den aktiva träningsprofilen.</p>'

    timeline_html = "".join(timeline_item(item) for item in roadmap.get("timeline") or [])

    role_groups = []
    for role in ROLE_ORDER:
        rows = [row for row in roadmap.get("capabilities") or [] if row.get("role") == role]
        if not rows:
            continue
        items = "".join(
            '<div class="cap-row">'
            f'<div><strong>{e(row.get("label"))}</strong><span>{e(row.get("role_label"))}</span></div>'
            f'<div class="cap-evidence state-{e(row.get("evidence_state"))}"><strong>{e(evidence_label(row.get("evidence_state")))}</strong>'
            f'<span>{e(row.get("evidence_summary"))}</span></div>'
            '</div>'
            for row in rows
        )
        role_groups.append(items)
    capabilities_html = "".join(role_groups)

    contribution_rows = []
    goal_by_id = {goal.get("id"): goal.get("label") for goal in canonical_goals}
    for row in block.get("goal_contributions") or []:
        contribution_rows.append(
            '<article class="contribution">'
            f'<span>{e(goal_by_id.get(row.get("goal_id"), row.get("goal_id")))}</span>'
            f'<p>{e(row.get("contribution"))}</p>'
            '</article>'
        )
    contributions_html = "".join(contribution_rows)

    primary = " · ".join(labels.get(key, key) for key in block.get("primary_capabilities") or [])
    secondary = " · ".join(labels.get(key, key) for key in block.get("secondary_capabilities") or [])
    protected = " · ".join(labels.get(key, key) for key in block.get("protected_capabilities") or [])

    signals = "".join(f"<li>{e(item)}</li>" for item in block.get("success_signals") or [])

    css = """
:root{color-scheme:light;--bg:#f7f7f8;--card:#fff;--text:#151516;--secondary:#45454a;--muted:#77777f;--line:#e6e6e9;--soft:#f1f1f3;--accent:#4c5fd5;--green:#287a50}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.shell{width:min(980px,100%);margin:0 auto;padding:26px 22px 72px}.topnav{display:flex;gap:18px;justify-content:flex-end;margin-bottom:48px;font-size:.82rem}.topnav a{color:var(--muted);text-decoration:none}
.hero{max-width:780px;margin-bottom:44px}.kicker,.eyebrow{color:var(--muted);font-size:.68rem;font-weight:750;text-transform:uppercase;letter-spacing:.08em}.hero h1{font-size:clamp(2rem,6vw,3.8rem);line-height:1.02;letter-spacing:-.055em;margin:8px 0 18px}.hero>p{font-size:1.08rem;line-height:1.55;color:var(--secondary);max-width:720px}.notice{margin-top:22px;padding:14px 16px;border-left:3px solid var(--accent);background:#fff;border-radius:0 12px 12px 0;color:var(--secondary);font-size:.86rem;line-height:1.5}
section{margin-top:50px}.section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:16px}.section-head h2{font-size:1.45rem;letter-spacing:-.025em;margin:0}.section-head p{margin:0;color:var(--muted);font-size:.8rem}
.goal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.goal-card,.block,.capabilities,.profile-goals{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px}.goal-card h3{font-size:1.2rem;letter-spacing:-.02em;margin:7px 0 7px}.meta{color:var(--muted);font-size:.78rem;margin:0}.goal-link{margin-top:17px;padding-top:14px;border-top:1px solid var(--line)}.goal-link span,.contribution span{color:var(--muted);font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}.goal-link p,.contribution p{margin:6px 0 0;color:var(--secondary);line-height:1.48;font-size:.86rem}.goal-link.muted p{color:var(--muted)}
.profile-goals{margin-top:12px;padding-top:14px;padding-bottom:14px}.profile-goals h3{font-size:.8rem;margin:0 0 9px;color:var(--muted)}.declared-goal{display:flex;justify-content:space-between;gap:18px;padding:10px 0;border-top:1px solid var(--line)}.declared-goal:first-of-type{border-top:0}.declared-goal p{margin:0;font-size:.9rem}.declared-goal span{color:var(--muted);font-size:.76rem;white-space:nowrap}.empty{color:var(--muted);font-size:.82rem;margin:4px 0}
.timeline{list-style:none;margin:0;padding:0 0 0 10px}.timeline-item{position:relative;display:grid;grid-template-columns:24px 1fr;gap:14px;padding-bottom:18px}.timeline-item:before{content:"";position:absolute;left:11px;top:19px;bottom:-3px;width:1px;background:var(--line)}.timeline-item:last-child:before{display:none}.timeline-dot{z-index:1;margin-top:15px;width:9px;height:9px;border-radius:50%;background:#b8b8bf;border:2px solid var(--bg);box-shadow:0 0 0 1px #b8b8bf}.kind-active_block .timeline-dot{background:var(--accent);box-shadow:0 0 0 1px var(--accent)}.kind-goal_event .timeline-dot{background:var(--text);box-shadow:0 0 0 1px var(--text)}
.timeline-body{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px 18px}.timeline-top{display:flex;justify-content:space-between;gap:14px;align-items:center}.badge{font-size:.64rem;font-weight:750;text-transform:uppercase;letter-spacing:.04em;color:var(--accent)}time{color:var(--muted);font-size:.73rem}.timeline-body h3{font-size:1rem;margin:8px 0 5px}.timeline-body p{margin:0;color:var(--secondary);font-size:.82rem;line-height:1.48}.timeline-body .boundary{margin-top:8px;color:var(--muted);font-size:.72rem}
.block h3{font-size:1.16rem;margin:4px 0 7px}.block-date{color:var(--muted);font-size:.76rem}.hypothesis{font-size:.95rem;line-height:1.55;color:var(--secondary);margin:18px 0}.chain{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:18px 0}.chain div{padding:12px;background:var(--soft);border-radius:12px}.chain span{display:block;color:var(--muted);font-size:.64rem;text-transform:uppercase;font-weight:750;letter-spacing:.05em;margin-bottom:5px}.chain strong{font-size:.82rem;line-height:1.35}.contributions{display:grid;gap:8px;margin-top:18px}.contribution{padding:12px 0;border-top:1px solid var(--line)}.signals{margin:16px 0 0;padding:0 0 0 18px;color:var(--secondary);font-size:.82rem;line-height:1.52}
.capabilities{padding:5px 20px}.cap-row{display:grid;grid-template-columns:minmax(180px,.8fr) minmax(0,1.2fr);gap:24px;padding:15px 0;border-top:1px solid var(--line)}.cap-row:first-child{border-top:0}.cap-row>div:first-child{display:grid;gap:3px}.cap-row>div:first-child strong{font-size:.88rem}.cap-row>div:first-child span{font-size:.7rem;color:var(--muted)}.cap-evidence{display:grid;gap:3px}.cap-evidence strong{font-size:.76rem;font-weight:650}.cap-evidence span{font-size:.74rem;color:var(--muted);line-height:1.4}.state-absorbed strong,.state-tolerated strong{color:var(--green)}.state-missing strong{color:#8a5a28}
.legend{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.legend div{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}.legend strong{display:block;font-size:.78rem;margin-bottom:4px}.legend span{color:var(--muted);font-size:.71rem;line-height:1.4}
@media(max-width:700px){.shell{padding:20px 14px 56px}.topnav{margin-bottom:36px}.goal-grid{grid-template-columns:1fr}.chain,.legend{grid-template-columns:1fr}.cap-row{grid-template-columns:1fr;gap:8px}.section-head{display:block}.section-head p{margin-top:5px}.timeline-body{padding:14px}.declared-goal{display:block}.declared-goal span{display:block;margin-top:4px}}
"""

    return (
        '<!doctype html><html lang="sv"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Mål & utveckling · Träning</title>'
        f'<style>{css}</style></head><body><div class="shell">'
        '<nav class="topnav"><a href="/träning/">Aktuell vecka</a><a href="/träning/onboarding/">Träningsprofil</a></nav>'
        '<header class="hero"><div class="kicker">Coachens utvecklingsplan</div>'
        '<h1>Mål & utveckling</h1>'
        '<p>Här går planen att följa hela vägen från dina mål till vilka kapaciteter som utvecklas nu, varför blocket ser ut som det gör och när nästa större beslut tas.</p>'
        f'<div class="notice">{e(roadmap.get("interpretation_boundary"))}</div></header>'
        '<section><div class="section-head"><h2>Målbild</h2><p>Fast datum visas som datum. Utvecklingsmål utan slutdatum är pågående.</p></div>'
        f'<div class="goal-grid">{goal_html}</div>'
        f'<div class="profile-goals"><h3>Dina mål från träningsprofilen</h3>{declared_html}</div></section>'
        '<section><div class="section-head"><h2>Vägen dit</h2><p>Framtida faser är beslutspunkter, inte färdigskrivna träningsblock.</p></div>'
        f'<ol class="timeline">{timeline_html}</ol></section>'
        '<section><div class="section-head"><h2>Aktuellt utvecklingsblock</h2>'
        f'<p>Nästa blockutvärdering {e(fmt_date(block.get("evaluation_date")))}</p></div>'
        '<div class="block">'
        f'<div class="eyebrow">Aktivt · {e(fmt_date(block.get("start_date")))} – {e(fmt_date(block.get("end_date")))}</div>'
        f'<h3>{e(block.get("title"))}</h3>'
        f'<p class="hypothesis">{e(block.get("hypothesis"))}</p>'
        '<div class="chain">'
        f'<div><span>Primärt nu</span><strong>{e(primary or "Ej specificerat")}</strong></div>'
        f'<div><span>Stödjande</span><strong>{e(secondary or "Ej specificerat")}</strong></div>'
        f'<div><span>Skyddas</span><strong>{e(protected or "Ej specificerat")}</strong></div>'
        '</div>'
        f'<div class="contributions">{contributions_html}</div>'
        '<h3 style="margin-top:22px">Vad ska tala för att blocket fungerar?</h3>'
        f'<ul class="signals">{signals}</ul>'
        '</div></section>'
        '<section><div class="section-head"><h2>Kapacitetskarta</h2><p>Observerat underlag skiljs från tolkning och planerad utveckling.</p></div>'
        f'<div class="capabilities">{capabilities_html}</div></section>'
        '<section><div class="section-head"><h2>Så läser du planen</h2></div><div class="legend">'
        '<div><strong>Fast</strong><span>Tävlings- eller måldatum som faktiskt är bestämt.</span></div>'
        '<div><strong>Aktivt</strong><span>Ett fattat träningsbeslut som gäller nu.</span></div>'
        '<div><strong>Preliminärt</strong><span>Datum då specificitet ska omprövas utifrån dåvarande data.</span></div>'
        '<div><strong>Checkpoint</strong><span>Utvärdering av faktisk respons innan nästa större beslut.</span></div>'
        '</div></section>'
        '</div></body></html>'
    )


def publish_development_page():
    strategy = load_json(DATA / "training_strategy.json")
    policy = load_json(DATA / "planning_policy.json")
    athlete_state = load_json(DATA / "athlete_state.json")
    document = render_page(strategy, policy, athlete_state)
    required = (
        "<!doctype html>",
        "Mål & utveckling",
        "Vägen dit",
        "Aktuellt utvecklingsblock",
        "Kapacitetskarta",
        "Preliminär beslutspunkt",
    )
    missing = [marker for marker in required if marker not in document]
    if missing:
        raise RuntimeError("Development page missing required structure: " + ", ".join(missing))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(document, encoding="utf-8")
    print(f"DEVELOPMENT_PAGE_OK {TARGET.relative_to(ROOT)}", flush=True)
    return TARGET


if __name__ == "__main__":
    publish_development_page()
