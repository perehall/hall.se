"""Materialize pre-window Planning Engine v1 load context from canonical plan rows.

The relational current-plan source supplies only identity/date/structured payload.
Load semantics are copied from the explicit Planning Engine v1 workout catalog,
never inferred from session titles, stimuli text or sport labels. Typed external
fixed commitments remain owned by their dedicated source and are only matched
here to avoid duplicate load exposure.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any


class PrewindowContextMaterializationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PrewindowContextMaterializationError(
            "INVALID_PREWINDOW_CONTEXT_SOURCE",
            f"{field} must be object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise PrewindowContextMaterializationError(
            "INVALID_PREWINDOW_CONTEXT_SOURCE",
            f"{field} must be array",
        )
    return value


def _catalog_options(canonical_catalog: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    root = _mapping(canonical_catalog, "canonical_catalog")
    v1 = _mapping(root.get("planning_engine_v1"), "canonical_catalog.planning_engine_v1")
    revision = _mapping(v1.get("catalog_revision"), "planning_engine_v1.catalog_revision")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(_list(revision.get("options"), "catalog_revision.options")):
        row = _mapping(raw, f"catalog_revision.options[{index}]")
        key = (
            str(row.get("recipe_id") or "").strip(),
            str(row.get("dose_option_id") or "").strip(),
        )
        if not all(key) or key in result:
            raise PrewindowContextMaterializationError(
                "INVALID_PREWINDOW_CATALOG",
                f"invalid/duplicate catalog option {key}",
            )
        result[key] = row
    return result


def _typed_fixed_rows(canonical_fixed_commitments: dict[str, Any]) -> list[dict[str, Any]]:
    root = _mapping(canonical_fixed_commitments, "canonical_fixed_commitments")
    v1 = _mapping(root.get("planning_engine_v1"), "fixed.planning_engine_v1")
    revision = _mapping(v1.get("fixed_commitments_revision"), "fixed.fixed_commitments_revision")
    return [
        _mapping(item, f"fixed_commitments_revision.commitments[{index}]")
        for index, item in enumerate(
            _list(revision.get("commitments"), "fixed_commitments_revision.commitments")
        )
    ]


def materialize_prewindow_load_context_document(
    *,
    canonical_planned_workouts: list[dict[str, Any]],
    canonical_catalog: dict[str, Any],
    canonical_fixed_commitments: dict[str, Any],
    coverage_from: date,
    coverage_through: date,
) -> dict[str, Any]:
    if not isinstance(coverage_from, date) or not isinstance(coverage_through, date):
        raise PrewindowContextMaterializationError(
            "INVALID_PREWINDOW_CONTEXT_SOURCE",
            "coverage bounds must be dates",
        )
    if coverage_through < coverage_from:
        raise PrewindowContextMaterializationError(
            "INVALID_PREWINDOW_CONTEXT_SOURCE",
            "coverage_through cannot precede coverage_from",
        )

    options = _catalog_options(canonical_catalog)
    fixed_rows = _typed_fixed_rows(canonical_fixed_commitments)
    fixed_by_date_label: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in fixed_rows:
        key = (
            str(row.get("local_date") or "").strip(),
            str(row.get("label") or "").strip(),
        )
        fixed_by_date_label.setdefault(key, []).append(row)

    commitments: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    source_hashes: set[str] = set()

    for index, raw in enumerate(canonical_planned_workouts):
        row = _mapping(raw, f"canonical_planned_workouts[{index}]")
        workout_key = str(row.get("workout_key") or "").strip()
        if not workout_key or workout_key in seen_keys:
            raise PrewindowContextMaterializationError(
                "INVALID_PREWINDOW_CONTEXT_SOURCE",
                "planned workout keys must be unique and non-empty",
            )
        seen_keys.add(workout_key)

        try:
            local_date = date.fromisoformat(str(row.get("date") or ""))
        except Exception as exc:
            raise PrewindowContextMaterializationError(
                "INVALID_PREWINDOW_CONTEXT_SOURCE",
                f"{workout_key} has invalid date",
            ) from exc
        if not coverage_from <= local_date <= coverage_through:
            raise PrewindowContextMaterializationError(
                "PREWINDOW_ROW_OUTSIDE_COVERAGE",
                workout_key,
            )

        payload = _mapping(row.get("payload"), f"{workout_key}.payload")
        source_hash = str(row.get("last_seen_source_hash") or "").strip()
        if source_hash:
            source_hashes.add(source_hash)

        planning_status = str(
            row.get("planning_status")
            or payload.get("planning_status")
            or ""
        ).strip().lower()
        manual_lock = bool(row.get("manual_lock") or payload.get("manual_lock"))
        session = str(payload.get("session") or "").strip()

        # External/fixed load is already canonical in the typed commitment
        # source. Match only identity here; never borrow semantics from text.
        if planning_status == "fixed" or manual_lock:
            matches = fixed_by_date_label.get(
                (local_date.isoformat(), session),
                [],
            )
            if len(matches) != 1:
                raise PrewindowContextMaterializationError(
                    "PREWINDOW_FIXED_COMMITMENT_NOT_TYPED",
                    (
                        f"{workout_key} requires exactly one typed fixed commitment "
                        "with matching date/label"
                    ),
                )
            continue

        recipe_id = str(payload.get("recipe_key") or "").strip()
        resolution = payload.get("dose_resolution")
        resolution = _mapping(resolution, f"{workout_key}.payload.dose_resolution")
        dose_option_id = str(resolution.get("option_id") or "").strip()
        if not recipe_id or not dose_option_id:
            raise PrewindowContextMaterializationError(
                "PREWINDOW_STRUCTURED_IDENTITY_MISSING",
                f"{workout_key} requires recipe_key and dose_resolution.option_id",
            )
        option = options.get((recipe_id, dose_option_id))
        if option is None:
            raise PrewindowContextMaterializationError(
                "PREWINDOW_OPTION_NOT_IN_V1_CATALOG",
                f"{workout_key}: {recipe_id}/{dose_option_id}",
            )

        raw_order = payload.get("same_day_order")
        within_day_order = None
        if raw_order is not None:
            if isinstance(raw_order, bool) or not isinstance(raw_order, int) or raw_order < 0:
                raise PrewindowContextMaterializationError(
                    "INVALID_PREWINDOW_CONTEXT_SOURCE",
                    f"{workout_key}.same_day_order must be a non-negative integer",
                )
            within_day_order = raw_order + 1

        option_ref = f"v1_catalog:{recipe_id}/{dose_option_id}"
        commitments.append(
            {
                "commitment_id": f"current-plan:{workout_key}",
                "local_date": local_date.isoformat(),
                "label": session or f"{recipe_id}/{dose_option_id}",
                "load_dimensions": _list(
                    option.get("load_dimensions"),
                    f"{option_ref}.load_dimensions",
                ),
                "quantitative_load": _list(
                    option.get("quantitative_load", []),
                    f"{option_ref}.quantitative_load",
                ),
                "source_refs": list(
                    dict.fromkeys(
                        [
                            f"planned_workout:{workout_key}",
                            option_ref,
                            *(
                                [f"plan_snapshot:{source_hash}"]
                                if source_hash
                                else []
                            ),
                        ]
                    )
                ),
                **(
                    {"within_day_order": within_day_order}
                    if within_day_order is not None
                    else {}
                ),
            }
        )

    semantic = {
        "coverage_from": coverage_from.isoformat(),
        "coverage_through": coverage_through.isoformat(),
        "commitments": commitments,
        "source_hashes": sorted(source_hashes),
    }
    digest = hashlib.sha256(
        json.dumps(
            semantic,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "prewindow_load_context_revision": {
                "revision_id": f"prewindow:{digest}",
                "coverage_from": coverage_from.isoformat(),
                "coverage_through": coverage_through.isoformat(),
                "source_refs": [
                    "canonical_current_planned_workouts:supabase",
                    *(
                        f"plan_snapshot:{value}"
                        for value in sorted(source_hashes)
                    ),
                ],
                "commitments": commitments,
            },
        },
    }
