"""Materialize Planning Engine v1 catalog semantics from the owned workout catalog.

The legacy *planner* is never consulted. The workout catalog is itself the
canonical recipe source, but V1 requires explicit dose-evidence semantics.
Those semantics must be declared per recipe under planning_v1. Load dimension
names are preserved exactly and their categorical level is deliberately
UNKNOWN unless a future explicit catalog contract states otherwise.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from training_core.application.planning_catalog_projection import (
    CatalogProjectionError,
)


class CatalogMaterializationError(CatalogProjectionError):
    pass


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogMaterializationError(
            "INVALID_CANONICAL_CATALOG_SOURCE",
            f"{field} must be object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise CatalogMaterializationError(
            "INVALID_CANONICAL_CATALOG_SOURCE",
            f"{field} must be array",
        )
    return value


def _unique_strings(value: Any, field: str) -> list[str]:
    rows = _list(value, field)
    result = [str(item or "").strip() for item in rows]
    if not result or any(not item for item in result):
        raise CatalogMaterializationError(
            "INVALID_CANONICAL_CATALOG_SOURCE",
            f"{field} must contain non-empty strings",
        )
    if len(set(result)) != len(result):
        raise CatalogMaterializationError(
            "INVALID_CANONICAL_CATALOG_SOURCE",
            f"{field} must not contain duplicates",
        )
    return result


def materialize_catalog_document(
    canonical_catalog: dict[str, Any],
) -> dict[str, Any]:
    root = _mapping(canonical_catalog, "canonical_catalog")
    recipes = _mapping(root.get("recipes"), "canonical_catalog.recipes")
    if not recipes:
        raise CatalogMaterializationError(
            "INVALID_CANONICAL_CATALOG_SOURCE",
            "canonical catalog requires recipes",
        )

    options: list[dict[str, Any]] = []
    for recipe_id in sorted(recipes):
        recipe = _mapping(recipes[recipe_id], f"recipes.{recipe_id}")
        sport = str(recipe.get("sport") or "").strip()
        if not sport:
            raise CatalogMaterializationError(
                "INVALID_CANONICAL_CATALOG_SOURCE",
                f"recipes.{recipe_id}.sport must be non-empty",
            )
        capabilities = _unique_strings(
            recipe.get("stimuli"),
            f"recipes.{recipe_id}.stimuli",
        )
        dimensions = _unique_strings(
            recipe.get("load_dimensions"),
            f"recipes.{recipe_id}.load_dimensions",
        )
        v1 = recipe.get("planning_v1")
        if not isinstance(v1, dict):
            raise CatalogMaterializationError(
                "CATALOG_V1_METADATA_MISSING",
                f"recipes.{recipe_id} lacks planning_v1 metadata",
            )
        basis_source = _mapping(
            v1.get("eligibility_basis"),
            f"recipes.{recipe_id}.planning_v1.eligibility_basis",
        )
        if set(basis_source) != set(capabilities):
            raise CatalogMaterializationError(
                "CATALOG_V1_ELIGIBILITY_INCOMPLETE",
                (
                    f"recipes.{recipe_id} eligibility keys must exactly match "
                    "required stimuli"
                ),
            )

        recipe_options = _list(
            recipe.get("options"),
            f"recipes.{recipe_id}.options",
        )
        if not recipe_options:
            raise CatalogMaterializationError(
                "INVALID_CANONICAL_CATALOG_SOURCE",
                f"recipes.{recipe_id}.options must not be empty",
            )

        for option_index, raw_option in enumerate(recipe_options):
            option = _mapping(
                raw_option,
                f"recipes.{recipe_id}.options[{option_index}]",
            )
            dose_option_id = str(option.get("id") or "").strip()
            if not dose_option_id:
                raise CatalogMaterializationError(
                    "INVALID_CANONICAL_CATALOG_SOURCE",
                    f"recipes.{recipe_id}.options[{option_index}].id is required",
                )

            eligibility_basis = []
            for capability in capabilities:
                basis = _mapping(
                    basis_source[capability],
                    (
                        f"recipes.{recipe_id}.planning_v1."
                        f"eligibility_basis.{capability}"
                    ),
                )
                mode = str(basis.get("mode") or "").strip()
                source_ref = (
                    f"workout_catalog:recipe:{recipe_id}:"
                    f"eligibility_basis:{capability}"
                )
                if mode == "numeric":
                    metric = str(basis.get("metric") or "").strip()
                    value = option.get("value")
                    if not metric:
                        raise CatalogMaterializationError(
                            "CATALOG_V1_ELIGIBILITY_INVALID",
                            f"{source_ref} numeric basis requires metric",
                        )
                    if isinstance(value, bool) or not isinstance(
                        value,
                        (int, float),
                    ):
                        raise CatalogMaterializationError(
                            "CATALOG_V1_ELIGIBILITY_INVALID",
                            (
                                f"{recipe_id}/{dose_option_id} requires numeric "
                                "option.value for numeric eligibility"
                            ),
                        )
                    eligibility_basis.append(
                        {
                            "capability": capability,
                            "mode": "numeric",
                            "metric": metric,
                            "value": value,
                            "source_refs": [source_ref],
                        }
                    )
                elif mode == "qualitative":
                    if basis.get("metric") is not None:
                        raise CatalogMaterializationError(
                            "CATALOG_V1_ELIGIBILITY_INVALID",
                            f"{source_ref} qualitative basis cannot declare metric",
                        )
                    eligibility_basis.append(
                        {
                            "capability": capability,
                            "mode": "qualitative",
                            "source_refs": [source_ref],
                        }
                    )
                else:
                    raise CatalogMaterializationError(
                        "CATALOG_V1_ELIGIBILITY_INVALID",
                        f"{source_ref} mode must be numeric or qualitative",
                    )

            option_ref = f"workout_catalog:option:{dose_option_id}"
            quantitative_load = [
                {
                    "scope": "planned",
                    "subject": "mutable_training",
                    "metric": "session_count",
                    "unit": "sessions",
                    "min_value": 1,
                    "max_value": 1,
                    "provenance_refs": [
                        option_ref,
                        "planning_v1:one_catalog_option_is_one_session",
                    ],
                }
            ]
            option_kind = str(option.get("kind") or "").strip()
            option_value = option.get("value")
            if option_kind == "duration_minutes":
                if (
                    isinstance(option_value, bool)
                    or not isinstance(option_value, (int, float))
                    or float(option_value) <= 0
                ):
                    raise CatalogMaterializationError(
                        "CATALOG_V1_DURATION_INVALID",
                        (
                            f"{recipe_id}/{dose_option_id} duration_minutes "
                            "requires positive numeric option.value"
                        ),
                    )
                quantitative_load.append(
                    {
                        "scope": "global",
                        "subject": "training_duration",
                        "metric": "duration",
                        "unit": "minutes",
                        "min_value": option_value,
                        "max_value": option_value,
                        "provenance_refs": [
                            option_ref,
                            "workout_catalog:option_kind:duration_minutes",
                        ],
                    }
                )

            options.append(
                {
                    "recipe_id": recipe_id,
                    "dose_option_id": dose_option_id,
                    "capabilities": capabilities,
                    "components": [
                        {
                            "discipline": sport,
                            "order": 1,
                        }
                    ],
                    "load_dimensions": [
                        {
                            "dimension": dimension,
                            "level": "unknown",
                            "provenance_refs": [
                                f"workout_catalog:recipe:{recipe_id}:load_dimension:{dimension}",
                                "planning_v1:categorical_level:unknown",
                            ],
                        }
                        for dimension in dimensions
                    ],
                    "quantitative_load": quantitative_load,
                    "source_refs": [
                        f"workout_catalog:recipe:{recipe_id}",
                        option_ref,
                    ],
                    "development_character": str(
                        recipe.get("development_character") or recipe_id
                    ),
                    "planning_priority": int(
                        v1.get("planning_priority", 100)
                    ),
                    "eligibility_basis": eligibility_basis,
                }
            )

    semantic = {
        "schema_version": root.get("schema_version"),
        "options": options,
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
            "catalog_revision": {
                "revision_id": f"catalog:{digest}",
                "source_refs": [
                    f"workout_catalog:schema:{root.get('schema_version')}",
                    "planning_v1:catalog_materializer:v1",
                ],
                "options": options,
            },
        },
    }
