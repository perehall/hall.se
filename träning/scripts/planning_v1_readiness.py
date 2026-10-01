#!/usr/bin/env python3
"""Read-only Planning Engine v1 canonical projection readiness probe.

This command never runs the solver and never writes runtime state. It reports
which explicit V1 source projections are missing or inconsistent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from training_core.application.planning_projection_assembly import (
    assemble_canonical_shadow_projections,
)


HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE.parent / "data"
EXECUTION_FACTS_FILE = "planning_execution_facts.json"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object")
    return value


def _optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
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


def build_readiness_report(data_dir: Path = DEFAULT_DATA) -> dict[str, Any]:
    documents = {
        "strategy": _read_json(data_dir / "training_strategy.json"),
        "catalog": _read_json(data_dir / "workout_catalog.json"),
        "athlete_state": _read_json(data_dir / "athlete_state.json"),
        "policy": _read_json(data_dir / "planning_policy.json"),
        "execution_facts": _optional_json(
            data_dir / EXECUTION_FACTS_FILE
        ),
    }
    source_revision = diagnostic_source_revision(documents)
    result = assemble_canonical_shadow_projections(
        source_revision=source_revision,
        canonical_strategy=documents["strategy"],
        canonical_catalog=documents["catalog"],
        canonical_athlete_state=documents["athlete_state"],
        canonical_policy=documents["policy"],
        canonical_execution_facts=documents["execution_facts"],
    )
    return {
        "ready": result.ready,
        "source_revision": source_revision,
        "component_revisions": dict(result.component_revisions),
        "blockers": [
            {
                "stage": item.stage,
                "code": item.code,
                "message": item.message,
            }
            for item in result.blockers
        ],
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA,
    )
    args = parser.parse_args(argv)
    report = build_readiness_report(args.data_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
