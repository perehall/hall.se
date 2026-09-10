#!/usr/bin/env python3
"""Show explicit user-reported workout feedback on historical activity insights.

User reports are first-class training evidence. They must not disappear behind a
regenerated coach summary, so this finalizer renders the persisted report verbatim
in a compact, clearly labelled block on the matching historical insight card.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
CSS_MARKER = "/* explicit-user-report-v1 */"

CSS = r"""
/* explicit-user-report-v1 */
.week-activity-user-report{margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0;color:#475569;font-size:.8rem;line-height:1.42}
.week-activity-user-report span{display:block;margin-bottom:2px;color:#64748b;font-size:.66rem;font-weight:900;letter-spacing:.06em;text-transform:uppercase}
.week-activity-user-report p{margin:0}
""".strip()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def add_css(page: str) -> str:
    page = re.sub(
        r"/\* explicit-user-report-v1 \*/.*?(?=(?:/\*|</style>))",
        "",
        page,
        flags=re.S,
    )
    if "</style>" not in page:
        raise RuntimeError("Användarrapport UI: </style> saknas")
    return page.replace("</style>", CSS + "\n</style>", 1)


def remove_existing_blocks(page: str) -> str:
    return re.sub(
        r"\n?<!-- explicit-user-report-v1:\d+:start -->.*?<!-- explicit-user-report-v1:\d+:end -->\n?",
        "\n",
        page,
        flags=re.S,
    )


def insert_report(page: str, activity_id: int, report: str) -> tuple[str, bool]:
    anchor = f'<section class="week-activity-insight" data-week-activity-insight="{activity_id}">'
    start = page.find(anchor)
    if start < 0:
        return page, False
    end = page.find("</section>", start + len(anchor))
    if end < 0:
        raise RuntimeError(f"Användarrapport UI: insight-sektion saknar sluttagg för aktivitet {activity_id}")
    block = (
        f'<!-- explicit-user-report-v1:{activity_id}:start -->\n'
        '<div class="week-activity-user-report"><span>Din kommentar</span>'
        f'<p>{html.escape(report)}</p></div>\n'
        f'<!-- explicit-user-report-v1:{activity_id}:end -->\n'
    )
    return page[:end] + block + page[end:], True


def apply_user_reports(page: str, activities_state: dict) -> str:
    page = add_css(remove_existing_blocks(page))
    for activity in activities_state.get("activities") or []:
        report = str(activity.get("user_report") or "").strip()
        activity_id = activity.get("id")
        if not report or not isinstance(activity_id, int):
            continue
        page, _ = insert_report(page, activity_id, report)
    return page


def main() -> int:
    page = INDEX_FILE.read_text(encoding="utf-8")
    activities = load_json(ACTIVITIES_FILE)
    rendered = apply_user_reports(page, activities)
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    count = rendered.count('class="week-activity-user-report"')
    print(f"Användarrapport UI OK: {count} explicit rapport(er) synliga.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
