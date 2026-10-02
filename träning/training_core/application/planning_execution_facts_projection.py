"""Strict future execution-facts projection for Planning Engine v1.

Fixed commitments and availability are facts, not planner output. This compiler
accepts only an explicit V1 facts revision and never parses profile free text or
legacy calendar rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from training_core.planning.models import (
    DailyAvailability,
    FixedLoadCommitment,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    PlanningContractError,
)


class ExecutionFactsProjectionError(PlanningContractError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ExecutionFactsProjection:
    revision_id: str
    fixed_commitments: tuple[FixedLoadCommitment, ...]
    availability: tuple[DailyAvailability, ...]
    closed_dates: tuple[date, ...]
    source_refs: tuple[str, ...]
    prewindow_load_context_from: date | None = None
    prewindow_load_context_through: date | None = None

    def __post_init__(self) -> None:
        revision = str(self.revision_id or "").strip()
        if not revision:
            raise ExecutionFactsProjectionError(
                "INVALID_V1_EXECUTION_FACTS",
                "revision_id must be non-empty",
            )
        object.__setattr__(self, "revision_id", revision)

        commitments = tuple(self.fixed_commitments)
        ids = [item.commitment_id for item in commitments]
        if len(set(ids)) != len(ids):
            raise ExecutionFactsProjectionError(
                "DUPLICATE_V1_FIXED_COMMITMENT",
                "fixed commitments contain duplicate ids",
            )
        object.__setattr__(self, "fixed_commitments", commitments)

        availability = tuple(self.availability)
        days = [item.local_date for item in availability]
        if len(set(days)) != len(days):
            raise ExecutionFactsProjectionError(
                "DUPLICATE_V1_AVAILABILITY",
                "availability contains duplicate dates",
            )
        object.__setattr__(self, "availability", availability)

        closed = tuple(self.closed_dates)
        if len(set(closed)) != len(closed):
            raise ExecutionFactsProjectionError(
                "DUPLICATE_V1_CLOSED_DATE",
                "closed_dates contains duplicates",
            )
        object.__setattr__(self, "closed_dates", tuple(sorted(closed)))

        refs = tuple(str(item or "").strip() for item in self.source_refs)
        if not refs or any(not item for item in refs) or len(set(refs)) != len(refs):
            raise ExecutionFactsProjectionError(
                "INVALID_V1_EXECUTION_FACTS",
                "source_refs must be unique and non-empty",
            )
        object.__setattr__(self, "source_refs", refs)

        coverage_from = self.prewindow_load_context_from
        coverage_through = self.prewindow_load_context_through
        if (coverage_from is None) != (coverage_through is None):
            raise ExecutionFactsProjectionError(
                "INVALID_V1_EXECUTION_FACTS",
                "prewindow load context requires both coverage bounds",
            )
        if coverage_from is not None:
            if not isinstance(coverage_from, date) or not isinstance(
                coverage_through,
                date,
            ):
                raise ExecutionFactsProjectionError(
                    "INVALID_V1_EXECUTION_FACTS",
                    "prewindow load context coverage must use dates",
                )
            if coverage_through < coverage_from:
                raise ExecutionFactsProjectionError(
                    "INVALID_V1_EXECUTION_FACTS",
                    "prewindow load context coverage cannot run backwards",
                )


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionFactsProjectionError(
            "INVALID_V1_EXECUTION_FACTS_SOURCE",
            f"{field} must be object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ExecutionFactsProjectionError(
            "INVALID_V1_EXECUTION_FACTS_SOURCE",
            f"{field} must be array",
        )
    return value


def _strings(value: Any, field: str) -> tuple[str, ...]:
    return tuple(str(item) for item in _list(value, field))


def _date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise ExecutionFactsProjectionError(
            "INVALID_V1_EXECUTION_FACTS_SOURCE",
            f"{field} must be ISO date",
        ) from exc


def _dimension(row: dict[str, Any], field: str) -> LoadDimensionExposure:
    try:
        return LoadDimensionExposure(
            dimension=str(row.get("dimension") or ""),
            level=LoadDimensionLevel(str(row.get("level") or "")),
            provenance_refs=_strings(
                row.get("provenance_refs"),
                f"{field}.provenance_refs",
            ),
        )
    except (PlanningContractError, ValueError) as exc:
        raise ExecutionFactsProjectionError(
            "INVALID_V1_EXECUTION_FACTS",
            str(exc),
        ) from exc


def _load(row: dict[str, Any], field: str) -> LoadEstimate:
    try:
        return LoadEstimate(
            scope=str(row.get("scope") or ""),
            subject=str(row.get("subject") or ""),
            metric=str(row.get("metric") or ""),
            unit=str(row.get("unit") or ""),
            min_value=row.get("min_value"),
            max_value=row.get("max_value"),
            provenance_refs=_strings(
                row.get("provenance_refs"),
                f"{field}.provenance_refs",
            ),
        )
    except PlanningContractError as exc:
        raise ExecutionFactsProjectionError(
            "INVALID_V1_EXECUTION_FACTS",
            str(exc),
        ) from exc


def compile_execution_facts_projection(
    canonical_execution_facts: dict[str, Any],
) -> ExecutionFactsProjection:
    root = _mapping(canonical_execution_facts, "canonical_execution_facts")
    v1 = root.get("planning_engine_v1")
    if not isinstance(v1, dict):
        raise ExecutionFactsProjectionError(
            "MISSING_V1_EXECUTION_FACTS",
            "execution facts lack explicit planning_engine_v1 section",
        )
    if v1.get("schema_version") != 1:
        raise ExecutionFactsProjectionError(
            "UNSUPPORTED_V1_EXECUTION_FACTS_SCHEMA",
            "planning_engine_v1.schema_version must equal 1",
        )
    source = _mapping(
        v1.get("execution_facts_revision"),
        "planning_engine_v1.execution_facts_revision",
    )

    commitments = []
    for index, raw in enumerate(
        _list(
            source.get("fixed_commitments"),
            "execution_facts_revision.fixed_commitments",
        )
    ):
        row = _mapping(
            raw,
            f"execution_facts_revision.fixed_commitments[{index}]",
        )
        try:
            commitments.append(
                FixedLoadCommitment(
                    commitment_id=str(row.get("commitment_id") or ""),
                    local_date=_date(
                        row.get("local_date"),
                        f"execution_facts_revision.fixed_commitments[{index}].local_date",
                    ),
                    label=str(row.get("label") or ""),
                    load_dimensions=tuple(
                        _dimension(
                            _mapping(
                                item,
                                f"execution_facts_revision.fixed_commitments[{index}].load_dimensions[{dimension_index}]",
                            ),
                            f"execution_facts_revision.fixed_commitments[{index}].load_dimensions[{dimension_index}]",
                        )
                        for dimension_index, item in enumerate(
                            _list(
                                row.get("load_dimensions"),
                                f"execution_facts_revision.fixed_commitments[{index}].load_dimensions",
                            )
                        )
                    ),
                    quantitative_load=tuple(
                        _load(
                            _mapping(
                                item,
                                f"execution_facts_revision.fixed_commitments[{index}].quantitative_load[{load_index}]",
                            ),
                            f"execution_facts_revision.fixed_commitments[{index}].quantitative_load[{load_index}]",
                        )
                        for load_index, item in enumerate(
                            _list(
                                row.get("quantitative_load", []),
                                f"execution_facts_revision.fixed_commitments[{index}].quantitative_load",
                            )
                        )
                    ),
                    source_refs=_strings(
                        row.get("source_refs"),
                        f"execution_facts_revision.fixed_commitments[{index}].source_refs",
                    ),
                    within_day_order=row.get("within_day_order"),
                )
            )
        except PlanningContractError as exc:
            raise ExecutionFactsProjectionError(
                "INVALID_V1_EXECUTION_FACTS",
                str(exc),
            ) from exc

    availability = []
    for index, raw in enumerate(
        _list(
            source.get("availability"),
            "execution_facts_revision.availability",
        )
    ):
        row = _mapping(
            raw,
            f"execution_facts_revision.availability[{index}]",
        )
        try:
            availability.append(
                DailyAvailability(
                    local_date=_date(
                        row.get("local_date"),
                        f"execution_facts_revision.availability[{index}].local_date",
                    ),
                    available=row.get("available"),
                    max_sessions=row.get("max_sessions"),
                    max_duration_minutes=row.get("max_duration_minutes"),
                    source_refs=_strings(
                        row.get("source_refs"),
                        f"execution_facts_revision.availability[{index}].source_refs",
                    ),
                )
            )
        except PlanningContractError as exc:
            raise ExecutionFactsProjectionError(
                "INVALID_V1_EXECUTION_FACTS",
                str(exc),
            ) from exc

    prewindow = source.get("prewindow_load_context")
    prewindow_from = None
    prewindow_through = None
    if prewindow is not None:
        prewindow = _mapping(
            prewindow,
            "execution_facts_revision.prewindow_load_context",
        )
        prewindow_from = _date(
            prewindow.get("coverage_from"),
            "execution_facts_revision.prewindow_load_context.coverage_from",
        )
        prewindow_through = _date(
            prewindow.get("coverage_through"),
            "execution_facts_revision.prewindow_load_context.coverage_through",
        )

    return ExecutionFactsProjection(
        revision_id=str(source.get("revision_id") or ""),
        fixed_commitments=tuple(commitments),
        availability=tuple(availability),
        closed_dates=tuple(
            _date(
                value,
                f"execution_facts_revision.closed_dates[{index}]",
            )
            for index, value in enumerate(
                _list(
                    source.get("closed_dates"),
                    "execution_facts_revision.closed_dates",
                )
            )
        ),
        source_refs=_strings(
            source.get("source_refs"),
            "execution_facts_revision.source_refs",
        ),
        prewindow_load_context_from=prewindow_from,
        prewindow_load_context_through=prewindow_through,
    )
