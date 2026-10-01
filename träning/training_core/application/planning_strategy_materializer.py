"""Materialize a bounded Planning Engine v1 StrategyRevision from the canonical mesocycle blueprint.

The materializer never reads calendar placements, forward_horizon day slots or
legacy planner output. It consumes only the canonical mesocycle contract,
the matching development_blueprint microcycle and the canonical workout catalog.

Mandatory obligations come from planned_variants + protected_variants.
supporting_candidates remain optional and are deliberately excluded.

The aggregate envelope is structural rather than physiological: every mutable
catalog option carries an exact planned-session count of one, and the blueprint
declares how many mandatory mutable sessions exist in the microcycle.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from typing import Any


class StrategyMaterializationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StrategyMaterializationError(
            "INVALID_CANONICAL_STRATEGY_SOURCE",
            f"{field} must be object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise StrategyMaterializationError(
            "INVALID_CANONICAL_STRATEGY_SOURCE",
            f"{field} must be array",
        )
    return value


def _strings(value: Any, field: str) -> tuple[str, ...]:
    rows = _list(value, field)
    result = tuple(str(item or "").strip() for item in rows)
    if any(not item for item in result) or len(set(result)) != len(result):
        raise StrategyMaterializationError(
            "INVALID_CANONICAL_STRATEGY_SOURCE",
            f"{field} must contain unique non-empty strings",
        )
    return result


def _iso_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise StrategyMaterializationError(
            "INVALID_CANONICAL_STRATEGY_SOURCE",
            f"{field} must be ISO date",
        ) from exc


def _find_blueprint(
    mesocycle: dict[str, Any],
    *,
    affected_from: date,
    affected_until: date,
) -> dict[str, Any]:
    matches = []
    for index, raw in enumerate(
        _list(
            mesocycle.get("development_blueprint"),
            "current_mesocycle.development_blueprint",
        )
    ):
        row = _mapping(
            raw,
            f"current_mesocycle.development_blueprint[{index}]",
        )
        start = _iso_date(
            row.get("week_start"),
            f"development_blueprint[{index}].week_start",
        )
        end = _iso_date(
            row.get("week_end"),
            f"development_blueprint[{index}].week_end",
        )
        if start == affected_from and end == affected_until:
            matches.append(row)

    if len(matches) != 1:
        raise StrategyMaterializationError(
            "V1_BLUEPRINT_WINDOW_NOT_UNIQUE",
            (
                f"expected exactly one blueprint for "
                f"{affected_from.isoformat()}..{affected_until.isoformat()}, "
                f"found {len(matches)}"
            ),
        )
    return matches[0]


def _recipe_capabilities(
    canonical_catalog: dict[str, Any],
) -> dict[str, tuple[str, ...]]:
    recipes = _mapping(
        canonical_catalog.get("recipes"),
        "canonical_catalog.recipes",
    )
    result: dict[str, tuple[str, ...]] = {}
    for recipe_id, raw in recipes.items():
        row = _mapping(raw, f"recipes.{recipe_id}")
        result[str(recipe_id)] = _strings(
            row.get("stimuli"),
            f"recipes.{recipe_id}.stimuli",
        )
    return result


def materialize_strategy_document(
    *,
    canonical_strategy: dict[str, Any],
    canonical_catalog: dict[str, Any],
    affected_from: date,
    affected_until: date,
) -> dict[str, Any]:
    if affected_until < affected_from:
        raise StrategyMaterializationError(
            "INVALID_CANONICAL_STRATEGY_SOURCE",
            "affected_until cannot precede affected_from",
        )

    root = _mapping(canonical_strategy, "canonical_strategy")
    goal_contract = _mapping(root.get("goal_contract"), "goal_contract")
    goal_hash = str(goal_contract.get("goal_hash") or "").strip()
    if not goal_hash:
        raise StrategyMaterializationError(
            "CANONICAL_GOAL_HASH_MISSING",
            "goal_contract.goal_hash must be non-empty",
        )

    mesocycle = _mapping(root.get("current_mesocycle"), "current_mesocycle")
    mesocycle_id = str(mesocycle.get("id") or "").strip()
    if not mesocycle_id:
        raise StrategyMaterializationError(
            "INVALID_CANONICAL_STRATEGY_SOURCE",
            "current_mesocycle.id must be non-empty",
        )
    meso_start = _iso_date(
        mesocycle.get("start_date"),
        "current_mesocycle.start_date",
    )
    meso_end = _iso_date(
        mesocycle.get("end_date"),
        "current_mesocycle.end_date",
    )
    if affected_from < meso_start or affected_until > meso_end:
        raise StrategyMaterializationError(
            "V1_WINDOW_OUTSIDE_ACTIVE_MESOCYCLE",
            (
                f"{affected_from.isoformat()}..{affected_until.isoformat()} "
                f"outside {meso_start.isoformat()}..{meso_end.isoformat()}"
            ),
        )

    contract = _mapping(mesocycle.get("contract"), "current_mesocycle.contract")
    primary = set(_strings(contract.get("primary"), "contract.primary"))
    protected = set(
        _strings(
            contract.get("protected_capacity"),
            "contract.protected_capacity",
        )
    )
    if primary & protected:
        raise StrategyMaterializationError(
            "V1_STRATEGY_ROLE_OVERLAP",
            "a capability cannot be both primary and protected",
        )

    blueprint = _find_blueprint(
        mesocycle,
        affected_from=affected_from,
        affected_until=affected_until,
    )
    recipe_caps = _recipe_capabilities(canonical_catalog)

    mandatory_rows: list[tuple[str, dict[str, Any], str]] = []
    for collection, role_group in (
        ("planned_variants", "primary"),
        ("protected_variants", "protected"),
    ):
        for index, raw in enumerate(
            _list(blueprint.get(collection, []), f"blueprint.{collection}")
        ):
            row = _mapping(raw, f"blueprint.{collection}[{index}]")
            mandatory_rows.append((collection, row, role_group))

    if not mandatory_rows:
        raise StrategyMaterializationError(
            "V1_BLUEPRINT_HAS_NO_MANDATORY_VARIANTS",
            "blueprint must declare planned/protected variants",
        )

    occurrence_count: dict[str, int] = defaultdict(int)
    recipe_family: dict[str, set[str]] = defaultdict(set)
    capability_role: dict[str, str] = {}

    for collection, row, role_group in mandatory_rows:
        recipe_id = str(row.get("recipe_key") or "").strip()
        declared_capability = str(row.get("capability") or "").strip()
        if not recipe_id or recipe_id not in recipe_caps:
            raise StrategyMaterializationError(
                "V1_BLUEPRINT_RECIPE_NOT_IN_CATALOG",
                f"{collection}: unknown recipe {recipe_id!r}",
            )

        allowed = primary if role_group == "primary" else protected
        provided = tuple(
            capability
            for capability in recipe_caps[recipe_id]
            if capability in allowed
        )
        if declared_capability not in provided:
            raise StrategyMaterializationError(
                "V1_BLUEPRINT_CAPABILITY_RECIPE_MISMATCH",
                (
                    f"{collection}: {recipe_id} does not provide declared "
                    f"{role_group} capability {declared_capability!r}"
                ),
            )
        if not provided:
            raise StrategyMaterializationError(
                "V1_BLUEPRINT_VARIANT_HAS_NO_STRATEGIC_CAPABILITY",
                f"{collection}: {recipe_id}",
            )

        for capability in provided:
            previous_role = capability_role.get(capability)
            if previous_role is not None and previous_role != role_group:
                raise StrategyMaterializationError(
                    "V1_STRATEGY_ROLE_OVERLAP",
                    capability,
                )
            capability_role[capability] = role_group
            occurrence_count[capability] += 1
            recipe_family[capability].add(recipe_id)

    obligations = []
    for capability in sorted(
        occurrence_count,
        key=lambda item: (
            1 if capability_role[item] == "primary" else 2,
            item,
        ),
    ):
        count = occurrence_count[capability]
        role_group = capability_role[capability]
        obligations.append(
            {
                "obligation_id": (
                    f"{affected_from.isoformat()}:{capability}"
                ),
                "capability": capability,
                "role": role_group,
                "priority_tier": 1 if role_group == "primary" else 2,
                "min_exposures": count,
                "max_exposures": count,
                "recipe_family": sorted(recipe_family[capability]),
                "valid_from": affected_from.isoformat(),
                "valid_until": affected_until.isoformat(),
                "source_refs": [
                    f"mesocycle:{mesocycle_id}",
                    (
                        f"development_blueprint:"
                        f"{affected_from.isoformat()}..{affected_until.isoformat()}"
                    ),
                    f"mesocycle_contract:{role_group}:{capability}",
                ],
                "progression_axes": [],
                "partial_coverage": [],
                "prefer_character_variation": False,
                "accepted_observed_bases": ["confirmed_stimulus"],
            }
        )

    mandatory_session_count = len(mandatory_rows)
    semantic = {
        "goal_set_hash": goal_hash,
        "mesocycle_id": mesocycle_id,
        "affected_from": affected_from.isoformat(),
        "affected_until": affected_until.isoformat(),
        "obligations": obligations,
        "mandatory_session_count": mandatory_session_count,
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
        "goal_contract": goal_contract,
        "planning_engine_v1": {
            "schema_version": 1,
            "strategy_revision": {
                "revision_id": f"strategy:{digest}",
                "goal_set_hash": goal_hash,
                "valid_from": affected_from.isoformat(),
                "valid_until": affected_until.isoformat(),
                "accepted_by": "canonical_mesocycle_blueprint",
                "source_refs": [
                    f"mesocycle:{mesocycle_id}",
                    (
                        f"development_blueprint:"
                        f"{affected_from.isoformat()}..{affected_until.isoformat()}"
                    ),
                    "planning_v1:strategy_materializer:v1",
                ],
                "obligations": obligations,
                "load_envelope": {
                    "envelope_id": f"mutable-session-cap:{digest[:16]}",
                    "unknown_policy": "block_increase",
                    "established_baseline_ref": (
                        f"development_blueprint:{affected_from.isoformat()}:"
                        f"mandatory_session_count:{mandatory_session_count}"
                    ),
                    "source_refs": [
                        (
                            f"development_blueprint:"
                            f"{affected_from.isoformat()}..{affected_until.isoformat()}"
                        ),
                        "planning_v1:one_catalog_option_is_one_session",
                    ],
                    "bounds": [
                        {
                            "bound_id": (
                                f"mandatory-mutable-sessions:"
                                f"{affected_from.isoformat()}"
                            ),
                            "scope": "planned",
                            "subject": "mutable_training",
                            "metric": "session_count",
                            "unit": "sessions",
                            "window_days": (
                                affected_until - affected_from
                            ).days + 1,
                            "max_value": mandatory_session_count,
                            "provenance_refs": [
                                (
                                    f"development_blueprint:"
                                    f"{affected_from.isoformat()}.."
                                    f"{affected_until.isoformat()}"
                                )
                            ],
                            "requires_complete_coverage": False,
                        }
                    ],
                },
            },
        },
    }
