"""Multi-week training overview read model.

The overview is deliberately factual. It aggregates canonical planned workouts and
completed activities without inferring missing training load from session names.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from training_core.domain.weather import WeatherSnapshot
from training_core.domain.workouts import PlannedWorkout, planned_training_workouts
from training_core.presentation.prescription import PrescriptionRow, prescription_rows
from training_core.presentation.sport_identity import activity_icon_key, planned_icon_keys
from training_core.presentation.today import CompletedActivity
from training_core.presentation.weather import DayWeatherReadModel, build_daily_weather_models
from training_core.presentation.week import format_distance, format_duration


@dataclass(frozen=True)
class OverviewPlannedWorkoutReadModel:
    workout_key: str
    session: str
    sport: str
    state: str
    icon_keys: tuple[str, ...]
    development_focus: str
    stimuli: tuple[str, ...]
    recipe_key: str
    priority_role: str
    block_intent: str
    development_character: str
    development_relation: str
    development_reason: str
    prescription_rows: tuple[PrescriptionRow, ...]


@dataclass(frozen=True)
class OverviewActivityReadModel:
    provider_activity_id: str
    label: str
    sport_family: str
    duration_s: int
    distance_m: float
    icon_key: str

    @property
    def duration(self) -> str:
        return format_duration(self.duration_s)

    @property
    def distance(self) -> str:
        return format_distance(self.distance_m)


@dataclass(frozen=True)
class OverviewDayReadModel:
    local_date: date
    planned_workouts: tuple[OverviewPlannedWorkoutReadModel, ...]
    actual_activities: tuple[OverviewActivityReadModel, ...]
    state: str
    weather: DayWeatherReadModel | None = None

    @property
    def planned_count(self) -> int:
        return len(self.planned_workouts)

    @property
    def actual_count(self) -> int:
        return len(self.actual_activities)

    @property
    def is_rest(self) -> bool:
        return not self.planned_workouts and not self.actual_activities


@dataclass(frozen=True)
class OverviewWeekReadModel:
    start: date
    end: date
    days: tuple[OverviewDayReadModel, ...]
    planned_count: int
    completed_count: int
    planned_training_days: int
    actual_training_days: int
    actual_duration_s: int
    actual_distance_m: float
    fixed_count: int

    @property
    def iso_key(self) -> str:
        year, week, _ = self.start.isocalendar()
        return f"{year}-W{week:02d}"

    @property
    def week_number(self) -> int:
        return self.start.isocalendar().week

    @property
    def actual_duration(self) -> str:
        return format_duration(self.actual_duration_s)

    @property
    def actual_distance(self) -> str:
        return format_distance(self.actual_distance_m)

    @property
    def planned_workouts(self) -> tuple[OverviewPlannedWorkoutReadModel, ...]:
        return tuple(
            workout
            for day in self.days
            for workout in day.planned_workouts
        )

    @property
    def block_intents(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                workout.block_intent
                for workout in self.planned_workouts
                if workout.block_intent
            )
        )

    @property
    def primary_workouts(self) -> tuple[OverviewPlannedWorkoutReadModel, ...]:
        return tuple(
            workout for workout in self.planned_workouts
            if workout.priority_role == "anchor"
        )

    @property
    def primary_progress_count(self) -> int:
        return sum(
            workout.development_relation == "progress"
            for workout in self.primary_workouts
        )

    @property
    def primary_hold_count(self) -> int:
        return sum(
            workout.development_relation == "hold"
            for workout in self.primary_workouts
        )

    @property
    def primary_establish_count(self) -> int:
        return sum(
            workout.development_relation == "establish"
            for workout in self.primary_workouts
        )


@dataclass(frozen=True)
class OverviewProgressionAxisReadModel:
    capability_key: str
    capability_label: str
    axis: str
    objective: str


@dataclass(frozen=True)
class OverviewMicrocycleIntentReadModel:
    index: int
    intent: str
    definition: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class OverviewBlueprintVariantReadModel:
    role: str
    capability_key: str
    capability_label: str
    recipe_key: str
    development_character: str
    label: str
    progression_intent: str
    baseline_session: str
    conditional_target_session: str
    target_condition: str


@dataclass(frozen=True)
class OverviewBlueprintWeekReadModel:
    index: int
    start_date: str
    end_date: str
    block_intent: str
    planned_variants: tuple[OverviewBlueprintVariantReadModel, ...]
    supporting_candidates: tuple[OverviewBlueprintVariantReadModel, ...]
    protected_variants: tuple[OverviewBlueprintVariantReadModel, ...]
    principle: str


@dataclass(frozen=True)
class OverviewForwardSlotReadModel:
    day_index: int
    role: str
    sport: str
    recipe_key: str
    label: str
    progression_intent: str
    baseline_session: str
    conditional_target_session: str


@dataclass(frozen=True)
class OverviewCapabilityDirectionReadModel:
    capability_key: str
    capability_label: str
    direction: str
    candidate_recipe_characters: tuple[str, ...]
    progression_ready_now: bool
    evidence_state_now: str


@dataclass(frozen=True)
class OverviewForwardWeekReadModel:
    start_date: str
    end_date: str
    planning_level: str
    planning_label: str
    day_precision: str
    block_intent: str
    title: str
    slots: tuple[OverviewForwardSlotReadModel, ...]
    capability_directions: tuple[OverviewCapabilityDirectionReadModel, ...]
    support_candidates: tuple[OverviewCapabilityDirectionReadModel, ...]
    protected_capabilities: tuple[str, ...]
    decision_gate: str
    source: str


@dataclass(frozen=True)
class OverviewGoalReadModel:
    label: str
    target: str
    target_date: str


@dataclass(frozen=True)
class OverviewBlockReadModel:
    title: str
    start_date: str
    end_date: str
    evaluation_date: str
    primary_capability_keys: tuple[str, ...]
    primary_capabilities: tuple[str, ...]
    secondary_capabilities: tuple[str, ...]
    protected_capabilities: tuple[str, ...]
    progression_axes: tuple[OverviewProgressionAxisReadModel, ...]
    microcycle_intents: tuple[OverviewMicrocycleIntentReadModel, ...]
    development_blueprint: tuple[OverviewBlueprintWeekReadModel, ...]
    forward_horizon: tuple[OverviewForwardWeekReadModel, ...]


@dataclass(frozen=True)
class OverviewPlanContextReadModel:
    goals: tuple[OverviewGoalReadModel, ...]
    active_block: OverviewBlockReadModel | None
    interpretation_boundary: str


@dataclass(frozen=True)
class TrainingOverviewReadModel:
    start: date
    end: date
    current_week_start: date
    weeks: tuple[OverviewWeekReadModel, ...]
    context: OverviewPlanContextReadModel | None

    @property
    def future_planned_week_count(self) -> int:
        return sum(
            1
            for week in self.weeks
            if week.start > self.current_week_start and week.planned_count > 0
        )


def _planned_state(workout: PlannedWorkout) -> str:
    if workout.manual_lock or workout.planning_status == "fixed":
        return "fixed"
    return str(workout.status or "planned").strip().lower() or "planned"


def _day_state(
    planned: tuple[OverviewPlannedWorkoutReadModel, ...],
    actual: tuple[OverviewActivityReadModel, ...],
) -> str:
    if actual:
        return "completed"
    if any(workout.state == "fixed" for workout in planned):
        return "fixed"
    states = tuple(workout.state for workout in planned if workout.state)
    if states and len(set(states)) == 1:
        return states[0]
    if planned:
        return "planned"
    return "open"


def _planned_model(workout: PlannedWorkout) -> OverviewPlannedWorkoutReadModel:
    payload = workout.payload or {}
    stimuli = payload.get("stimuli") or ()
    if not isinstance(stimuli, (list, tuple)):
        stimuli = ()
    development_step = payload.get("development_step") or {}
    if not isinstance(development_step, dict):
        development_step = {}
    return OverviewPlannedWorkoutReadModel(
        workout_key=workout.workout_key,
        session=workout.session,
        sport=workout.sport,
        state=_planned_state(workout),
        icon_keys=planned_icon_keys(sport=workout.sport, payload=payload),
        development_focus=str(workout.development_focus or "").strip(),
        stimuli=tuple(str(item) for item in stimuli if str(item).strip()),
        recipe_key=str(payload.get("recipe_key") or "").strip(),
        priority_role=str(payload.get("priority_role") or "").strip(),
        block_intent=str(payload.get("block_intent") or "").strip(),
        development_character=str(payload.get("development_character") or "").strip(),
        development_relation=str(development_step.get("relation") or "").strip(),
        development_reason=str(
            workout.reason or development_step.get("reason") or ""
        ).strip(),
        prescription_rows=prescription_rows(payload),
    )


def _actual_model(activity: CompletedActivity) -> OverviewActivityReadModel:
    return OverviewActivityReadModel(
        provider_activity_id=activity.provider_activity_id,
        label=activity.label,
        sport_family=activity.sport_family,
        duration_s=int(activity.elapsed_time_s or 0),
        distance_m=float(activity.distance_m or 0.0),
        icon_key=activity_icon_key(activity.sport_family),
    )


def build_overview_context(roadmap: dict | None) -> OverviewPlanContextReadModel | None:
    if not isinstance(roadmap, dict):
        return None

    capability_labels = {
        str(row.get("key")): str(row.get("label"))
        for row in roadmap.get("capabilities") or ()
        if isinstance(row, dict) and row.get("key") and row.get("label")
    }
    goals = tuple(
        OverviewGoalReadModel(
            label=str(goal.get("label") or "").strip(),
            target=str(goal.get("target") or "").strip(),
            target_date=str(goal.get("target_date") or "").strip(),
        )
        for goal in roadmap.get("canonical_goals") or ()
        if isinstance(goal, dict) and str(goal.get("label") or "").strip()
    )

    block_raw = roadmap.get("active_block")
    block = None
    if isinstance(block_raw, dict):
        labels = lambda keys: tuple(
            capability_labels.get(str(key), str(key))
            for key in (keys or ())
            if str(key).strip()
        )
        primary_keys = tuple(
            str(key) for key in (block_raw.get("primary_capabilities") or ())
            if str(key).strip()
        )
        progression_axes = tuple(
            OverviewProgressionAxisReadModel(
                capability_key=str(row.get("capability") or "").strip(),
                capability_label=capability_labels.get(
                    str(row.get("capability") or ""),
                    str(row.get("capability") or ""),
                ),
                axis=str(row.get("axis") or "").strip(),
                objective=str(row.get("objective") or "").strip(),
            )
            for row in block_raw.get("progression_axes") or ()
            if isinstance(row, dict) and str(row.get("capability") or "").strip()
        )
        microcycle_intents = tuple(
            OverviewMicrocycleIntentReadModel(
                index=int(row.get("index") or 0),
                intent=str(row.get("intent") or "").strip(),
                definition=str(row.get("definition") or "").strip(),
                start_date=str(row.get("start_date") or "").strip(),
                end_date=str(row.get("end_date") or "").strip(),
            )
            for row in block_raw.get("microcycle_intents") or ()
            if isinstance(row, dict) and int(row.get("index") or 0) > 0
        )

        def blueprint_variant(row):
            capability_key = str(row.get("capability") or "").strip()
            return OverviewBlueprintVariantReadModel(
                role=str(row.get("role") or "").strip(),
                capability_key=capability_key,
                capability_label=capability_labels.get(capability_key, capability_key),
                recipe_key=str(row.get("recipe_key") or "").strip(),
                development_character=str(row.get("development_character") or "").strip(),
                label=str(row.get("label") or "").strip(),
                progression_intent=str(row.get("progression_intent") or "").strip(),
                baseline_session=str(row.get("baseline_session") or "").strip(),
                conditional_target_session=str(
                    row.get("conditional_target_session") or ""
                ).strip(),
                target_condition=str(row.get("target_condition") or "").strip(),
            )

        development_blueprint = tuple(
            OverviewBlueprintWeekReadModel(
                index=int(row.get("microcycle_index") or 0),
                start_date=str(row.get("week_start") or "").strip(),
                end_date=str(row.get("week_end") or "").strip(),
                block_intent=str(row.get("block_intent") or "").strip(),
                planned_variants=tuple(
                    blueprint_variant(item)
                    for item in row.get("planned_variants") or ()
                    if isinstance(item, dict)
                ),
                supporting_candidates=tuple(
                    blueprint_variant(item)
                    for item in row.get("supporting_candidates") or ()
                    if isinstance(item, dict)
                ),
                protected_variants=tuple(
                    blueprint_variant(item)
                    for item in row.get("protected_variants") or ()
                    if isinstance(item, dict)
                ),
                principle=str(row.get("principle") or "").strip(),
            )
            for row in block_raw.get("development_blueprint") or ()
            if isinstance(row, dict) and int(row.get("microcycle_index") or 0) > 0
        )
        def forward_direction(row):
            capability_key = str(row.get("capability") or "").strip()
            return OverviewCapabilityDirectionReadModel(
                capability_key=capability_key,
                capability_label=capability_labels.get(
                    capability_key,
                    str(row.get("label") or capability_key).strip(),
                ),
                direction=str(row.get("direction") or "").strip(),
                candidate_recipe_characters=tuple(
                    str(value)
                    for value in row.get("candidate_recipe_characters") or ()
                    if str(value).strip()
                ),
                progression_ready_now=bool(
                    row.get("progression_ready_now") is True
                ),
                evidence_state_now=str(
                    row.get("evidence_state_now") or ""
                ).strip(),
            )

        forward_horizon = tuple(
            OverviewForwardWeekReadModel(
                start_date=str(row.get("week_start") or "").strip(),
                end_date=str(row.get("week_end") or "").strip(),
                planning_level=str(row.get("planning_level") or "").strip(),
                planning_label=str(row.get("planning_label") or "").strip(),
                day_precision=str(row.get("day_precision") or "").strip(),
                block_intent=str(row.get("block_intent") or "").strip(),
                title=str(row.get("title") or "").strip(),
                slots=tuple(
                    OverviewForwardSlotReadModel(
                        day_index=int(item.get("day_index") or 0),
                        role=str(item.get("role") or "").strip(),
                        sport=str(item.get("sport") or "").strip(),
                        recipe_key=str(item.get("recipe_key") or "").strip(),
                        label=str(item.get("label") or "").strip(),
                        progression_intent=str(
                            item.get("progression_intent") or ""
                        ).strip(),
                        baseline_session=str(
                            item.get("baseline_session") or ""
                        ).strip(),
                        conditional_target_session=str(
                            item.get("conditional_target_session") or ""
                        ).strip(),
                    )
                    for item in row.get("slots") or ()
                    if isinstance(item, dict)
                    and int(item.get("day_index") or 0) in range(1, 8)
                ),
                capability_directions=tuple(
                    forward_direction(item)
                    for item in row.get("capability_directions") or ()
                    if isinstance(item, dict)
                ),
                support_candidates=tuple(
                    forward_direction(item)
                    for item in row.get("support_candidates") or ()
                    if isinstance(item, dict)
                ),
                protected_capabilities=tuple(
                    capability_labels.get(
                        str(item.get("capability") or ""),
                        str(item.get("label") or item.get("capability") or ""),
                    )
                    for item in row.get("protected_capabilities") or ()
                    if isinstance(item, dict)
                    and str(item.get("capability") or item.get("label") or "").strip()
                ),
                decision_gate=str(row.get("decision_gate") or "").strip(),
                source=str(row.get("source") or "").strip(),
            )
            for row in block_raw.get("forward_horizon") or ()
            if isinstance(row, dict)
            and str(row.get("week_start") or "").strip()
        )

        block = OverviewBlockReadModel(
            title=str(block_raw.get("title") or "").strip(),
            start_date=str(block_raw.get("start_date") or "").strip(),
            end_date=str(block_raw.get("end_date") or "").strip(),
            evaluation_date=str(block_raw.get("evaluation_date") or "").strip(),
            primary_capability_keys=primary_keys,
            primary_capabilities=labels(primary_keys),
            secondary_capabilities=labels(block_raw.get("secondary_capabilities")),
            protected_capabilities=labels(block_raw.get("protected_capabilities")),
            progression_axes=progression_axes,
            microcycle_intents=microcycle_intents,
            development_blueprint=development_blueprint,
            forward_horizon=forward_horizon,
        )

    return OverviewPlanContextReadModel(
        goals=goals,
        active_block=block,
        interpretation_boundary=str(roadmap.get("interpretation_boundary") or "").strip(),
    )


def build_training_overview(
    *,
    start: date,
    end: date,
    current_date: date,
    plan: Iterable[PlannedWorkout],
    activities: Iterable[CompletedActivity],
    roadmap: dict | None = None,
    weather_snapshot: WeatherSnapshot | None = None,
) -> TrainingOverviewReadModel:
    if end < start:
        raise ValueError("overview end must not precede start")
    if start.weekday() != 0 or end.weekday() != 6:
        raise ValueError("overview window must span complete Monday-Sunday weeks")

    plan_rows = tuple(
        workout
        for workout in planned_training_workouts(tuple(plan))
        if start <= workout.local_date <= end
    )
    activity_rows = tuple(
        activity for activity in activities if start <= activity.local_date <= end
    )

    plan_by_date: dict[date, list[PlannedWorkout]] = {}
    for workout in plan_rows:
        plan_by_date.setdefault(workout.local_date, []).append(workout)

    activities_by_date: dict[date, list[CompletedActivity]] = {}
    for activity in activity_rows:
        activities_by_date.setdefault(activity.local_date, []).append(activity)

    weather_by_date = {
        item.local_date: item
        for item in build_daily_weather_models(weather_snapshot)
        if start <= item.local_date <= end
    }

    current_week_start = current_date - timedelta(days=current_date.weekday())
    weeks: list[OverviewWeekReadModel] = []
    cursor = start
    while cursor <= end:
        week_end = cursor + timedelta(days=6)
        days: list[OverviewDayReadModel] = []
        for offset in range(7):
            local_date = cursor + timedelta(days=offset)
            planned = tuple(
                _planned_model(workout)
                for workout in plan_by_date.get(local_date, ())
            )
            actual = tuple(
                _actual_model(activity)
                for activity in activities_by_date.get(local_date, ())
            )
            days.append(
                OverviewDayReadModel(
                    local_date=local_date,
                    planned_workouts=planned,
                    actual_activities=actual,
                    state=_day_state(planned, actual),
                    weather=weather_by_date.get(local_date),
                )
            )

        week_activities = tuple(
            activity
            for activity in activity_rows
            if cursor <= activity.local_date <= week_end
        )
        week_planned = tuple(
            workout
            for workout in plan_rows
            if cursor <= workout.local_date <= week_end
        )
        weeks.append(
            OverviewWeekReadModel(
                start=cursor,
                end=week_end,
                days=tuple(days),
                planned_count=len(week_planned),
                completed_count=len(week_activities),
                planned_training_days=len({workout.local_date for workout in week_planned}),
                actual_training_days=len({activity.local_date for activity in week_activities}),
                actual_duration_s=sum(int(activity.elapsed_time_s or 0) for activity in week_activities),
                actual_distance_m=sum(float(activity.distance_m or 0.0) for activity in week_activities),
                fixed_count=sum(1 for workout in week_planned if _planned_state(workout) == "fixed"),
            )
        )
        cursor += timedelta(days=7)

    return TrainingOverviewReadModel(
        start=start,
        end=end,
        current_week_start=current_week_start,
        weeks=tuple(weeks),
        context=build_overview_context(roadmap),
    )
