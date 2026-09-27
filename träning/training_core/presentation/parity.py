"""Semantic contracts used to compare legacy and v2 without comparing markup."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from training_core.application.presentation import PresentationSnapshot


def semantic_snapshot(snapshot: PresentationSnapshot) -> dict[str, Any]:
    return {
        "today": {
            "date": snapshot.today.local_date.isoformat(),
            "state": snapshot.today.state,
            "title": snapshot.today.title,
            "details": list(snapshot.today.details),
            "planned_session": snapshot.today.planned_session,
            "next_session": snapshot.today.next_session,
        },
        "week": {
            "start": snapshot.week.start.isoformat(),
            "end": snapshot.week.end.isoformat(),
            "planned_count": snapshot.week.planned_count,
            "completed_activity_count": snapshot.week.completed_activity_count,
            "training_day_count": snapshot.week.training_day_count,
            "days": [
                {
                    "date": d.local_date.isoformat(),
                    "state": d.state,
                    "planned_session": d.planned_session,
                    "actual_labels": list(d.actual_labels),
                }
                for d in snapshot.week.days
            ],
        },
    }


def compare_semantics(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    differences: list[str] = []
    def walk(path: str, left: Any, right: Any) -> None:
        if type(left) is not type(right):
            differences.append(f"{path}: type {type(left).__name__} != {type(right).__name__}")
        elif isinstance(left, dict):
            for key in sorted(set(left) | set(right)):
                if key not in left:
                    differences.append(f"{path}.{key}: unexpected")
                elif key not in right:
                    differences.append(f"{path}.{key}: missing")
                else:
                    walk(f"{path}.{key}", left[key], right[key])
        elif isinstance(left, list):
            if len(left) != len(right):
                differences.append(f"{path}: length {len(left)} != {len(right)}")
            for i, (a, b) in enumerate(zip(left, right)):
                walk(f"{path}[{i}]", a, b)
        elif left != right:
            differences.append(f"{path}: {left!r} != {right!r}")
    walk("$", expected, actual)
    return differences
