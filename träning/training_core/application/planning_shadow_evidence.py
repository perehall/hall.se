from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ShadowEvidenceRequirements:
    min_microcycles: int = 4
    min_events: int = 20

    def __post_init__(self) -> None:
        if self.min_microcycles < 1:
            raise ValueError("min_microcycles must be >= 1")
        if self.min_events < 1:
            raise ValueError("min_events must be >= 1")


def _stable_outcome(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("solver_status"),
        row.get("plan_content_hash"),
        row.get("objective_vector"),
    )


def evaluate_shadow_evidence(
    rows: Iterable[dict[str, Any]],
    requirements: ShadowEvidenceRequirements = ShadowEvidenceRequirements(),
) -> dict[str, Any]:
    """Evaluate accumulated shadow evidence without inferring missing semantics.

    Only rows that reached readiness_status=ready and actually ran the solver
    count as validation events. BLOCKED solver outcomes remain valid evidence:
    a fail-closed engine is allowed to refuse an invalid plan. What is never
    acceptable is nondeterminism for the same semantic input and engine version.
    """

    materialized = list(rows)
    ready_rows = [
        row
        for row in materialized
        if row.get("readiness_status") == "ready"
        and row.get("solver_status") in {"current", "blocked"}
        and row.get("semantic_input_hash")
        and row.get("engine_version")
    ]

    event_keys = {
        str(row["event_key"])
        for row in ready_rows
        if row.get("event_key")
    }
    microcycles = {
        str(row["microcycle_key"])
        for row in ready_rows
        if row.get("microcycle_key")
    }

    outcomes_by_input: dict[tuple[str, str], set[tuple[Any, ...]]] = defaultdict(set)
    for row in ready_rows:
        key = (
            str(row["engine_version"]),
            str(row["semantic_input_hash"]),
        )
        outcomes_by_input[key].add(_stable_outcome(row))

    nondeterministic_inputs = [
        {
            "engine_version": engine_version,
            "semantic_input_hash": semantic_input_hash,
            "outcome_count": len(outcomes),
        }
        for (engine_version, semantic_input_hash), outcomes in sorted(outcomes_by_input.items())
        if len(outcomes) > 1
    ]

    current_count = sum(row.get("solver_status") == "current" for row in ready_rows)
    blocked_count = sum(row.get("solver_status") == "blocked" for row in ready_rows)

    blockers: list[dict[str, Any]] = []
    if len(microcycles) < requirements.min_microcycles:
        blockers.append(
            {
                "code": "INSUFFICIENT_LIVE_MICROCYCLES",
                "required": requirements.min_microcycles,
                "observed": len(microcycles),
            }
        )
    if len(event_keys) < requirements.min_events:
        blockers.append(
            {
                "code": "INSUFFICIENT_REAL_REPLANNING_EVENTS",
                "required": requirements.min_events,
                "observed": len(event_keys),
            }
        )
    if nondeterministic_inputs:
        blockers.append(
            {
                "code": "NONDETERMINISTIC_SHADOW_OUTCOME",
                "inputs": nondeterministic_inputs,
            }
        )

    return {
        "ready_for_cutover_review": not blockers,
        "requirements": {
            "min_microcycles": requirements.min_microcycles,
            "min_events": requirements.min_events,
        },
        "evidence": {
            "total_rows": len(materialized),
            "ready_solver_rows": len(ready_rows),
            "distinct_events": len(event_keys),
            "distinct_microcycles": len(microcycles),
            "current_outcomes": current_count,
            "blocked_outcomes": blocked_count,
            "microcycles": sorted(microcycles),
        },
        "blockers": blockers,
    }
