"""Strict athlete schedule-preference projection for Planning Engine v1.

The source is the canonical athlete profile returned by the profile repository.
No UI/onboarding defaults are accepted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from training_core.planning.models import PlanningContractError
from training_core.planning.objectives import (
    DoubleSessionPreference,
    SchedulePreferences,
)


class ProfileProjectionError(PlanningContractError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class AthletePlanningPreferencesProjection:
    revision_id: str
    schedule: SchedulePreferences
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        revision = str(self.revision_id or "").strip()
        if not revision:
            raise ProfileProjectionError(
                "INVALID_V1_PROFILE_CONTRACT",
                "revision_id must be non-empty",
            )
        object.__setattr__(self, "revision_id", revision)
        refs = tuple(str(item or "").strip() for item in self.source_refs)
        if not refs or any(not item for item in refs) or len(set(refs)) != len(refs):
            raise ProfileProjectionError(
                "INVALID_V1_PROFILE_CONTRACT",
                "source_refs must be unique and non-empty",
            )
        object.__setattr__(self, "source_refs", refs)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileProjectionError(
            "INVALID_V1_PROFILE_SOURCE",
            f"{field} must be object",
        )
    return value


def compile_athlete_planning_preferences(
    canonical_profile_record: dict[str, Any],
) -> AthletePlanningPreferencesProjection:
    root = _mapping(canonical_profile_record, "canonical_profile_record")
    if root.get("status") != "found":
        raise ProfileProjectionError(
            "MISSING_CANONICAL_ATHLETE_PROFILE",
            "canonical athlete profile was not found",
        )

    profile = _mapping(root.get("profile"), "canonical_profile_record.profile")
    if profile.get("status") != "complete":
        raise ProfileProjectionError(
            "ATHLETE_PROFILE_NOT_COMPLETE",
            "planning preferences require a completed athlete profile",
        )

    revision = root.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise ProfileProjectionError(
            "INVALID_V1_PROFILE_SOURCE",
            "canonical profile revision must be a positive integer",
        )

    preferences = _mapping(profile.get("preferences"), "profile.preferences")
    frequency = _mapping(
        preferences.get("frequency"),
        "profile.preferences.frequency",
    )

    required = {
        "preferred_days": frequency.get("preferred_days"),
        "min_days": frequency.get("min_days"),
        "max_days": frequency.get("max_days"),
        "double_sessions": preferences.get("double_sessions"),
    }
    missing = sorted(
        key
        for key, value in required.items()
        if value is None or (isinstance(value, str) and not value.strip())
    )
    if missing:
        raise ProfileProjectionError(
            "INCOMPLETE_ATHLETE_SCHEDULE_PREFERENCES",
            ", ".join(missing),
        )

    try:
        schedule = SchedulePreferences(
            preferred_active_days=required["preferred_days"],
            min_active_days=required["min_days"],
            max_active_days=required["max_days"],
            double_sessions=DoubleSessionPreference(
                str(required["double_sessions"])
            ),
        )
    except (PlanningContractError, ValueError, TypeError) as exc:
        raise ProfileProjectionError(
            "INVALID_V1_PROFILE_CONTRACT",
            str(exc),
        ) from exc

    return AthletePlanningPreferencesProjection(
        revision_id=f"athlete-profile:{revision}",
        schedule=schedule,
        source_refs=(
            f"athlete_profile:revision:{revision}",
            "athlete_profile:preferences:frequency",
            "athlete_profile:preferences:double_sessions",
        ),
    )
