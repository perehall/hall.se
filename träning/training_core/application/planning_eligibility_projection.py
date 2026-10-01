"""Athlete-specific option eligibility projection for Planning Engine v1.

Eligibility is derived only from explicit V1 dose-evidence semantics plus
canonical capability state. Recipe names, free text and calendar history are not
interpreted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from training_core.application.planning_catalog_projection import (
    DoseEvidenceMode,
    OptionDoseEvidence,
    PlanningCatalogProjection,
)
from training_core.planning.models import EligibilityKind, OptionEligibility


_EPSILON = 1e-9
_EVIDENCE_PRESENT = {"observed", "demonstrated", "tolerated", "absorbed"}


@dataclass(frozen=True)
class EligibilityProjectionBlocker:
    code: str
    capability: str
    message: str


@dataclass(frozen=True)
class EligibilityDecision:
    recipe_id: str
    dose_option_id: str
    capability: str
    eligible: bool
    kind: EligibilityKind | None
    reason_code: str
    evidence_state: str
    metric: str | None
    option_value: float | None
    reference_value: float | None
    next_progress_value: float | None


@dataclass(frozen=True)
class EligibilityProjectionResult:
    option_eligibility: tuple[OptionEligibility, ...]
    decisions: tuple[EligibilityDecision, ...]
    blockers: tuple[EligibilityProjectionBlocker, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


def _capability_states(athlete_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    root = athlete_state.get("capability_states")
    if not isinstance(root, dict):
        return {}
    rows = root.get("by_capability")
    if not isinstance(rows, dict):
        return {}
    return {
        str(key): value
        for key, value in rows.items()
        if isinstance(value, dict)
    }


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _equal(first: float, second: float) -> bool:
    return abs(first - second) <= _EPSILON


def _numeric_steps(
    catalog: PlanningCatalogProjection,
) -> dict[tuple[str, str], tuple[float, ...]]:
    result: dict[tuple[str, str], set[float]] = {}
    for basis in catalog.eligibility_basis:
        if basis.mode is not DoseEvidenceMode.NUMERIC:
            continue
        assert basis.metric is not None
        assert basis.value is not None
        result.setdefault(
            (basis.capability, basis.metric),
            set(),
        ).add(float(basis.value))
    return {
        key: tuple(sorted(values))
        for key, values in result.items()
    }


def _state_source_refs(capability: str, state: dict[str, Any]) -> tuple[str, ...]:
    refs = {f"athlete_state:capability:{capability}"}
    for row in state.get("verified_exposures") or []:
        if not isinstance(row, dict):
            continue
        activity_id = row.get("activity_id")
        if activity_id is not None:
            refs.add(f"activity:{activity_id}")
    return tuple(sorted(refs))


def _reference_numeric_state(
    state: dict[str, Any],
) -> tuple[str | None, float | None]:
    absorbed = _numeric(state.get("absorbed_value"))
    if absorbed is not None:
        return "absorbed", absorbed

    candidates = [
        value
        for value in (
            _numeric(state.get("tolerated_value")),
            _numeric(state.get("demonstrated_value")),
        )
        if value is not None
    ]
    if candidates:
        # Without absorbed evidence, use the conservative lower ceiling when
        # tolerated/demonstrated summaries differ.
        return "establish", min(candidates)
    return None, None


def _numeric_decision(
    basis: OptionDoseEvidence,
    state: dict[str, Any],
    steps: tuple[float, ...],
) -> EligibilityDecision:
    assert basis.metric is not None
    assert basis.value is not None
    evidence_state = str(state.get("evidence_state") or "missing")
    reference_mode, reference = _reference_numeric_state(state)
    option_value = float(basis.value)

    if reference is None:
        return EligibilityDecision(
            basis.recipe_id,
            basis.dose_option_id,
            basis.capability,
            False,
            None,
            "NO_NUMERIC_EVIDENCE",
            evidence_state,
            basis.metric,
            option_value,
            None,
            None,
        )

    at_or_below = [value for value in steps if value <= reference + _EPSILON]
    if not at_or_below:
        return EligibilityDecision(
            basis.recipe_id,
            basis.dose_option_id,
            basis.capability,
            False,
            None,
            "NO_CATALOG_STEP_AT_OR_BELOW_EVIDENCE",
            evidence_state,
            basis.metric,
            option_value,
            reference,
            min(steps) if steps else None,
        )

    established_step = max(at_or_below)
    higher = [value for value in steps if value > reference + _EPSILON]
    next_step = min(higher) if higher else None

    if option_value < established_step - _EPSILON:
        return EligibilityDecision(
            basis.recipe_id,
            basis.dose_option_id,
            basis.capability,
            True,
            EligibilityKind.REDUCE,
            "ELIGIBLE_REDUCE",
            evidence_state,
            basis.metric,
            option_value,
            reference,
            next_step,
        )

    if _equal(option_value, established_step):
        kind = (
            EligibilityKind.HOLD
            if reference_mode == "absorbed"
            else EligibilityKind.ESTABLISH
        )
        return EligibilityDecision(
            basis.recipe_id,
            basis.dose_option_id,
            basis.capability,
            True,
            kind,
            "ELIGIBLE_HOLD" if kind is EligibilityKind.HOLD else "ELIGIBLE_ESTABLISH",
            evidence_state,
            basis.metric,
            option_value,
            reference,
            next_step,
        )

    progression_ready = state.get("progression_ready") is True
    if (
        reference_mode == "absorbed"
        and progression_ready
        and next_step is not None
        and _equal(option_value, next_step)
    ):
        return EligibilityDecision(
            basis.recipe_id,
            basis.dose_option_id,
            basis.capability,
            True,
            EligibilityKind.PROGRESS,
            "ELIGIBLE_NEXT_PROGRESS_STEP",
            evidence_state,
            basis.metric,
            option_value,
            reference,
            next_step,
        )

    return EligibilityDecision(
        basis.recipe_id,
        basis.dose_option_id,
        basis.capability,
        False,
        None,
        (
            "PROGRESSION_NOT_READY"
            if not progression_ready
            else "ABOVE_NEXT_PROGRESS_STEP"
        ),
        evidence_state,
        basis.metric,
        option_value,
        reference,
        next_step,
    )


def _qualitative_decision(
    basis: OptionDoseEvidence,
    state: dict[str, Any],
) -> EligibilityDecision:
    evidence_state = str(state.get("evidence_state") or "missing")
    if evidence_state not in _EVIDENCE_PRESENT:
        return EligibilityDecision(
            basis.recipe_id,
            basis.dose_option_id,
            basis.capability,
            False,
            None,
            "QUALITATIVE_EVIDENCE_MISSING",
            evidence_state,
            None,
            None,
            None,
            None,
        )

    kind = (
        EligibilityKind.HOLD
        if evidence_state == "absorbed"
        else EligibilityKind.ESTABLISH
    )
    return EligibilityDecision(
        basis.recipe_id,
        basis.dose_option_id,
        basis.capability,
        True,
        kind,
        "ELIGIBLE_QUALITATIVE_HOLD"
        if kind is EligibilityKind.HOLD
        else "ELIGIBLE_QUALITATIVE_ESTABLISH",
        evidence_state,
        None,
        None,
        None,
        None,
    )


def project_option_eligibility(
    catalog: PlanningCatalogProjection,
    athlete_state: dict[str, Any],
) -> EligibilityProjectionResult:
    states = _capability_states(athlete_state)
    steps = _numeric_steps(catalog)
    decisions: list[EligibilityDecision] = []
    blockers: list[EligibilityProjectionBlocker] = []
    eligibility: list[OptionEligibility] = []

    for basis in sorted(
        catalog.eligibility_basis,
        key=lambda item: item.eligibility_key,
    ):
        state = states.get(basis.capability)
        if state is None:
            decisions.append(
                EligibilityDecision(
                    basis.recipe_id,
                    basis.dose_option_id,
                    basis.capability,
                    False,
                    None,
                    "CAPABILITY_STATE_MISSING",
                    "missing",
                    basis.metric,
                    basis.value,
                    None,
                    None,
                )
            )
            continue

        if basis.mode is DoseEvidenceMode.NUMERIC:
            state_metric = str(state.get("metric") or "").strip()
            if state_metric != basis.metric:
                blockers.append(
                    EligibilityProjectionBlocker(
                        code="CAPABILITY_METRIC_MISMATCH",
                        capability=basis.capability,
                        message=(
                            f"catalog metric {basis.metric!r} != "
                            f"athlete-state metric {state_metric!r}"
                        ),
                    )
                )
                decisions.append(
                    EligibilityDecision(
                        basis.recipe_id,
                        basis.dose_option_id,
                        basis.capability,
                        False,
                        None,
                        "CAPABILITY_METRIC_MISMATCH",
                        str(state.get("evidence_state") or "missing"),
                        basis.metric,
                        basis.value,
                        None,
                        None,
                    )
                )
                continue
            decision = _numeric_decision(
                basis,
                state,
                steps[(basis.capability, basis.metric)],
            )
        else:
            decision = _qualitative_decision(basis, state)

        decisions.append(decision)
        if not decision.eligible or decision.kind is None:
            continue
        eligibility.append(
            OptionEligibility(
                recipe_id=basis.recipe_id,
                dose_option_id=basis.dose_option_id,
                capability=basis.capability,
                kind=decision.kind,
                source_refs=tuple(
                    sorted(
                        set(basis.source_refs)
                        | set(_state_source_refs(basis.capability, state))
                    )
                ),
            )
        )

    return EligibilityProjectionResult(
        option_eligibility=tuple(
            sorted(
                eligibility,
                key=lambda item: (
                    item.recipe_id,
                    item.dose_option_id,
                    item.capability,
                ),
            )
        ),
        decisions=tuple(decisions),
        blockers=tuple(
            sorted(
                blockers,
                key=lambda item: (item.code, item.capability, item.message),
            )
        ),
    )
