"""Typed historical-week read model built from immutable audit-domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from training_core.domain.history import (
    ArchivedActivity,
    ArchivedCoachEvaluation,
    ArchivedWeek,
    ArchivedWeekReview,
)
from training_core.presentation.public_copy import public_reason
from training_core.presentation.prescription import prescription_lines
from training_core.presentation.sport_identity import (
    activity_icon_key,
    planned_icon_keys,
)


PLAN_IMPACT_LABELS = {
    "keep": "Ingen ändring",
    "review": "Fortsatt bedömning",
}


@dataclass(frozen=True)
class HistoricalActivityReadModel:
    provider_activity_id: str
    label: str
    detail: str
    classification: str
    user_report: str
    coach_summary: str
    plan_impact: str
    action_reason: str
    next_step: str
    uncertainties: tuple[str, ...]
    icon_key: str


@dataclass(frozen=True)
class HistoricalDayReadModel:
    local_date: date
    planned_session: str
    reason: str
    development_focus: str
    prescription: tuple[str, ...]
    activities: tuple[HistoricalActivityReadModel, ...]
    planned_icon_keys: tuple[str, ...]
    state: str


@dataclass(frozen=True)
class HistoricalWeekReviewReadModel:
    activity_count: int
    training_activity_count: int
    recreation_activity_count: int
    active_days: int
    total_activity_time: str
    summary: str
    worked: tuple[str, ...]
    not_as_planned: tuple[str, ...]
    load_continuity: str
    key_lesson: str
    next_week_implication: str
    uncertainties: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalWeekReadModel:
    key: str
    start: date
    end: date
    title: str
    principle: str
    days: tuple[HistoricalDayReadModel, ...]
    review: HistoricalWeekReviewReadModel | None


def _duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _activity_detail(activity: ArchivedActivity) -> str:
    parts: list[str] = []
    if activity.distance_m and activity.distance_m > 0:
        parts.append(f"{activity.distance_m / 1000:.2f} km".replace(".", ","))
    duration = _duration(activity.elapsed_time_s)
    if duration:
        parts.append(duration)
    if activity.average_heartrate:
        parts.append(f"snittpuls {round(float(activity.average_heartrate))}")
    if activity.max_heartrate:
        parts.append(f"max {round(float(activity.max_heartrate))}")
    return " · ".join(parts)


def _prescription_lines(payload: dict) -> tuple[str, ...]:
    return prescription_lines(payload)


def _plan_impact(evaluation: ArchivedCoachEvaluation | None) -> str:
    if evaluation is None:
        return ""
    action = evaluation.plan_action
    if action in PLAN_IMPACT_LABELS:
        return PLAN_IMPACT_LABELS[action]
    if action in {"reduce", "rest"}:
        return (
            "Planen justerades"
            if evaluation.auto_applied
            else "Ändring rekommenderades"
        )
    return ""


def _latest_evaluations(
    evaluations: tuple[ArchivedCoachEvaluation, ...],
) -> dict[str, ArchivedCoachEvaluation]:
    latest: dict[str, ArchivedCoachEvaluation] = {}
    for evaluation in evaluations:
        previous = latest.get(evaluation.provider_activity_id)
        if previous is None or evaluation.generated_at_utc >= previous.generated_at_utc:
            latest[evaluation.provider_activity_id] = evaluation
    return latest


def _activity_model(
    activity: ArchivedActivity,
    evaluation: ArchivedCoachEvaluation | None,
) -> HistoricalActivityReadModel:
    return HistoricalActivityReadModel(
        provider_activity_id=activity.provider_activity_id,
        label=activity.label,
        detail=_activity_detail(activity),
        classification=activity.classification,
        user_report=activity.user_report,
        coach_summary=evaluation.summary if evaluation else "",
        plan_impact=_plan_impact(evaluation),
        action_reason=evaluation.action_reason if evaluation else "",
        next_step=evaluation.recommendation if evaluation else "",
        uncertainties=evaluation.unknowns if evaluation else (),
        icon_key=activity_icon_key(activity.sport_type),
    )


def _review_model(
    review: ArchivedWeekReview | None,
) -> HistoricalWeekReviewReadModel | None:
    if review is None:
        return None
    return HistoricalWeekReviewReadModel(
        activity_count=review.activity_count,
        training_activity_count=review.training_activity_count,
        recreation_activity_count=review.recreation_activity_count,
        active_days=review.active_days,
        total_activity_time=_duration(review.total_activity_time_s),
        summary=review.summary,
        worked=review.worked,
        not_as_planned=review.not_as_planned,
        load_continuity=review.load_continuity,
        key_lesson=review.key_lesson,
        next_week_implication=review.next_week_implication,
        uncertainties=review.uncertainties,
    )


def build_historical_week_read_model(
    archived: ArchivedWeek,
) -> HistoricalWeekReadModel:
    latest = _latest_evaluations(archived.coach_evaluations)
    by_date: dict[date, list[ArchivedActivity]] = {}
    for activity in archived.activities:
        by_date.setdefault(activity.local_date, []).append(activity)

    days: list[HistoricalDayReadModel] = []
    for planned in archived.plan_days:
        activities = tuple(
            _activity_model(
                activity,
                latest.get(activity.provider_activity_id),
            )
            for activity in by_date.get(planned.local_date, [])
        )
        days.append(
            HistoricalDayReadModel(
                local_date=planned.local_date,
                planned_session=planned.session,
                reason=public_reason(planned.reason),
                development_focus=planned.development_focus,
                prescription=_prescription_lines(planned.payload),
                activities=activities,
                planned_icon_keys=planned_icon_keys(
                    sport=str(planned.payload.get("sport") or ""),
                    payload=planned.payload,
                ),
                state="completed" if activities else "not_recorded",
            )
        )

    return HistoricalWeekReadModel(
        key=archived.key,
        start=archived.start,
        end=archived.end,
        title=archived.title,
        principle=archived.principle,
        days=tuple(days),
        review=_review_model(archived.review),
    )
