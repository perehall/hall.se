"""Semantic contract for the legacy presentation during the v2 strangler migration.

This adapter is deliberately outside training_core. It may inspect legacy HTML,
but the new core never imports or depends on it. The output is a small semantic
contract used only as a cutover gate.
"""

from __future__ import annotations

import re
from datetime import date
from html import unescape
from pathlib import Path

_DAY_RE = re.compile(
    r'<div class="day[^"]*" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">(?P<body>.*?)(?=<div class="day[^"]*" id="dag-|\Z)',
    re.S,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(value: str) -> str:
    return " ".join(unescape(_TAG_RE.sub(" ", value)).split())


def legacy_semantic_contract(index_path: Path, *, today: date) -> dict:
    html = index_path.read_text(encoding="utf-8")
    today_iso = today.isoformat()

    title_match = re.search(
        r'<section class="top-today"[^>]*>.*?<div class="top-today-title">(.*?)</div>',
        html,
        re.S,
    )
    if not title_match:
        raise RuntimeError("legacy parity: top-today title missing")
    today_title = _text(title_match.group(1))

    day_matches = list(_DAY_RE.finditer(html))
    if not day_matches:
        raise RuntimeError("legacy parity: no dated day cards found")

    days = []
    for match in day_matches:
        body = match.group("body")
        date_value = match.group("date")
        completed = "completed-day-summary" in body
        actual_labels = []
        if completed:
            title = re.search(r'<div class="completed-day-title">(.*?)</div>', body, re.S)
            if title:
                actual_labels = [
                    _text(part)
                    for part in re.split(r'<span class="completed-day-title-sep">.*?</span>', title.group(1), flags=re.S)
                    if _text(part)
                ]
        days.append(
            {
                "date": date_value,
                "completed": completed,
                "actual_labels": actual_labels,
            }
        )

    return {
        "today": {"date": today_iso, "title": today_title},
        "week": {"days": days},
    }


def compare_cutover_contract(legacy: dict, v2: dict) -> list[str]:
    differences = []
    if legacy["today"]["date"] != v2["today"]["date"]:
        differences.append(
            f"today.date: {legacy['today']['date']!r} != {v2['today']['date']!r}"
        )
    legacy_title = legacy["today"]["title"]
    v2_title = v2["today"]["title"]
    # Legacy splits dose into a separate meta line; v2 currently keeps it in the
    # canonical session title. Prefix equality therefore represents the same fact.
    if not (v2_title == legacy_title or v2_title.startswith(legacy_title + " ·")):
        differences.append(f"today.title: {legacy_title!r} != {v2_title!r}")

    legacy_days = {d["date"]: d for d in legacy["week"]["days"]}
    v2_days = {d["date"]: d for d in v2["week"]["days"]}
    for day_date, v2_day in sorted(v2_days.items()):
        legacy_day = legacy_days.get(day_date)
        if legacy_day is None:
            differences.append(f"week.{day_date}: missing in legacy")
            continue
        if legacy_day["completed"] != (v2_day["state"] == "completed"):
            differences.append(
                f"week.{day_date}.completed: {legacy_day['completed']!r} != "
                f"{(v2_day['state'] == 'completed')!r}"
            )
        if legacy_day["completed"] and legacy_day["actual_labels"]:
            if legacy_day["actual_labels"] != v2_day["actual_labels"]:
                differences.append(
                    f"week.{day_date}.actual_labels: "
                    f"{legacy_day['actual_labels']!r} != {v2_day['actual_labels']!r}"
                )
    return differences
