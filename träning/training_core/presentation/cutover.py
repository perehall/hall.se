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
        "blocker",
        "Production requires visible sport SVG identity for planned and completed primary surfaces; v2 has no icon contract yet.",
    ),
    CutoverSurface(
        "week_context",
        "migrated",
        "Current week focus, microcycle position, plan idea and capability taxonomy are read from canonical mesocycle/microcycle PostgreSQL state.",
    ),
    CutoverSurface(
        "week_status",
        "blocker",
        "Current production exposes pass count, session time, training days and sport distribution; v2 only carries partial counts.",
    ),
    CutoverSurface(
        "device_sync_status",
        "blocker",
        "Planned syncable workouts expose Klocksync status in production; v2 does not yet surface device_sync.",
    ),
    CutoverSurface(
        "page_shell",
        "blocker",
        "V2 renderer currently emits fragments, not the complete responsive document shell used for publication.",
    ),
    CutoverSurface(
        "manual_activity_truth",
        "blocker",
        "Manual completed activities are an explicit production contract and have not yet been proven through the v2 repository path.",
    ),
    CutoverSurface(
        "goal_page",
        "separate",
        "The existing goal page may remain separately generated during main training-page cutover, provided the v2 shell preserves its link.",
    ),
    CutoverSurface(
        "goal_link",
        "blocker",
        "The main v2 shell must retain a route to the separately published goal page.",
    ),
    CutoverSurface(
        "system_reference_tools",
        "blocker",
        "The current page exposes Om systemet and Styrkemall reference tools; cutover must preserve or explicitly redesign them.",
    ),
    CutoverSurface(
        "backend_status",
        "separate",
        "Operational backend health is not training read-model state and can remain an independent UI/status integration.",
    ),
    CutoverSurface(
        "legacy_card_layers",
        "retire",
        "Historical card-v1/v2, quiet-performance and HTML post-processing layers are implementation details, not retained capabilities.",
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
