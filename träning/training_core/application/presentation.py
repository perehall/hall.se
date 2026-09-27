"""Application use case for a presentation snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from training_core.presentation.today import TodayReadModel, build_today_read_model
from training_core.repositories.presentation import PresentationRepository


@dataclass(frozen=True)
class PresentationSnapshot:
    today: TodayReadModel


def build_presentation_snapshot(
    repository: PresentationRepository,
    *,
    today: date,
) -> PresentationSnapshot:
    # Read a bounded presentation window from canonical storage. No compatibility
    # JSON is consulted here.
    plan = repository.planned_days(today, today + timedelta(days=7))
    activities = repository.completed_activities(today, today)
    return PresentationSnapshot(
        today=build_today_read_model(today=today, plan=plan, activities=activities)
    )
