"""Strict canonical StrategyRevision projection for Planning Engine v1.

The compiler accepts only an explicit planning_engine_v1.strategy_revision
section. It never infers exposure counts, recipes or load ceilings from legacy
mesocycle/calendar output.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from training_core.planning.models import (
    AggregateLoadEnvelope,
    CoverageRule,
    LoadBound,
    ObservedCreditBasis,
    PlanningContractError,
    PlanningObligation,
    StrategyRevision,
    UnknownAggregatePolicy,
)


class StrategyProjectionError(PlanningContractError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StrategyProjectionError(
            "INVALID_V1_STRATEGY_SOURCE",
            f"{field} must be an object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise StrategyProjectionError(
            "INVALID_V1_STRATEGY_SOURCE",
            f"{field} must be an array",
        )
    return value


def _date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise StrategyProjectionError(
            "INVALID_V1_STRATEGY_SOURCE",
            f"{field} must be ISO date",
        ) from exc


def _strings(value: Any, field: str) -> tuple[str, ...]:
    rows = _list(value, field)
    return tuple(str(item) for item in rows)


def _coverage(row: dict[str, Any], field: str) -> CoverageRule:
    return CoverageRule(
        source_capability=str(row.get("source_capability") or ""),
        credit_numerator=row.get("credit_numerator"),
        credit_denominator=row.get("credit_denominator"),
    )


def _obligation(row: dict[str, Any], index: int) -> PlanningObligation:
    field = f"strategy_revision.obligations[{index}]"
    partial_rows = _list(row.get("partial_coverage", []), f"{field}.partial_coverage")
    return PlanningObligation(
        obligation_id=str(row.get("obligation_id") or ""),
        capability=str(row.get("capability") or ""),
        role=str(row.get("role") or ""),
        priority_tier=row.get("priority_tier"),
        min_exposures=row.get("min_exposures"),
        max_exposures=row.get("max_exposures"),
        recipe_family=_strings(row.get("recipe_family"), f"{field}.recipe_family"),
        valid_from=_date(row.get("valid_from"), f"{field}.valid_from"),
        valid_until=_date(row.get("valid_until"), f"{field}.valid_until"),
        source_refs=_strings(row.get("source_refs"), f"{field}.source_refs"),
        progression_axes=_strings(
            row.get("progression_axes", []),
            f"{field}.progression_axes",
        ),
        partial_coverage=tuple(
            _coverage(
                _mapping(item, f"{field}.partial_coverage[{partial_index}]"),
                f"{field}.partial_coverage[{partial_index}]",
            )
            for partial_index, item in enumerate(partial_rows)
        ),
        prefer_character_variation=bool(
            row.get("prefer_character_variation", False)
        ),
        accepted_observed_bases=tuple(
            ObservedCreditBasis(value)
            for value in _strings(
                row.get("accepted_observed_bases"),
                f"{field}.accepted_observed_bases",
            )
        ),
    )


def _bound(row: dict[str, Any], index: int) -> LoadBound:
    field = f"strategy_revision.load_envelope.bounds[{index}]"
    return LoadBound(
        bound_id=str(row.get("bound_id") or ""),
        scope=str(row.get("scope") or ""),
        subject=str(row.get("subject") or ""),
        metric=str(row.get("metric") or ""),
        unit=str(row.get("unit") or ""),
        window_days=row.get("window_days"),
        max_value=row.get("max_value"),
        provenance_refs=_strings(
            row.get("provenance_refs"),
            f"{field}.provenance_refs",
        ),
        requires_complete_coverage=row.get(
            "requires_complete_coverage",
            False,
        ),
    )


def compile_strategy_revision(
    canonical_strategy: dict[str, Any],
) -> StrategyRevision:
    root = _mapping(canonical_strategy, "canonical_strategy")
    v1 = root.get("planning_engine_v1")
    if not isinstance(v1, dict):
        raise StrategyProjectionError(
            "MISSING_V1_STRATEGY_REVISION",
            "canonical strategy lacks explicit planning_engine_v1 section",
        )
    if v1.get("schema_version") != 1:
        raise StrategyProjectionError(
            "UNSUPPORTED_V1_STRATEGY_SCHEMA",
            "planning_engine_v1.schema_version must equal 1",
        )

    source = _mapping(
        v1.get("strategy_revision"),
        "planning_engine_v1.strategy_revision",
    )
    obligations_source = _list(
        source.get("obligations"),
        "strategy_revision.obligations",
    )
    envelope_source = _mapping(
        source.get("load_envelope"),
        "strategy_revision.load_envelope",
    )
    bounds_source = _list(
        envelope_source.get("bounds"),
        "strategy_revision.load_envelope.bounds",
    )

    declared_goal_hash = (
        (root.get("goal_contract") or {}).get("goal_hash")
        if isinstance(root.get("goal_contract"), dict)
        else None
    )
    v1_goal_hash = str(source.get("goal_set_hash") or "")
    if declared_goal_hash and v1_goal_hash != str(declared_goal_hash):
        raise StrategyProjectionError(
            "STALE_V1_GOAL_SET",
            "V1 strategy goal_set_hash differs from canonical goal_contract.goal_hash",
        )

    try:
        envelope = AggregateLoadEnvelope(
            envelope_id=str(envelope_source.get("envelope_id") or ""),
            bounds=tuple(
                _bound(
                    _mapping(row, f"strategy_revision.load_envelope.bounds[{index}]"),
                    index,
                )
                for index, row in enumerate(bounds_source)
            ),
            unknown_policy=UnknownAggregatePolicy(
                str(envelope_source.get("unknown_policy") or "")
            ),
            established_baseline_ref=str(
                envelope_source.get("established_baseline_ref") or ""
            ),
            source_refs=_strings(
                envelope_source.get("source_refs"),
                "strategy_revision.load_envelope.source_refs",
            ),
        )
        return StrategyRevision(
            revision_id=str(source.get("revision_id") or ""),
            goal_set_hash=v1_goal_hash,
            valid_from=_date(source.get("valid_from"), "strategy_revision.valid_from"),
            valid_until=_date(source.get("valid_until"), "strategy_revision.valid_until"),
            obligations=tuple(
                _obligation(
                    _mapping(row, f"strategy_revision.obligations[{index}]"),
                    index,
                )
                for index, row in enumerate(obligations_source)
            ),
            load_envelope=envelope,
            source_refs=_strings(
                source.get("source_refs"),
                "strategy_revision.source_refs",
            ),
            accepted_by=str(source.get("accepted_by") or ""),
        )
    except StrategyProjectionError:
        raise
    except (PlanningContractError, ValueError, TypeError) as exc:
        raise StrategyProjectionError(
            "INVALID_V1_STRATEGY_CONTRACT",
            str(exc),
        ) from exc
