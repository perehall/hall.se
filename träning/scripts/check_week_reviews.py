#!/usr/bin/env python3
import json
from pathlib import Path
from week_review_contracts import validate_week_review_document

ROOT = Path(__file__).resolve().parents[1]
REVIEWS_DIR = ROOT / "data" / "week_reviews"


def main():
    count = 0
    if REVIEWS_DIR.exists():
        for path in sorted(REVIEWS_DIR.glob("????-W??.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            validate_week_review_document(document)
            if document.get("week_key") != path.stem:
                raise RuntimeError(f"Veckoutvärdering: week_key matchar inte {path.name}")
            count += 1
    print(f"Veckoutvärdering kontrakt OK: {count} validerade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
