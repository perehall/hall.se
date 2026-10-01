"""Strict global Planning Engine v1 policy projection.

Global policy owns generic hard load compatibility and generic spacing
preferences. Athlete-specific calendar frequency and double-session preferences
are deliberately NOT accepted here; they belong to the athlete profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from training_core.planning.models import (
    LoadCompatibilityPolicy,
    LoadCompatibilityRule,
    LoadDimensionLevel,
    PlanningContractError,
    SameDayOrderRule,
)
from training_core.planning.objectives import (
    SpacingPreference,
    SpacingSubjectKind,
)


class PolicyProjectionError(PlanningContractError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class PlanningPolicyProjection:
    revision_id: str
    compatibility_policy: LoadCompatibilityPolicy
    spacing_preferences: tuple[SpacingPreference, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        revision = str(self.revision_id or "").strip()
        if not revision:
            raise PolicyProjectionError(
                "INVALID_V1_POLICY_CONTRACT",
                "revision_id must be non-empty",
            )
        object.__setattr__(self, "revision_id", revision)
        object.__setattr__(
            self,
            "spacing_preferences",
            tuple(self.spacing_preferences),
        )
        refs = tuple(str(item or "").strip() for item in self.source_refs)
        if not refs or any(not item for item in refs) or len(set(refs)) != len(refs):
            raise PolicyProjectionError(
                "INVALID_V1_POLICY_CONTRACT",
                "source_refs must be unique and non-empty",
            )
        object.__setattr__(self, "source_refs", refs)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyProjectionError(
            "INVALID_V1_POLICY_SOURCE",
            f"{field} must be object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise PolicyProjectionError(
            "INVALID_V1_POLICY_SOURCE",
            f"{field} must be array",
        )
    return value


def _strings(value: Any, field: str) -> tuple[str, ...]:
    return tuple(str(item) for item in _list(value, field))


def compile_policy_projection(
    canonical_policy: dict[str, Any],
) -> PlanningPolicyProjection:
    root = _mapping(canonical_policy, "canonical_policy")
    v1 = root.get("planning_engine_v1")
    if not isinstance(v1, dict):
        raise PolicyProjectionError(
            "MISSING_V1_POLICY_PROJECTION",
            "planning policy lacks explicit planning_engine_v1 section",
        )
    if v1.get("schema_version") != 1:
        raise PolicyProjectionError(
            "UNSUPPORTED_V1_POLICY_SCHEMA",
            "planning_engine_v1.schema_version must equal 1",
        )
    source = _mapping(
        v1.get("policy_revision"),
        "planning_engine_v1.policy_revision",
    )

    # Athlete schedule preferences are forbidden in global policy. This catches
    # accidental migration of onboarding/UI defaults into planner authority.
    if "objective_policy" in source or "schedule" in source:
        raise PolicyProjectionError(
            "ATHLETE_PREFERENCES_IN_GLOBAL_POLICY",
            "schedule/double-session preferences must come from athlete profile",
        )

    compatibility_source = _mapping(
        source.get("compatibility_policy"),
        "policy_revision.compatibility_policy",
    )
    rules = []
    for index, raw in enumerate(
        _list(
            compatibility_source.get("rules"),
            "policy_revision.compatibility_policy.rules",
        )
    ):
        row = _mapping(
            raw,
            f"policy_revision.compatibility_policy.rules[{index}]",
        )
        try:
            rules.append(
                LoadCompatibilityRule(
                    rule_id=str(row.get("rule_id") or ""),
                    first_dimension=str(row.get("first_dimension") or ""),
                    first_min_level=LoadDimensionLevel(
                        str(row.get("first_min_level") or "")
                    ),
                    second_dimension=str(row.get("second_dimension") or ""),
                    second_min_level=LoadDimensionLevel(
                        str(row.get("second_min_level") or "")
                    ),
                    min_calendar_separation_days=row.get(
                        "min_calendar_separation_days"
                    ),
                    min_first_to_second_days=row.get(
                        "min_first_to_second_days"
                    ),
                    min_second_to_first_days=row.get(
                        "min_second_to_first_days"
                    ),
                    same_day_order=SameDayOrderRule(
                        str(row.get("same_day_order") or "")
                    ),
                    source_refs=_strings(
                        row.get("source_refs"),
                        f"policy_revision.compatibility_policy.rules[{index}].source_refs",
                    ),
                )
            )
        except (PlanningContractError, ValueError, TypeError) as exc:
            raise PolicyProjectionError(
                "INVALID_V1_POLICY_CONTRACT",
                str(exc),
            ) from exc

    spacing = []
    for index, raw in enumerate(
        _list(
            source.get("spacing_preferences"),
            "policy_revision.spacing_preferences",
        )
    ):
        row = _mapping(
            raw,
            f"policy_revision.spacing_preferences[{index}]",
        )
        try:
            spacing.append(
                SpacingPreference(
                    subject_kind=SpacingSubjectKind(
                        str(row.get("subject_kind") or "")
                    ),
                    subject=str(row.get("subject") or ""),
                    desired_min_gap_days=row.get("desired_min_gap_days"),
                    min_level=LoadDimensionLevel(
                        str(row.get("min_level") or "")
                    ),
                )
            )
        except (PlanningContractError, ValueError, TypeError) as exc:
            raise PolicyProjectionError(
                "INVALID_V1_POLICY_CONTRACT",
                str(exc),
            ) from exc

    try:
        compatibility = LoadCompatibilityPolicy(
            policy_id=str(compatibility_source.get("policy_id") or ""),
            rules=tuple(rules),
            source_refs=_strings(
                compatibility_source.get("source_refs"),
                "policy_revision.compatibility_policy.source_refs",
            ),
        )
        return PlanningPolicyProjection(
            revision_id=str(source.get("revision_id") or ""),
            compatibility_policy=compatibility,
            spacing_preferences=tuple(spacing),
            source_refs=_strings(
                source.get("source_refs"),
                "policy_revision.source_refs",
            ),
        )
    except (PlanningContractError, ValueError, TypeError) as exc:
        raise PolicyProjectionError(
            "INVALID_V1_POLICY_CONTRACT",
            str(exc),
        ) from exc
