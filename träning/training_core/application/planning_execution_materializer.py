"""Materialize dated Planning Engine v1 execution facts from owned sources.

Hard availability comes from the canonical saved athlete profile. Fixed
commitments come only from an explicit typed commitment source. Profile free
text is intentionally ignored.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any

from training_core.application.planning_execution_facts_projection import (
    ExecutionFactsProjection,
    ExecutionFactsProjectionError,
    compile_execution_facts_projection,
)


WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            f"{field} must be object",
        )
    return value


def _profile_payload(record: dict[str, Any]) -> tuple[dict[str, Any], int]:
    root = _mapping(record, "canonical_profile_record")
    if root.get("status") != "found":
        raise ExecutionFactsProjectionError(
            "MISSING_CANONICAL_ATHLETE_PROFILE",
            "canonical athlete profile was not found",
        )
    profile = _mapping(root.get("profile"), "canonical_profile_record.profile")
    if profile.get("status") != "complete":
        raise ExecutionFactsProjectionError(
            "ATHLETE_PROFILE_NOT_COMPLETE",
            "execution facts require a completed athlete profile",
        )
    revision = root.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "profile revision must be a positive integer",
        )
    return profile, revision


def _typed_commitment_revision(
    document: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], tuple[str, ...]]:
    root = _mapping(document, "canonical_fixed_commitments")
    v1 = root.get("planning_engine_v1")
    if not isinstance(v1, dict):
        raise ExecutionFactsProjectionError(
            "MISSING_TYPED_FIXED_COMMITMENTS",
            "fixed commitments lack explicit planning_engine_v1 section",
        )
    if v1.get("schema_version") != 1:
        raise ExecutionFactsProjectionError(
            "UNSUPPORTED_TYPED_FIXED_COMMITMENTS_SCHEMA",
            "planning_engine_v1.schema_version must equal 1",
        )
    source = _mapping(
        v1.get("fixed_commitments_revision"),
        "planning_engine_v1.fixed_commitments_revision",
    )
    revision = str(source.get("revision_id") or "").strip()
    if not revision:
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "fixed commitment revision_id must be non-empty",
        )
    rows = source.get("commitments")
    if not isinstance(rows, list):
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "fixed_commitments_revision.commitments must be array",
        )
    refs = tuple(str(item or "").strip() for item in source.get("source_refs", []))
    if not refs or any(not item for item in refs):
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "fixed commitment source_refs must be non-empty",
        )
    return revision, rows, refs


def _typed_prewindow_revision(
    document: dict[str, Any] | None,
) -> tuple[str | None, date | None, date | None, list[dict[str, Any]], tuple[str, ...]]:
    if document is None:
        return None, None, None, [], ()
    root = _mapping(document, "canonical_prewindow_load_context")
    v1 = _mapping(
        root.get("planning_engine_v1"),
        "canonical_prewindow_load_context.planning_engine_v1",
    )
    if v1.get("schema_version") != 1:
        raise ExecutionFactsProjectionError(
            "UNSUPPORTED_PREWINDOW_CONTEXT_SCHEMA",
            "planning_engine_v1.schema_version must equal 1",
        )
    source = _mapping(
        v1.get("prewindow_load_context_revision"),
        "planning_engine_v1.prewindow_load_context_revision",
    )
    revision = str(source.get("revision_id") or "").strip()
    if not revision:
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "prewindow context revision_id must be non-empty",
        )
    coverage_from = _iso_day(
        source.get("coverage_from"),
        "prewindow_load_context_revision.coverage_from",
    )
    coverage_through = _iso_day(
        source.get("coverage_through"),
        "prewindow_load_context_revision.coverage_through",
    )
    if coverage_through < coverage_from:
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "prewindow context coverage cannot run backwards",
        )
    rows = source.get("commitments")
    if not isinstance(rows, list):
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "prewindow context commitments must be array",
        )
    refs = tuple(str(item or "").strip() for item in source.get("source_refs", []))
    if not refs or any(not item for item in refs):
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "prewindow context source_refs must be non-empty",
        )
    return revision, coverage_from, coverage_through, rows, refs


def _iso_day(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            f"{field} must be ISO date",
        ) from exc


def _raw_duration_upper_minutes(row: dict[str, Any]) -> float | None:
    loads = row.get("quantitative_load", [])
    if not isinstance(loads, list):
        return None
    matches = [
        item
        for item in loads
        if isinstance(item, dict)
        and item.get("scope") == "global"
        and item.get("subject") == "training_duration"
        and item.get("metric") == "duration"
        and item.get("unit") == "minutes"
    ]
    if not matches:
        return None
    values = []
    for item in matches:
        value = item.get("max_value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        values.append(float(value))
    return sum(values)


def materialize_execution_facts_document(
    *,
    canonical_profile_record: dict[str, Any],
    canonical_fixed_commitments: dict[str, Any],
    canonical_prewindow_load_context: dict[str, Any] | None = None,
    affected_from: date,
    affected_until: date,
    future_context_through: date,
    planning_date: date,
) -> dict[str, Any]:
    if not all(
        isinstance(item, date)
        for item in (
            affected_from,
            affected_until,
            future_context_through,
            planning_date,
        )
    ):
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "planning window values must be dates",
        )
    if affected_until < affected_from:
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "affected_until cannot precede affected_from",
        )
    if future_context_through < affected_until:
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "future_context_through cannot precede affected_until",
        )

    profile, profile_revision = _profile_payload(canonical_profile_record)
    availability_template = _mapping(
        profile.get("availability"),
        "profile.availability",
    )
    missing_weekdays = [
        key for key in WEEKDAY_KEYS if key not in availability_template
    ]
    if missing_weekdays:
        raise ExecutionFactsProjectionError(
            "INCOMPLETE_PROFILE_AVAILABILITY",
            ", ".join(missing_weekdays),
        )

    availability = []
    day = affected_from
    while day <= affected_until:
        key = WEEKDAY_KEYS[day.weekday()]
        row = _mapping(
            availability_template.get(key),
            f"profile.availability.{key}",
        )
        available = row.get("available")
        if not isinstance(available, bool):
            raise ExecutionFactsProjectionError(
                "INVALID_PROFILE_AVAILABILITY",
                f"{key}.available must be boolean",
            )
        minutes = row.get("minutes")
        if minutes is not None and (
            isinstance(minutes, bool)
            or not isinstance(minutes, int)
            or minutes < 0
        ):
            raise ExecutionFactsProjectionError(
                "INVALID_PROFILE_AVAILABILITY",
                f"{key}.minutes must be non-negative integer or null",
            )
        availability.append(
            {
                "local_date": day.isoformat(),
                "available": available,
                "max_sessions": 0 if not available else None,
                "max_duration_minutes": (
                    0 if not available
                    else minutes
                ),
                "source_refs": [
                    f"athlete_profile:revision:{profile_revision}",
                    f"athlete_profile:availability:{key}",
                ],
            }
        )
        day += timedelta(days=1)

    fixed_revision, commitment_rows, fixed_refs = _typed_commitment_revision(
        canonical_fixed_commitments
    )
    (
        prewindow_revision,
        prewindow_coverage_from,
        prewindow_coverage_through,
        prewindow_rows,
        prewindow_refs,
    ) = _typed_prewindow_revision(canonical_prewindow_load_context)
    if prewindow_coverage_from is not None:
        if prewindow_coverage_from < planning_date:
            raise ExecutionFactsProjectionError(
                "INVALID_PREWINDOW_CONTEXT_COVERAGE",
                "prewindow load context cannot begin before planning_date",
            )
        if prewindow_coverage_through is None or prewindow_coverage_through >= affected_from:
            raise ExecutionFactsProjectionError(
                "INVALID_PREWINDOW_CONTEXT_COVERAGE",
                "prewindow load context must end before affected_from",
            )

    commitments = []
    for index, raw in enumerate(commitment_rows):
        row = _mapping(
            raw,
            f"fixed_commitments_revision.commitments[{index}]",
        )
        local_date = _iso_day(
            row.get("local_date"),
            f"fixed_commitments_revision.commitments[{index}].local_date",
        )
        if local_date < planning_date or local_date > future_context_through:
            continue
        # Preserve the typed semantics exactly. The downstream strict compiler
        # validates them; this layer never guesses dimensions or intensity.
        commitments.append(row)

    for index, raw in enumerate(prewindow_rows):
        row = _mapping(
            raw,
            f"prewindow_load_context_revision.commitments[{index}]",
        )
        local_date = _iso_day(
            row.get("local_date"),
            f"prewindow_load_context_revision.commitments[{index}].local_date",
        )
        if (
            prewindow_coverage_from is None
            or prewindow_coverage_through is None
            or not prewindow_coverage_from <= local_date <= prewindow_coverage_through
        ):
            raise ExecutionFactsProjectionError(
                "INVALID_PREWINDOW_CONTEXT_COVERAGE",
                "prewindow commitment lies outside declared coverage",
            )
        commitments.append(row)

    ids = [str(item.get("commitment_id") or "") for item in commitments]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ExecutionFactsProjectionError(
            "INVALID_EXECUTION_MATERIALIZER_SOURCE",
            "merged fixed/prewindow commitments require unique non-empty ids",
        )

    # A finite daily time budget plus a same-day fixed commitment whose
    # duration is unknown leaves no provable residual time for mutable
    # training. Preserve the commitment without inventing a duration by
    # saturating session capacity for that date. The generic final validator
    # remains strict.
    for availability_row in availability:
        if not availability_row["available"]:
            continue
        if availability_row["max_duration_minutes"] is None:
            continue
        day = _iso_day(
            availability_row["local_date"],
            "availability.local_date",
        )
        same_day_fixed = [
            row
            for row in commitments
            if _iso_day(row.get("local_date"), "commitment.local_date") == day
        ]
        unknown_duration = [
            row
            for row in same_day_fixed
            if _raw_duration_upper_minutes(row) is None
        ]
        if not unknown_duration:
            continue
        fixed_count = len(same_day_fixed)
        existing_session_cap = availability_row.get("max_sessions")
        if (
            existing_session_cap is None
            or existing_session_cap > fixed_count
        ):
            availability_row["max_sessions"] = fixed_count
        availability_row["max_duration_minutes"] = None
        availability_row["source_refs"] = list(
            dict.fromkeys(
                [
                    *availability_row["source_refs"],
                    "planning_v1:unknown_fixed_duration:no_proven_residual_time",
                    *[
                        f"fixed_commitment:{row.get('commitment_id')}"
                        for row in unknown_duration
                    ],
                ]
            )
        )

    closed_dates = []
    day = affected_from
    while day <= affected_until:
        if day < planning_date:
            closed_dates.append(day.isoformat())
        day += timedelta(days=1)

    semantic = {
        "profile_revision": profile_revision,
        "fixed_revision": fixed_revision,
        "prewindow_revision": prewindow_revision,
        "prewindow_coverage_from": (
            prewindow_coverage_from.isoformat()
            if prewindow_coverage_from is not None
            else None
        ),
        "prewindow_coverage_through": (
            prewindow_coverage_through.isoformat()
            if prewindow_coverage_through is not None
            else None
        ),
        "affected_from": affected_from.isoformat(),
        "affected_until": affected_until.isoformat(),
        "future_context_through": future_context_through.isoformat(),
        "planning_date": planning_date.isoformat(),
        "availability": availability,
        "commitments": commitments,
    }
    digest = hashlib.sha256(
        json.dumps(
            semantic,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    source_refs = list(
        dict.fromkeys(
            [
                f"athlete_profile:revision:{profile_revision}",
                f"fixed_commitments:{fixed_revision}",
                *fixed_refs,
                *(
                    [f"prewindow_context:{prewindow_revision}"]
                    if prewindow_revision is not None
                    else []
                ),
                *prewindow_refs,
            ]
        )
    )
    document = {
        "planning_engine_v1": {
            "schema_version": 1,
            "execution_facts_revision": {
                "revision_id": f"execution:{digest}",
                "source_refs": source_refs,
                "fixed_commitments": commitments,
                "prewindow_load_context": (
                    {
                        "coverage_from": prewindow_coverage_from.isoformat(),
                        "coverage_through": prewindow_coverage_through.isoformat(),
                    }
                    if prewindow_coverage_from is not None
                    and prewindow_coverage_through is not None
                    else None
                ),
                "availability": availability,
                "closed_dates": closed_dates,
            },
        },
    }
    return document


def materialize_execution_facts(
    *,
    canonical_profile_record: dict[str, Any],
    canonical_fixed_commitments: dict[str, Any],
    canonical_prewindow_load_context: dict[str, Any] | None = None,
    affected_from: date,
    affected_until: date,
    future_context_through: date,
    planning_date: date,
) -> ExecutionFactsProjection:
    """Compile the exact document produced by the owned-source materializer."""

    document = materialize_execution_facts_document(
        canonical_profile_record=canonical_profile_record,
        canonical_fixed_commitments=canonical_fixed_commitments,
        canonical_prewindow_load_context=canonical_prewindow_load_context,
        affected_from=affected_from,
        affected_until=affected_until,
        future_context_through=future_context_through,
        planning_date=planning_date,
    )
    return compile_execution_facts_projection(document)
