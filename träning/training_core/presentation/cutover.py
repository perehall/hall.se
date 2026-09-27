"""Machine-readable cutover contract for the v2 training presentation.

This is intentionally about user-visible/operational capabilities, not legacy
scripts. A legacy finalizer can disappear when its capability is either carried
by v2, explicitly kept as a separate surface, or deliberately retired.
"""

from __future__ import annotations

from dataclasses import dataclass


VALID_STATES = {"migrated", "blocker", "separate", "retire"}


@dataclass(frozen=True)
class CutoverSurface:
    key: str
    state: str
    rationale: str

    def __post_init__(self) -> None:
        if self.state not in VALID_STATES:
            raise ValueError(f"invalid cutover surface state: {self.state!r}")
        if not self.key or not self.rationale.strip():
            raise ValueError("cutover surface requires key and rationale")


SURFACES = (
    CutoverSurface(
        "today_week_truth",
        "migrated",
        "Today/Week are typed read models built from canonical PostgreSQL state.",
    ),
    CutoverSurface(
        "workout_prescription",
        "migrated",
        "Selected workout prescription is carried as typed Today detail.",
    ),
    CutoverSurface(
        "post_workout_outcome",
        "migrated",
        "Feedback, coach outcome, plan impact and next step are rendered from canonical state.",
    ),
    CutoverSurface(
        "feedback_editor",
        "migrated",
        "Completed-workout feedback is rendered in v2 and durably persisted through Supabase.",
    ),
    CutoverSurface(
        "week_navigation",
        "migrated",
        "History/current/future navigation uses explicit publication metadata and canonical planned dates.",
    ),
    CutoverSurface(
        "historical_week_detail",
        "migrated",
        "Archived plan, activities, coach evaluations and week review render from typed immutable audit objects.",
    ),
    CutoverSurface(
        "weather",
        "migrated",
        "Synced SMHI forecast is isolated behind WeatherRepository and rendered through typed fields.",
    ),
    CutoverSurface(
        "public_copy_normalization",
        "migrated",
        "Canonical planning provenance is filtered at the read-model boundary; internal athlete_state/decision-trace vocabulary is not public copy.",
    ),
    CutoverSurface(
        "sport_identity_icons",
        "migrated",
        "Structured plan/activity/manual sport identity is carried as typed icon keys and rendered from a validated read-only SVG asset registry across current and historical surfaces.",
    ),
    CutoverSurface(
        "week_context",
        "migrated",
        "Current week focus, microcycle position, plan idea and capability taxonomy are read from canonical mesocycle/microcycle PostgreSQL state.",
    ),
    CutoverSurface(
        "week_status",
        "migrated",
        "Pass count, exact session time, training-day count and sport distribution are derived directly from canonical activity truth in the v2 Week read model.",
    ),
    CutoverSurface(
        "device_sync_status",
        "migrated",
        "Planned syncable workouts expose fail-closed pending/synced/error state from canonical payload; deferred and completed states remain hidden and physical watch delivery is never claimed.",
    ),
    CutoverSurface(
        "page_shell",
        "blocker",
        "V2 has a responsive document shell, but it has not yet reproduced the human-approved current-week information hierarchy, progressive disclosure, card/timeline treatment and interaction density.",
    ),
    CutoverSurface(
        "approved_current_week_experience",
        "blocker",
        "The pre-cutover current-week page is the human-approved product baseline. V2 must preserve what is primary, secondary/collapsed, completed-vs-planned emphasis, feedback/evaluation presentation, week focus/status placement, navigation and mobile visual hierarchy before production cutover.",
    ),
    CutoverSurface(
        "manual_activity_truth",
        "migrated",
        "Manual completed activities are fail-closed typed factual context read from canonical planned_workouts.payload and rendered separately from imported activities.",
    ),
    CutoverSurface(
        "goal_page",
        "separate",
        "The existing goal page may remain separately generated during main training-page cutover, provided the v2 shell preserves its link.",
    ),
    CutoverSurface(
        "goal_link",
        "migrated",
        "The v2 publication shell retains the canonical /träning/malbild-2027/ route.",
    ),
    CutoverSurface(
        "system_reference_tools",
        "migrated",
        "The v2 publication shell preserves Styrkemall and Om systemet as accessible dialog references.",
    ),
    CutoverSurface(
        "backend_status",
        "separate",
        "Operational backend health is not training read-model state and can remain an independent UI/status integration.",
    ),
    CutoverSurface(
        "legacy_card_layers",
        "blocker",
        "The mutator implementation remains a deletion target, but its user-visible presentation semantics are retained until the approved current-week experience has an equivalent pure-render contract.",
    ),
)


def blocker_keys() -> tuple[str, ...]:
    return tuple(surface.key for surface in SURFACES if surface.state == "blocker")


def cutover_ready() -> bool:
    return not blocker_keys()


def surface_map() -> dict[str, CutoverSurface]:
    return {surface.key: surface for surface in SURFACES}


def assert_contract_complete() -> None:
    keys = [surface.key for surface in SURFACES]
    if len(keys) != len(set(keys)):
        raise RuntimeError("duplicate v2 cutover surface key")
    if not any(surface.state == "migrated" for surface in SURFACES):
        raise RuntimeError("v2 cutover contract has no migrated surfaces")
