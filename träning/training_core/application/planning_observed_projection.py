"""Strict observed-training projection for Planning Engine v1.

The projection accepts only explicit V1 activity semantics. It never derives
load levels from sport names, heart rate, free text or legacy planner matches.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from training_core.planning.models import (
    ContributionKind,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    ObligationContribution,
    ObservedCreditBasis,
    ObservedLoadExposure,
    ObservedObligationCredit,
    PlanningContractError,
    StrategyRevision,
)


class ObservedTrainingProjectionError(PlanningContractError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ObservedCapabilityEvidence:
    evidence_id: str
    exposure_ref: str
    local_date: date
    capability: str
    basis: ObservedCreditBasis
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("evidence_id", "exposure_ref", "capability"):
            value = str(getattr(self, field) or "").strip()
            if not value:
                raise ObservedTrainingProjectionError(
                    "INVALID_V1_OBSERVED_EVIDENCE",
                    f"{field} must be non-empty",
                )
            object.__setattr__(self, field, value)
        if not isinstance(self.local_date, date):
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_EVIDENCE",
                "local_date must be date",
            )
        if not isinstance(self.basis, ObservedCreditBasis):
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_EVIDENCE",
                "basis must be ObservedCreditBasis",
            )
        refs = tuple(str(item or "").strip() for item in self.source_refs)
        if not refs or any(not item for item in refs) or len(set(refs)) != len(refs):
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_EVIDENCE",
                "source_refs must be unique and non-empty",
            )
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True)
class ObservedTrainingProjection:
    revision_id: str
    coverage_from: date
    coverage_through: date
    capability_evidence: tuple[ObservedCapabilityEvidence, ...]
    load_exposures: tuple[ObservedLoadExposure, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        revision = str(self.revision_id or "").strip()
        if not revision:
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_TRAINING",
                "revision_id must be non-empty",
            )
        object.__setattr__(self, "revision_id", revision)
        if not isinstance(self.coverage_from, date) or not isinstance(
            self.coverage_through, date
        ):
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_TRAINING",
                "coverage_from/coverage_through must be dates",
            )
        if self.coverage_through < self.coverage_from:
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_TRAINING",
                "coverage_through cannot precede coverage_from",
            )

        evidence = tuple(self.capability_evidence)
        ids = [item.evidence_id for item in evidence]
        if len(set(ids)) != len(ids):
            raise ObservedTrainingProjectionError(
                "DUPLICATE_V1_OBSERVED_EVIDENCE",
                "capability evidence contains duplicate evidence_id",
            )
        semantic = [
            (
                item.exposure_ref,
                item.local_date,
                item.capability,
                item.basis,
            )
            for item in evidence
        ]
        if len(set(semantic)) != len(semantic):
            raise ObservedTrainingProjectionError(
                "DUPLICATE_V1_OBSERVED_EVIDENCE",
                "one physical exposure repeats the same capability evidence",
            )
        object.__setattr__(self, "capability_evidence", evidence)

        loads = tuple(self.load_exposures)
        load_ids = [item.exposure_id for item in loads]
        if len(set(load_ids)) != len(load_ids):
            raise ObservedTrainingProjectionError(
                "DUPLICATE_V1_OBSERVED_LOAD",
                "observed load contains duplicate exposure_id",
            )
        object.__setattr__(self, "load_exposures", loads)

        refs = tuple(str(item or "").strip() for item in self.source_refs)
        if not refs or any(not item for item in refs) or len(set(refs)) != len(refs):
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_TRAINING",
                "source_refs must be unique and non-empty",
            )
        object.__setattr__(self, "source_refs", refs)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ObservedTrainingProjectionError(
            "INVALID_V1_OBSERVED_TRAINING",
            f"{field} must be object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ObservedTrainingProjectionError(
            "INVALID_V1_OBSERVED_TRAINING",
            f"{field} must be array",
        )
    return value


def _strings(value: Any, field: str) -> tuple[str, ...]:
    return tuple(str(item) for item in _list(value, field))


def _date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise ObservedTrainingProjectionError(
            "INVALID_V1_OBSERVED_TRAINING",
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
        raise ObservedTrainingProjectionError(
            "INVALID_V1_OBSERVED_LOAD",
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
        raise ObservedTrainingProjectionError(
            "INVALID_V1_OBSERVED_LOAD",
            str(exc),
        ) from exc


def compile_observed_training_projection(
    canonical_athlete_state: dict[str, Any],
) -> ObservedTrainingProjection:
    root = _mapping(canonical_athlete_state, "canonical_athlete_state")
    v1 = root.get("planning_engine_v1")
    if not isinstance(v1, dict):
        raise ObservedTrainingProjectionError(
            "MISSING_V1_OBSERVED_TRAINING",
            "athlete state lacks explicit planning_engine_v1 section",
        )
    if v1.get("schema_version") != 1:
        raise ObservedTrainingProjectionError(
            "UNSUPPORTED_V1_OBSERVED_SCHEMA",
            "planning_engine_v1.schema_version must equal 1",
        )
    source = _mapping(
        v1.get("observed_training_revision"),
        "planning_engine_v1.observed_training_revision",
    )

    evidence_rows = _list(
        source.get("capability_evidence"),
        "observed_training_revision.capability_evidence",
    )
    evidence = []
    for index, raw in enumerate(evidence_rows):
        row = _mapping(
            raw,
            f"observed_training_revision.capability_evidence[{index}]",
        )
        try:
            basis = ObservedCreditBasis(str(row.get("basis") or ""))
        except ValueError as exc:
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_EVIDENCE",
                "unknown observed credit basis",
            ) from exc
        evidence.append(
            ObservedCapabilityEvidence(
                evidence_id=str(row.get("evidence_id") or ""),
                exposure_ref=str(row.get("exposure_ref") or ""),
                local_date=_date(
                    row.get("local_date"),
                    f"observed_training_revision.capability_evidence[{index}].local_date",
                ),
                capability=str(row.get("capability") or ""),
                basis=basis,
                source_refs=_strings(
                    row.get("source_refs"),
                    f"observed_training_revision.capability_evidence[{index}].source_refs",
                ),
            )
        )

    load_rows = _list(
        source.get("load_exposures"),
        "observed_training_revision.load_exposures",
    )
    loads = []
    for index, raw in enumerate(load_rows):
        row = _mapping(
            raw,
            f"observed_training_revision.load_exposures[{index}]",
        )
        dimensions = tuple(
            _dimension(
                _mapping(
                    item,
                    f"observed_training_revision.load_exposures[{index}].load_dimensions[{dimension_index}]",
                ),
                f"observed_training_revision.load_exposures[{index}].load_dimensions[{dimension_index}]",
            )
            for dimension_index, item in enumerate(
                _list(
                    row.get("load_dimensions"),
                    f"observed_training_revision.load_exposures[{index}].load_dimensions",
                )
            )
        )
        quantitative = tuple(
            _load(
                _mapping(
                    item,
                    f"observed_training_revision.load_exposures[{index}].quantitative_load[{load_index}]",
                ),
                f"observed_training_revision.load_exposures[{index}].quantitative_load[{load_index}]",
            )
            for load_index, item in enumerate(
                _list(
                    row.get("quantitative_load", []),
                    f"observed_training_revision.load_exposures[{index}].quantitative_load",
                )
            )
        )
        try:
            loads.append(
                ObservedLoadExposure(
                    exposure_id=str(row.get("exposure_id") or ""),
                    local_date=_date(
                        row.get("local_date"),
                        f"observed_training_revision.load_exposures[{index}].local_date",
                    ),
                    load_dimensions=dimensions,
                    quantitative_load=quantitative,
                    source_refs=_strings(
                        row.get("source_refs"),
                        f"observed_training_revision.load_exposures[{index}].source_refs",
                    ),
                    within_day_order=row.get("within_day_order"),
                )
            )
        except PlanningContractError as exc:
            raise ObservedTrainingProjectionError(
                "INVALID_V1_OBSERVED_LOAD",
                str(exc),
            ) from exc

    coverage_from = _date(
        source.get("coverage_from"),
        "observed_training_revision.coverage_from",
    )
    coverage_through = _date(
        source.get("coverage_through"),
        "observed_training_revision.coverage_through",
    )

    expected_activity_refs = {
        f"activity:{item.get('id')}"
        for item in root.get("recent_sessions", [])
        if isinstance(item, dict)
        and item.get("id") is not None
        and str(item.get("classification") or "") == "training"
        and coverage_from
        <= _date(
            item.get("date"),
            "recent_sessions[].date",
        )
        <= coverage_through
    }
    actual_activity_refs = {
        item.exposure_id
        for item in loads
        if item.exposure_id.startswith("activity:")
    }

    missing_activity_refs = sorted(
        expected_activity_refs - actual_activity_refs
    )
    unexpected_activity_refs = sorted(
        actual_activity_refs - expected_activity_refs
    )
    if missing_activity_refs or unexpected_activity_refs:
        raise ObservedTrainingProjectionError(
            "INCOMPLETE_V1_OBSERVED_LOAD_COVERAGE",
            (
                f"missing={missing_activity_refs} "
                f"unexpected={unexpected_activity_refs}"
            ),
        )

    fact_window = root.get("fact_window")
    if isinstance(fact_window, dict):
        fact_start = _date(fact_window.get("start"), "fact_window.start")
        fact_end = _date(fact_window.get("end"), "fact_window.end")
        if coverage_from < fact_start or coverage_through > fact_end:
            raise ObservedTrainingProjectionError(
                "V1_OBSERVED_COVERAGE_OUTSIDE_FACT_WINDOW",
                (
                    f"coverage={coverage_from.isoformat()}.."
                    f"{coverage_through.isoformat()} fact_window="
                    f"{fact_start.isoformat()}..{fact_end.isoformat()}"
                ),
            )

    return ObservedTrainingProjection(
        revision_id=str(source.get("revision_id") or ""),
        coverage_from=coverage_from,
        coverage_through=coverage_through,
        capability_evidence=tuple(evidence),
        load_exposures=tuple(loads),
        source_refs=_strings(
            source.get("source_refs"),
            "observed_training_revision.source_refs",
        ),
    )


def map_observed_obligation_credits(
    projection: ObservedTrainingProjection,
    strategy: StrategyRevision,
) -> tuple[ObservedObligationCredit, ...]:
    credits: list[ObservedObligationCredit] = []
    seen = set()

    for evidence in projection.capability_evidence:
        for obligation in strategy.obligations:
            if not obligation.active_on(evidence.local_date):
                continue
            if not obligation.accepts_observed_basis(evidence.basis):
                continue

            if evidence.capability == obligation.capability:
                contribution = ObligationContribution(
                    obligation_id=obligation.obligation_id,
                    source_capability=evidence.capability,
                    kind=ContributionKind.DIRECT,
                    credit_numerator=1,
                    credit_denominator=1,
                )
            else:
                rule = next(
                    (
                        item
                        for item in obligation.partial_coverage
                        if item.source_capability == evidence.capability
                    ),
                    None,
                )
                if rule is None:
                    continue
                contribution = ObligationContribution(
                    obligation_id=obligation.obligation_id,
                    source_capability=evidence.capability,
                    kind=ContributionKind.PARTIAL,
                    credit_numerator=rule.credit_numerator,
                    credit_denominator=rule.credit_denominator,
                )

            semantic = (
                evidence.exposure_ref,
                obligation.obligation_id,
                evidence.capability,
                evidence.basis,
            )
            if semantic in seen:
                continue
            seen.add(semantic)
            credits.append(
                ObservedObligationCredit(
                    local_date=evidence.local_date,
                    contribution=contribution,
                    basis=evidence.basis,
                    source_refs=tuple(
                        sorted(
                            set(evidence.source_refs)
                            | {f"observed_evidence:{evidence.evidence_id}"}
                        )
                    ),
                )
            )

    return tuple(
        sorted(
            credits,
            key=lambda item: (
                item.local_date,
                item.contribution.obligation_id,
                item.contribution.source_capability,
                item.basis.value,
            ),
        )
    )
