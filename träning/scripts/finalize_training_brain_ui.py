#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from strategy_contracts import validate_training_strategy
from training_brain import resolve_block, resolve_next_decision, resolve_priority_line, resolve_today

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"

CSS_MARKER = "/* training-brain-v1 */"
SECTION_START = "<!-- training-brain-v1:start -->"
SECTION_END = "<!-- training-brain-v1:end -->"
CSS = r'''
/* training-brain-v1 */
.training-brain{display:grid;gap:12px;margin:0 0 18px}.brain-today{background:#fff;border:1px solid #bfdbfe;border-radius:20px;padding:17px 18px;box-shadow:var(--shadow)}.brain-kicker{font-size:.69rem;font-weight:900;letter-spacing:.09em;text-transform:uppercase;color:#1d4ed8;margin-bottom:6px}.brain-headline{font-size:1.28rem;font-weight:850;line-height:1.25;letter-spacing:-.015em}.brain-why{margin-top:9px;color:#334155;font-size:.91rem;line-height:1.45}.brain-why strong{color:#0f172a}.brain-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:11px}.brain-tag{padding:4px 8px;border-radius:999px;background:#eff6ff;color:#1e40af;font-size:.68rem;font-weight:800}.brain-tag.role{background:#e2e8f0;color:#334155}.brain-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.brain-card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:14px 15px;box-shadow:var(--shadow)}.brain-card-title{font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em;color:#64748b;margin-bottom:6px}.brain-card strong{display:block;font-size:.96rem;line-height:1.35}.brain-note{margin-top:5px;color:#475569;font-size:.84rem;line-height:1.43}.brain-meta{margin-top:8px;color:#64748b;font-size:.74rem}.brain-priority{margin-top:10px;color:#334155;font-size:.79rem;line-height:1.4}.brain-priority span{font-weight:800}.brain-hypothesis{margin-top:7px;color:#475569;font-size:.82rem;line-height:1.42}
@media (max-width:620px){.brain-grid{grid-template-columns:1fr}.brain-today{padding:15px}.brain-headline{font-size:1.16rem}}
'''


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def render_tags(today):
    tags = []
    if today.get("role"):
        tags.append(f'<span class="brain-tag role">{html.escape(today["role"])}</span>')
    tags.extend(f'<span class="brain-tag">{html.escape(label)}</span>' for label in today.get("stimuli") or [])
    return "".join(tags)


def render_section(plan, activities_state, strategy, today_date):
    activities = activities_state.get("activities") or []
    today = resolve_today(plan, activities, strategy, today_date)
    decision = resolve_next_decision(plan, activities, strategy, today_date)
    block = resolve_block(strategy, today_date)
    priorities = resolve_priority_line(strategy)
    priority_line = " · ".join(priorities)
    evaluation = block.get("evaluation_date") or "ej satt"
    tags = render_tags(today)
    hypothesis = html.escape(block.get("hypothesis") or "")
    protected = " · ".join(block.get("protected_stimuli") or [])

    return f'''{SECTION_START}
<section class="training-brain" aria-label="Träningsbeslut">
  <div class="brain-today">
    <div class="brain-kicker">Idag · {html.escape(today["status"])}</div>
    <div class="brain-headline">{html.escape(today["headline"])}</div>
    <div class="brain-why"><strong>Varför:</strong> {html.escape(today["why"])}</div>
    <div class="brain-tags">{tags}</div>
  </div>
  <div class="brain-grid">
    <div class="brain-card">
      <div class="brain-card-title">Nästa beslut</div>
      <strong>{html.escape(decision["label"] + " · " if decision.get("label") else "")}{html.escape(decision["headline"])}</strong>
      <div class="brain-note">{html.escape(decision["note"])}</div>
    </div>
    <div class="brain-card">
      <div class="brain-card-title">Aktuellt block · {html.escape(block["state"])}</div>
      <strong>{html.escape(block["title"])}</strong>
      <div class="brain-hypothesis">{hypothesis}</div>
      <div class="brain-meta">Utvärdering: {html.escape(evaluation)} · skyddade stimuli: {html.escape(protected)}</div>
    </div>
  </div>
  <div class="brain-priority"><span>Prioritering just nu:</span> {html.escape(priority_line)}</div>
</section>
{SECTION_END}'''


def apply_ui(page, section):
    page = re.sub(
        re.escape(SECTION_START) + r".*?" + re.escape(SECTION_END),
        "",
        page,
        flags=re.S,
    )
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Träningshjärna: index.html saknar </style>")
        page = page.replace("</style>", CSS + "\n</style>", 1)
    dashboard_marker = '<section class="dashboard"'
    if dashboard_marker not in page:
        raise RuntimeError("Träningshjärna: dashboard-markör saknas")
    return page.replace(dashboard_marker, section + "\n" + dashboard_marker, 1)


def main():
    plan = load_json(PLAN_FILE)
    activities = load_json(ACTIVITIES_FILE)
    strategy = load_json(STRATEGY_FILE)
    validate_training_strategy(strategy)
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today = datetime.now(ZoneInfo(timezone_name)).date()
    page = INDEX_FILE.read_text(encoding="utf-8")
    section = render_section(plan, activities, strategy, today)
    rendered = apply_ui(page, section)
    INDEX_FILE.write_text(rendered, encoding="utf-8")

    verify = INDEX_FILE.read_text(encoding="utf-8")
    for marker in (SECTION_START, "Idag ·", "Nästa beslut", "Aktuellt block", "Prioritering just nu"):
        if marker not in verify:
            raise RuntimeError(f"Träningshjärna: renderad sida saknar {marker!r}")
    print("Träningshjärna OK: idag, nästa beslut och aktuellt block renderade.")


if __name__ == "__main__":
    main()
