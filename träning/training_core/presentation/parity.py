"""Semantic contracts used to compare legacy and v2 without comparing markup."""

from __future__ import annotations

from typing import Any

from training_core.application.presentation import (
    HistoricalPresentationSnapshot,
    PresentationSnapshot,
)


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
            "icon_keys": list(snapshot.today.icon_keys),
            "manual_activities": [
                {
                    "session": activity.session,
                    "sport": activity.sport,
                    "classification": activity.classification,
                    "reason": activity.reason,
                    "icon_key": activity.icon_key,
                }
                for activity in snapshot.today.manual_activities
            ],
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
                    "icon_key": outcome.icon_key,
                }
                for outcome in snapshot.today.outcomes
            ],
        },
        "week_context": (
            {
                "focus": snapshot.week_context.focus,
                "meta_line": snapshot.week_context.meta_line,
                "principle": snapshot.week_context.principle,
                "hypothesis": snapshot.week_context.hypothesis,
                "primary": list(snapshot.week_context.primary),
                "secondary": list(snapshot.week_context.secondary),
                "maintenance": list(snapshot.week_context.maintenance),
                "protected": list(snapshot.week_context.protected),
            }
            if snapshot.week_context else None
        ),
        "weather": {
            "status": snapshot.weather.status,
            "source": snapshot.weather.source,
            "days": [
                {
                    "date": weather.local_date.isoformat(),
                    "summary": weather.summary,
                    "stale": weather.stale,
                }
                for weather in snapshot.weather.days
            ],
        },
        "week": {
            "start": snapshot.week.start.isoformat(),
            "end": snapshot.week.end.isoformat(),
            "planned_count": snapshot.week.planned_count,
            "completed_activity_count": snapshot.week.completed_activity_count,
            "training_day_count": snapshot.week.training_day_count,
            "status_summary": snapshot.week.status_summary,
            "sport_distribution": [
                {"label": item.label, "duration": item.duration}
                for item in snapshot.week.sport_distribution
            ],
            "days": [
                {
                    "date": d.local_date.isoformat(),
                    "state": d.state,
                    "planned_session": d.planned_session,
                    "actual_labels": list(d.actual_labels),
                    "icon_keys": list(d.icon_keys),
                    "manual_activities": [
                        {
                            "session": activity.session,
                            "sport": activity.sport,
                            "classification": activity.classification,
                            "reason": activity.reason,
                            "icon_key": activity.icon_key,
                        }
                        for activity in d.manual_activities
                    ],
                    "weather": (
                        snapshot.weather.for_date(d.local_date).summary
                        if snapshot.weather.for_date(d.local_date) is not None
                        and not d.actual_labels
                        else ""
                    ),
                }
                for d in snapshot.week.days
            ],
        },
    }


def historical_semantic_snapshot(
    snapshot: HistoricalPresentationSnapshot,
) -> dict[str, Any]:
    model = snapshot.history
    review = model.review
    return {
        "navigation": {
            "key": snapshot.navigation.key,
            "state": snapshot.navigation.state,
            "previous": snapshot.navigation.previous.key
            if snapshot.navigation.previous else None,
            "next": snapshot.navigation.next.key
            if snapshot.navigation.next else None,
        },
        "history": {
            "key": model.key,
            "start": model.start.isoformat(),
            "end": model.end.isoformat(),
            "title": model.title,
            "principle": model.principle,
            "days": [
                {
                    "date": day.local_date.isoformat(),
                    "state": day.state,
                    "planned_session": day.planned_session,
                    "reason": day.reason,
                    "development_focus": day.development_focus,
                    "prescription": list(day.prescription),
                    "planned_icon_keys": list(day.planned_icon_keys),
                    "activities": [
                        {
                            "provider_activity_id": activity.provider_activity_id,
                            "label": activity.label,
                            "detail": activity.detail,
                            "classification": activity.classification,
                            "user_report": activity.user_report,
                            "coach_summary": activity.coach_summary,
                            "plan_impact": activity.plan_impact,
                            "action_reason": activity.action_reason,
                            "next_step": activity.next_step,
                            "uncertainties": list(activity.uncertainties),
                            "icon_key": activity.icon_key,
                        }
                        for activity in day.activities
                    ],
                }
                for day in model.days
            ],
            "review": (
                {
                    "activity_count": review.activity_count,
                    "training_activity_count": review.training_activity_count,
                    "recreation_activity_count": review.recreation_activity_count,
                    "active_days": review.active_days,
                    "total_activity_time": review.total_activity_time,
                    "summary": review.summary,
                    "worked": list(review.worked),
                    "not_as_planned": list(review.not_as_planned),
                    "load_continuity": review.load_continuity,
                    "key_lesson": review.key_lesson,
                    "next_week_implication": review.next_week_implication,
                    "uncertainties": list(review.uncertainties),
                }
                if review else None
            ),
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
