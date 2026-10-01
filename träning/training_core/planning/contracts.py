"""Typed contracts for Planning Engine v1.

No solver lives here. These immutable values define the inputs/results that a
future solver must obey. Validation is deterministic and side-effect free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class ContractError(ValueError):
    pass


class ObligationRole(str, Enum):
    PRIMARY = "primary"
    PROTECTED = "protected"
    MAINTENANCE = "maintenance"
    SECONDARY = "secondary"


class PlanningStatus(str, Enum):
    CURRENT = "current"
    BLOCKED = "blocked"
    STALE = "stale"


class BoundKind(str, Enum):
    COUNT = "count"
    DURATION_MINUTES = "duration_minutes"
    DISTANCE_M = "distance_m"
    WORK_MINUTES = "work_minutes"
    REPETITIONS = "repetitions"


@dataclass(frozen=True)
class PlanningObligation:
    obligation_id: str
    capability: str
    role: ObligationRole
    priority_tier: int
    min_exposures: int
    max_useful_exposures: int
    permitted_recipe_family: tuple[str, ...]
    progression_axes: tuple[str, ...] = ()
    validity_start: str | None = None
    validity_end: str | None = None
    partial_coverage: Mapping[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.obligation_id.strip():
            raise ContractError("obligation_id must be non-empty")
        if not self.capability.strip():
            raise ContractError("capability must be non-empty")
        if self.priority_tier < 1:
            raise ContractError("priority_tier must be >= 1")
        if self.min_exposures < 0:
            raise ContractError("min_exposures must be >= 0")
        if self.max_useful_exposures < self.min_exposures:
            raise ContractError("max_useful_exposures must be >= min_exposures")
        if self.max_useful_exposures == 0 and self.min_exposures != 0:
            raise ContractError("zero max exposure cannot satisfy nonzero minimum")
        if self.max_useful_exposures > 0 and not self.permitted_recipe_family:
            raise ContractError("active obligation requires permitted_recipe_family")
        if len(set(self.permitted_recipe_family)) != len(self.permitted_recipe_family):
            raise ContractError("permitted_recipe_family must not contain duplicates")
        if len(set(self.progression_axes)) != len(self.progression_axes):
            raise ContractError("progression_axes must not contain duplicates")
        for source_capability, credit in self.partial_coverage.items():
            if not str(source_capability).strip():
                raise ContractError("partial_coverage capability must be non-empty")
            if not isinstance(credit, (int, float)) or not 0 < float(credit) <= 1:
                raise ContractError("partial_coverage credit must be in (0, 1]")


@dataclass(frozen=True)
class LoadBound:
    dimension: str
    kind: BoundKind
    maximum: float
    provenance: str
    rolling_window_hours: int | None = None
    capability: str | None = None

    def validate(self) -> None:
        if not self.dimension.strip():
            raise ContractError("load dimension must be non-empty")
        if not isinstance(self.maximum, (int, float)) or self.maximum < 0:
            raise ContractError("load maximum must be >= 0")
        if not self.provenance.strip():
            raise ContractError("every load bound requires provenance")
        if self.rolling_window_hours is not None and self.rolling_window_hours <= 0:
            raise ContractError("rolling_window_hours must be > 0")


@dataclass(frozen=True)
class AggregateLoadEnvelope:
    envelope_id: str
    bounds: tuple[LoadBound, ...]
    source_revision: str
    baseline_reference: str | None = None
    uncertainty_notes: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.envelope_id.strip():
            raise ContractError("envelope_id must be non-empty")
        if not self.source_revision.strip():
            raise ContractError("source_revision must be non-empty")
        seen: set[tuple[str, BoundKind, int | None, str | None]] = set()
        for bound in self.bounds:
            bound.validate()
            key = (
                bound.dimension,
                bound.kind,
                bound.rolling_window_hours,
                bound.capability,
            )
            if key in seen:
                raise ContractError(
                    "duplicate load bound for dimension/kind/window/capability"
                )
            seen.add(key)


@dataclass(frozen=True)
class PlanFreshness:
    status: PlanningStatus
    source_revision: str
    semantic_input_hash: str
    plan_content_hash: str | None = None
    supersedes_revision: str | None = None

    def validate(self) -> None:
        if not self.source_revision.strip():
            raise ContractError("source_revision must be non-empty")
        if not self.semantic_input_hash.strip():
            raise ContractError("semantic_input_hash must be non-empty")
        if self.status is PlanningStatus.CURRENT and not self.plan_content_hash:
            raise ContractError("current plan requires plan_content_hash")
        if self.status in {PlanningStatus.BLOCKED, PlanningStatus.STALE} and self.plan_content_hash:
            raise ContractError(
                "blocked/stale state must not masquerade as current PlanContent"
            )


@dataclass(frozen=True)
class PlanningBlocked:
    source_revision: str
    semantic_input_hash: str
    reason_codes: tuple[str, ...]
    involved_refs: tuple[str, ...] = ()
    unsatisfied_obligation_ids: tuple[str, ...] = ()
    stale_workout_keys: tuple[str, ...] = ()
    user_input_required: bool = False

    def validate(self) -> None:
        if not self.source_revision.strip():
            raise ContractError("source_revision must be non-empty")
        if not self.semantic_input_hash.strip():
            raise ContractError("semantic_input_hash must be non-empty")
        if not self.reason_codes:
            raise ContractError("PlanningBlocked requires at least one reason code")
        if any(not str(code).strip() for code in self.reason_codes):
            raise ContractError("reason codes must be non-empty")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ContractError("reason codes must be unique")
        if len(set(self.stale_workout_keys)) != len(self.stale_workout_keys):
            raise ContractError("stale_workout_keys must be unique")


def validate_strategy_obligations(obligations: Sequence[PlanningObligation]) -> None:
    ids: set[str] = set()
    for obligation in obligations:
        obligation.validate()
        if obligation.obligation_id in ids:
            raise ContractError(f"duplicate obligation_id {obligation.obligation_id!r}")
        ids.add(obligation.obligation_id)


def validate_blocked_freshness_pair(
    blocked: PlanningBlocked,
    freshness: PlanFreshness,
) -> None:
    blocked.validate()
    freshness.validate()
    if freshness.status is not PlanningStatus.BLOCKED:
        raise ContractError("PlanningBlocked must pair with blocked freshness")
    if blocked.source_revision != freshness.source_revision:
        raise ContractError("blocked/freshness source revisions differ")
    if blocked.semantic_input_hash != freshness.semantic_input_hash:
        raise ContractError("blocked/freshness semantic hashes differ")
