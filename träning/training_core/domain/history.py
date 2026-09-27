"""Immutable audit-domain objects for historical training weeks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ArchivedPlanDay:
    local_date: date
    session: str
    status: str
    planning_status: str
    manual_lock: bool
    reason: str
    development_focus: str
    payload: dict


@dataclass(frozen=True)
class ArchivedActivity:
    provider_activity_id: str
    local_date: date
    label: str
    sport_type: str
    classification: str
    elapsed_time_s: int | None
    distance_m: float | None
    average_heartrate: float | None
    max_heartrate: float | None
    user_report: str


@dataclass(frozen=True)
class ArchivedCoachEvaluation:
    provider_activity_id: str
    activity_date: date
    generated_at_utc: str
    summary: str
    interpretations: tuple[str, ...]
    unknowns: tuple[str, ...]
    plan_action: str
    action_reason: str
    recommendation: str
    auto_applied: bool


@dataclass(frozen=True)
class ArchivedWeekReview:
    activity_count: int
    training_activity_count: int
    recreation_activity_count: int
    active_days: int
    total_activity_time_s: int
    summary: str
    worked: tuple[str, ...]
    not_as_planned: tuple[str, ...]
    load_continuity: str
    key_lesson: str
    next_week_implication: str
    uncertainties: tuple[str, ...]


@dataclass(frozen=True)
class ArchivedWeek:
    key: str
    start: date
    end: date
    title: str
    principle: str
    plan_days: tuple[ArchivedPlanDay, ...]
    activities: tuple[ArchivedActivity, ...]
    coach_evaluations: tuple[ArchivedCoachEvaluation, ...]
    review: ArchivedWeekReview | None
