#!/usr/bin/env python3
"""Read-only Planning Engine v1 canonical-source readiness probe.

The probe never runs the solver and never writes runtime state. Repository
documents are inspected as canonical sources, while athlete-declared schedule
facts are read from the activated Supabase profile. Execution facts are
materialized deterministically from those owned sources. Missing typed V1
semantics remain explicit blockers; legacy planner output is never translated
to make readiness pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from athlete_profile_source import load_athlete_profile_for_planner
from planning_activity_source import load_canonical_training_activities
from training_core.application.planning_catalog_materializer import (
    CatalogMaterializationError,
    materialize_catalog_document,
)
from training_core.application.planning_execution_facts_projection import (
    ExecutionFactsProjectionError,
)
from training_core.application.planning_execution_materializer import (
    materialize_execution_facts_document,
)
from training_core.application.planning_fixed_commitments_source import (
    FixedCommitmentSourceError,
    resolve_fixed_commitments_document,
)
from training_core.application.planning_observed_materializer import (
    ObservedTrainingMaterializationError,
    materialize_observed_training_document,
)
from training_core.application.planning_projection_assembly import (
    assemble_canonical_shadow_projections,
)


HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE.parent / "data"
FIXED_COMMITMENTS_FILE = "planning_fixed_commitments.json"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object")
    return value


def _optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def diagnostic_source_revision(documents: dict[str, dict[str, Any]]) -> str:
    raw = json.dumps(
        documents,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"readiness:{digest}"


def _source_blocker(stage: str, code: str, message: str) -> dict[str, str]:
    return {
        "stage": stage,
        "code": str(code),
        "message": str(message),
    }


def _canonical_profile_record(
    loader: Callable[..., tuple[dict[str, Any] | None, dict[str, Any]]],
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, str] | None]:
    try:
        payload, metadata = loader()
    except Exception as exc:
        return None, {}, _source_blocker(
            "athlete_profile_source",
            "CANONICAL_ATHLETE_PROFILE_UNAVAILABLE",
            f"profile source failed: {type(exc).__name__}",
        )

    metadata = metadata if isinstance(metadata, dict) else {}
    safe_metadata = {
        "source": str(metadata.get("source") or "none"),
        "verified": bool(metadata.get("verified")),
        "reason": str(metadata.get("reason") or ""),
        "revision": metadata.get("revision"),
    }
    if payload is None:
        return None, safe_metadata, _source_blocker(
            "athlete_profile_source",
            "CANONICAL_ATHLETE_PROFILE_UNAVAILABLE",
            safe_metadata["reason"] or "profile source returned no active profile",
        )
    if not safe_metadata["verified"]:
        return None, safe_metadata, _source_blocker(
            "athlete_profile_source",
            "CANONICAL_ATHLETE_PROFILE_UNVERIFIED",
            safe_metadata["reason"] or "profile source is not verified",
        )

    revision = safe_metadata["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        return None, safe_metadata, _source_blocker(
            "athlete_profile_source",
            "CANONICAL_ATHLETE_PROFILE_REVISION_MISSING",
            "active profile requires a positive canonical revision",
        )

    return {
        "status": "found",
        "profile": payload,
        "revision": revision,
    }, safe_metadata, None


def build_readiness_report(
    data_dir: Path = DEFAULT_DATA,
    *,
    affected_from: date,
    affected_until: date,
    planning_date: date,
    future_context_through: date | None = None,
    profile_loader: Callable[
        ..., tuple[dict[str, Any] | None, dict[str, Any]]
    ] = load_athlete_profile_for_planner,
    activity_loader: Callable[
        [date, date], tuple[list[dict[str, Any]], dict[str, Any]]
    ] = load_canonical_training_activities,
) -> dict[str, Any]:
    """Inspect whether a real canonical shadow input can be assembled.

    The default future context closes the contract's minimum three-day
    look-ahead. Callers may provide a later date when another hard constraint
    requires a wider context.
    """

    if affected_until < affected_from:
        raise ValueError("affected_until cannot precede affected_from")
    context_through = future_context_through or (
        affected_until + timedelta(days=3)
    )
    if context_through < affected_until:
        raise ValueError("future_context_through cannot precede affected_until")

    catalog_source = _read_json(data_dir / "workout_catalog.json")
    athlete_state_source = _read_json(data_dir / "athlete_state.json")
    documents: dict[str, dict[str, Any]] = {
        "strategy": _read_json(data_dir / "training_strategy.json"),
        "catalog_source": catalog_source,
        "athlete_state_source": athlete_state_source,
        "policy": _read_json(data_dir / "planning_policy.json"),
    }
    source_blockers: list[dict[str, str]] = []

    catalog_document: dict[str, Any] | None = None
    try:
        catalog_document = materialize_catalog_document(catalog_source)
    except CatalogMaterializationError as exc:
        source_blockers.append(
            _source_blocker(
                "catalog_source",
                exc.code,
                str(exc),
            )
        )
    documents["catalog"] = catalog_document or {}

    observed_document: dict[str, Any] | None = None
    observed_metadata: dict[str, Any] = {}
    fact_window = athlete_state_source.get("fact_window")
    if not isinstance(fact_window, dict):
        source_blockers.append(
            _source_blocker(
                "observed_training_source",
                "CANONICAL_FACT_WINDOW_MISSING",
                "athlete_state.fact_window is required for observed-history coverage",
            )
        )
    else:
        try:
            coverage_from = date.fromisoformat(str(fact_window.get("start")))
            coverage_through = date.fromisoformat(str(fact_window.get("end")))
            if coverage_through < coverage_from:
                raise ValueError("coverage end precedes start")
        except Exception:
            source_blockers.append(
                _source_blocker(
                    "observed_training_source",
                    "CANONICAL_FACT_WINDOW_INVALID",
                    "athlete_state.fact_window must contain a valid start/end interval",
                )
            )
        else:
            try:
                activity_rows, observed_metadata = activity_loader(
                    coverage_from,
                    coverage_through,
                )
                observed_document = materialize_observed_training_document(
                    canonical_activities=activity_rows,
                    canonical_athlete_state=athlete_state_source,
                    canonical_catalog=catalog_source,
                    coverage_from=coverage_from,
                    coverage_through=coverage_through,
                )
            except ObservedTrainingMaterializationError as exc:
                source_blockers.append(
                    _source_blocker(
                        "observed_training_source",
                        exc.code,
                        str(exc),
                    )
                )
            except Exception as exc:
                source_blockers.append(
                    _source_blocker(
                        "observed_training_source",
                        "CANONICAL_ACTIVITY_HISTORY_UNAVAILABLE",
                        f"activity source failed: {type(exc).__name__}",
                    )
                )

    documents["athlete_state"] = observed_document or {}

    profile_record, profile_metadata, profile_blocker = _canonical_profile_record(
        profile_loader
    )
    if profile_blocker is not None:
        source_blockers.append(profile_blocker)
    documents["athlete_profile"] = profile_record or {}

    fixed_document: dict[str, Any] | None = None
    explicit_fixed = _optional_json(data_dir / FIXED_COMMITMENTS_FILE)
    if profile_record is not None:
        try:
            fixed_document = resolve_fixed_commitments_document(
                canonical_profile_record=profile_record,
                explicit_document=explicit_fixed,
            )
        except FixedCommitmentSourceError as exc:
            source_blockers.append(
                _source_blocker(
                    "fixed_commitments_source",
                    exc.code,
                    str(exc),
                )
            )

    execution_document: dict[str, Any] | None = None
    if profile_record is not None and fixed_document is not None:
        try:
            execution_document = materialize_execution_facts_document(
                canonical_profile_record=profile_record,
                canonical_fixed_commitments=fixed_document,
                affected_from=affected_from,
                affected_until=affected_until,
                future_context_through=context_through,
                planning_date=planning_date,
            )
        except ExecutionFactsProjectionError as exc:
            source_blockers.append(
                _source_blocker(
                    "execution_facts_source",
                    exc.code,
                    str(exc),
                )
            )

    documents["fixed_commitments"] = fixed_document or {}
    documents["execution_facts"] = execution_document or {}
    source_revision = diagnostic_source_revision(documents)

    result = assemble_canonical_shadow_projections(
        source_revision=source_revision,
        canonical_strategy=documents["strategy"],
        canonical_catalog=documents["catalog"],
        canonical_athlete_state=documents["athlete_state"],
        canonical_athlete_profile=documents["athlete_profile"],
        canonical_policy=documents["policy"],
        canonical_execution_facts=documents["execution_facts"],
    )

    source_stages = {item["stage"] for item in source_blockers}
    projection_blockers = []
    for item in result.blockers:
        if (
            item.stage == "catalog"
            and "catalog_source" in source_stages
        ):
            continue
        if (
            item.stage == "athlete_state"
            and "observed_training_source" in source_stages
        ):
            continue
        if (
            item.stage == "athlete_profile"
            and "athlete_profile_source" in source_stages
        ):
            continue
        if (
            item.stage == "execution_facts"
            and (
                "execution_facts_source" in source_stages
                or "fixed_commitments_source" in source_stages
                or "athlete_profile_source" in source_stages
            )
        ):
            continue
        projection_blockers.append(
            {
                "stage": item.stage,
                "code": item.code,
                "message": item.message,
            }
        )

    blockers = sorted(
        [*source_blockers, *projection_blockers],
        key=lambda item: (
            item["stage"],
            item["code"],
            item["message"],
        ),
    )
    return {
        "ready": result.ready and not source_blockers,
        "source_revision": source_revision,
        "window": {
            "affected_from": affected_from.isoformat(),
            "affected_until": affected_until.isoformat(),
            "planning_date": planning_date.isoformat(),
            "future_context_through": context_through.isoformat(),
        },
        "source_status": {
            "catalog": (
                "materialized_from_owned_source"
                if catalog_document is not None
                else "blocked"
            ),
            "observed_training": (
                {
                    "status": "materialized_from_canonical_activities",
                    **observed_metadata,
                }
                if observed_document is not None
                else {
                    "status": "blocked",
                    **observed_metadata,
                }
            ),
            "athlete_profile": profile_metadata,
            "fixed_commitments": (
                "explicit_typed_document"
                if explicit_fixed is not None
                else (
                    "profile_explicitly_empty"
                    if fixed_document is not None
                    else "blocked"
                )
            ),
            "execution_facts": (
                "materialized_from_owned_sources"
                if execution_document is not None
                else "blocked"
            ),
        },
        "component_revisions": dict(result.component_revisions),
        "blockers": blockers,
        "eligibility_decisions": [
            {
                "recipe_id": item.recipe_id,
                "dose_option_id": item.dose_option_id,
                "capability": item.capability,
                "eligible": item.eligible,
                "kind": item.kind.value if item.kind is not None else None,
                "reason_code": item.reason_code,
                "metric": item.metric,
                "option_value": item.option_value,
                "reference_value": item.reference_value,
                "next_progress_value": item.next_progress_value,
            }
            for item in result.eligibility_decisions
        ],
        "solver_ran": False,
        "production_mutated": False,
    }


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA,
    )
    parser.add_argument("--affected-from", type=_iso_date, required=True)
    parser.add_argument("--affected-until", type=_iso_date, required=True)
    parser.add_argument("--planning-date", type=_iso_date, required=True)
    parser.add_argument("--future-context-through", type=_iso_date)
    args = parser.parse_args(argv)
    report = build_readiness_report(
        args.data_dir,
        affected_from=args.affected_from,
        affected_until=args.affected_until,
        planning_date=args.planning_date,
        future_context_through=args.future_context_through,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
