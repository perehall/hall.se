"""Semantic contracts used to compare legacy and v2 without comparing markup."""

from __future__ import annotations

from typing import Any

from training_core.application.presentation import PresentationSnapshot


def semantic_snapshot(snapshot: PresentationSnapshot) -> dict[str, Any]:
    return {
        "navigation": {
            "key": snapshot.navigation.key,
            "label": snapshot.navigation.label,
            "period": snapshot.navigation.period,
            "state": snapshot.navigation.state,
            "previous": (
                {
                    "key": snapshot.navigation.previous.key,
                    "label": snapshot.navigation.previous.label,
                    "url": snapshot.navigation.previous.url,
                }
                if snapshot.navigation.previous else None
            ),
            "next": (
                {
                    "key": snapshot.navigation.next.key,
                    "label": snapshot.navigation.next.label,
                    "url": snapshot.navigation.next.url,
                }
                if snapshot.navigation.next else None
            ),
        },
        "today": {
            "date": snapshot.today.local_date.isoformat(),
            "state": snapshot.today.state,
            "title": snapshot.today.title,
            "details": list(snapshot.today.details),
            "planned_session": snapshot.today.planned_session,
            "next_session": snapshot.today.next_session,
            "reason": snapshot.today.reason,
            "development_focus": snapshot.today.development_focus,
            "prescription": list(snapshot.today.prescription),
            "outcomes": [
                {
                    "provider_activity_id": outcome.provider_activity_id,
                    "label": outcome.label,
                    "detail": outcome.detail,
                    "feedback_status": outcome.feedback_status,
                    "feedback_event_key": outcome.feedback_event_key,
                    "feedback_text": outcome.feedback_text,
                    "rpe": outcome.rpe,
                    "feelings": list(outcome.feelings),
                    "coach_summary": outcome.coach_summary,
                    "plan_impact": outcome.plan_impact,
                    "action_reason": outcome.action_reason,
                    "next_step": outcome.next_step,
                }
                for outcome in snapshot.today.outcomes
            ],
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
            differences.append(
                f"{path}: type {type(left).__name__} != {type(right).__name__}"
            )
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
