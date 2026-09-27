"""Planning-context domain objects used across presentation/application boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MesocycleContext:
    mesocycle_id: str
    title: str
    decision: str
    start_date: date
    end_date: date
    duration_weeks: int | None
    goal_contribution: str
    hypothesis: str
    payload: dict


@dataclass(frozen=True)
class MicrocycleContext:
    microcycle_id: str
    mesocycle_id: str
    microcycle_index: int | None
    week_start: date
    rationale: str
    payload: dict


@dataclass(frozen=True)
class WeekPlanningContext:
    mesocycle: MesocycleContext
    microcycle: MicrocycleContext
