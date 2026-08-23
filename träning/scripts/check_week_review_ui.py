#!/usr/bin/env python3
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from weekly_review import week_key_from_plan

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
REVIEWS_DIR = ROOT / "data" / "week_reviews"
INDEX_FILE = ROOT / "index.html"
PAGES_DIR = ROOT / "vecka"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    if not REVIEWS_DIR.exists():
        print("Veckoutvärdering UI-kontrakt: inga reviews ännu.")
        return 0

    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    current_key, _, current_end = week_key_from_plan(plan)
    tz = ZoneInfo((plan.get("meta") or {}).get("timezone") or "Europe/Stockholm")
    today = datetime.now(tz).date()
    checked = 0

    for review_file in sorted(REVIEWS_DIR.glob("????-W??.json")):
        review = json.loads(review_file.read_text(encoding="utf-8"))
        key = review.get("week_key")
        marker = f'data-week-review="{key}"'
        if key == current_key:
            if today <= date.fromisoformat(current_end):
                continue
            target = INDEX_FILE
        else:
            target = PAGES_DIR / str(key) / "index.html"
        require(target.exists(), f"Veckoutvärdering UI-kontrakt: sida saknas för {key}: {target}")
        rendered = target.read_text(encoding="utf-8")
        require(marker in rendered, f"Veckoutvärdering UI-kontrakt: {key} saknas i {target}")
        require("Veckoutvärdering" in rendered, f"Veckoutvärdering UI-kontrakt: rubrik saknas för {key}")
        require(
            "Till nästa veckas planering" in rendered,
            f"Veckoutvärdering UI-kontrakt: nästa-vecka-sektion saknas för {key}",
        )
        checked += 1

    print(
        f"Veckoutvärdering UI-kontrakt OK: {checked} renderad(e) review/reviews verifierade."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
