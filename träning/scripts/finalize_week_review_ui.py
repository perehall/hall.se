#!/usr/bin/env python3
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from weekly_review import week_key_from_plan
from weekly_review_ui import insert_review_after_dashboard

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
REVIEWS_DIR = ROOT / "data" / "week_reviews"
INDEX_FILE = ROOT / "index.html"
PAGES_DIR = ROOT / "vecka"


def apply_review(path, review):
    if not path.exists():
        return False
    page = path.read_text(encoding="utf-8")
    page = insert_review_after_dashboard(page, review)
    path.write_text(page, encoding="utf-8")
    rendered = path.read_text(encoding="utf-8")
    key = review.get("week_key")
    if f'data-week-review="{key}"' not in rendered:
        raise RuntimeError(f"Veckoutvärdering UI: review {key} kunde inte verifieras i {path}")
    return True


def main():
    if not REVIEWS_DIR.exists():
        print("Veckoutvärdering UI: inga reviews ännu; hoppar över.")
        return 0

    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    current_key, _, current_end = week_key_from_plan(plan)
    tz = ZoneInfo((plan.get("meta") or {}).get("timezone") or "Europe/Stockholm")
    today = datetime.now(tz).date()
    applied = 0

    for review_file in sorted(REVIEWS_DIR.glob("????-W??.json")):
        review = json.loads(review_file.read_text(encoding="utf-8"))
        key = review.get("week_key")
        if key != review_file.stem:
            raise RuntimeError(f"Veckoutvärdering UI: fel week_key i {review_file.name}")

        if key == current_key:
            if today <= date.fromisoformat(current_end):
                continue
            if apply_review(INDEX_FILE, review):
                applied += 1
            continue

        historical = PAGES_DIR / key / "index.html"
        if apply_review(historical, review):
            applied += 1

    print(f"Veckoutvärdering UI OK: {applied} sida/sidor dekorerade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
