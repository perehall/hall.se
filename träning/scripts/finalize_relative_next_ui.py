#!/usr/bin/env python3
"""Make the training-brain 'Nästa' label relative when the session is tomorrow."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from coach_rules import planning_window
from training_brain import resolve_next_decision


ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"
SECTION_START = "<!-- training-brain-v1:start -->"
SECTION_END = "<!-- training-brain-v1:end -->"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_next_label(today: date, decision: dict) -> str:
    try:
        decision_date = date.fromisoformat(str(decision.get("date") or ""))
    except ValueError:
        return "Nästa"
    return "Nästa · imorgon" if decision_date == today + timedelta(days=1) else "Nästa"


def patch_page(page: str, label: str) -> str:
    start = page.find(SECTION_START)
    end = page.find(SECTION_END, start + len(SECTION_START))
    if start < 0 or end < 0:
        raise RuntimeError("Relativ Nästa-etikett: träningshjärnans sektion saknas")
    end += len(SECTION_END)
    section = page[start:end]
    pattern = r'<div class="brain-next-label">Nästa(?:\s*·\s*imorgon)?</div>'
    patched, count = re.subn(pattern, f'<div class="brain-next-label">{label}</div>', section, count=1)
    if count != 1:
        raise RuntimeError("Relativ Nästa-etikett: exakt en Nästa-etikett förväntades")
    return page[:start] + patched + page[end:]


def main() -> int:
    plan = load_json(PLAN_FILE)
    upcoming = load_json(UPCOMING_FILE) if UPCOMING_FILE.exists() else {}
    activities_state = load_json(ACTIVITIES_FILE)
    strategy = load_json(STRATEGY_FILE)
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today = datetime.now(ZoneInfo(timezone_name)).date()
    decision_plan = planning_window(plan, upcoming)
    decision = resolve_next_decision(
        decision_plan,
        activities_state.get("activities") or [],
        strategy,
        today,
    )
    label = relative_next_label(today, decision)
    page = INDEX_FILE.read_text(encoding="utf-8")
    INDEX_FILE.write_text(patch_page(page, label), encoding="utf-8")
    print(f"RELATIVE_NEXT_UI_OK label={label!r} date={decision.get('date')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
