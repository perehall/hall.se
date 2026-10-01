"""Materialize Planning Engine v1 observed training from canonical sources.

The relational activity roster owns completeness of physical training history.
Athlete state may add explicit capability evidence, but never determines
whether an activity exists. Legacy plan matches and planning credits are not
used as physiological evidence.

Categorical load level remains UNKNOWN because current canonical activities do
not carry a validated per-dimension load level. UNKNOWN is intentionally
conservative in V1 hard compatibility validation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any


class ObservedTrainingMaterializationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ObservedTrainingMaterializationError(
            "INVALID_OBSERVED_TRAINING_SOURCE",
            f"{field} must be object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ObservedTrainingMaterializationError(
            "INVALID_OBSERVED_TRAINING_SOURCE",
            f"{field} must be array",
        )
    return value


def _iso_day(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise ObservedTrainingMaterializationError(
            "INVALID_OBSERVED_TRAINING_SOURCE",
            f"{field} must be ISO date",
        ) from exc


def _catalog_dimensions(
    canonical_catalog: dict[str, Any],
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    root = _mapping(canonical_catalog, "canonical_catalog")
    recipes = _mapping(root.get("recipes"), "canonical_catalog.recipes")
    by_sport: dict[str, set[str]] = {}
    universe: set[str] = set()

    for recipe_id, raw_recipe in recipes.items():
        recipe = _mapping(raw_recipe, f"recipes.{recipe_id}")
        sport = str(recipe.get("sport") or "").strip()
        if not sport:
            raise ObservedTrainingMaterializationError(
                "INVALID_OBSERVED_TRAINING_SOURCE",
                f"recipes.{recipe_id}.sport must be non-empty",
            )
        dimensions = [
            str(item or "").strip()
            for item in _list(
                recipe.get("load_dimensions"),
                f"recipes.{recipe_id}.load_dimensions",
            )
        ]
        if not dimensions or any(not item for item in dimensions):
            raise ObservedTrainingMaterializationError(
                "INVALID_OBSERVED_TRAINING_SOURCE",
                f"recipes.{recipe_id}.load_dimensions must be non-empty",
            )
        universe.update(dimensions)
        by_sport.setdefault(sport, set()).update(dimensions)

    if not universe:
        raise ObservedTrainingMaterializationError(
            "INVALID_OBSERVED_TRAINING_SOURCE",
            "canonical catalog has no load dimension universe",
        )
    return (
        {
            sport: tuple(sorted(dimensions))
            for sport, dimensions in by_sport.items()
        },
        tuple(sorted(universe)),
    )


def _activity_roster(
    canonical_activities: list[dict[str, Any]],
    *,
    coverage_from: date,
    coverage_through: date,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    for index, raw in enumerate(canonical_activities):
        row = _mapping(raw, f"canonical_activities[{index}]")
        source_id = str(row.get("id") or "").strip()
        if not source_id:
            raise ObservedTrainingMaterializationError(
                "INVALID_OBSERVED_TRAINING_SOURCE",
                f"canonical_activities[{index}].id must be non-empty",
            )
        if source_id in by_id:
            raise ObservedTrainingMaterializationError(
                "DUPLICATE_OBSERVED_ACTIVITY",
                source_id,
            )
        local_day = _iso_day(
            row.get("date"),
            f"canonical_activities[{index}].date",
        )
        if not coverage_from <= local_day <= coverage_through:
            raise ObservedTrainingMaterializationError(
                "OBSERVED_ACTIVITY_OUTSIDE_COVERAGE",
                source_id,
            )
        if str(row.get("classification") or "") != "training":
            raise ObservedTrainingMaterializationError(
                "NON_TRAINING_ACTIVITY_IN_OBSERVED_SOURCE",
                source_id,
            )
        elapsed = row.get("elapsed_time_s")
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or float(elapsed) < 0
        ):
            raise ObservedTrainingMaterializationError(
                "OBSERVED_ACTIVITY_DURATION_MISSING",
                source_id,
            )
        normalized = {
            "id": source_id,
            "date": local_day.isoformat(),
            "classification": "training",
            "sport_family": str(row.get("sport_family") or "").strip(),
            "elapsed_time_s": float(elapsed),
            "distance_m": row.get("distance_m"),
        }
        rows.append(normalized)
        by_id[source_id] = normalized

    rows.sort(key=lambda item: (item["date"], item["id"]))
    return rows, by_id


def _confirmed_capability_evidence(
    canonical_athlete_state: dict[str, Any],
    roster: dict[str, dict[str, Any]],
    *,
    coverage_from: date,
    coverage_through: date,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for index, raw_session in enumerate(
        canonical_athlete_state.get("recent_sessions") or []
    ):
        if not isinstance(raw_session, dict):
            continue
        source_id = str(raw_session.get("id") or "").strip()
        if not source_id or source_id not in roster:
            continue
        local_day = _iso_day(
            raw_session.get("date"),
            f"recent_sessions[{index}].date",
        )
        if not coverage_from <= local_day <= coverage_through:
            continue

        profile = raw_session.get("training_profile")
        if not isinstance(profile, dict):
            continue
        for stimulus_index, raw_stimulus in enumerate(profile.get("stimuli") or []):
            if not isinstance(raw_stimulus, dict):
                continue
            if raw_stimulus.get("status") != "confirmed":
                continue
            if raw_stimulus.get("confidence") != "high":
                continue
            capability = str(raw_stimulus.get("key") or "").strip()
            if not capability:
                continue
            semantic = (source_id, capability)
            if semantic in seen:
                continue
            seen.add(semantic)
            source = str(raw_stimulus.get("source") or "").strip()
            source_refs = [
                f"activity:{source_id}",
                f"athlete_state:confirmed_stimulus:{source_id}:{capability}",
            ]
            if source:
                source_refs.append(f"stimulus_source:{source}")
            evidence.append(
                {
                    "evidence_id": f"activity:{source_id}:capability:{capability}",
                    "exposure_ref": f"activity:{source_id}",
                    "local_date": local_day.isoformat(),
                    "capability": capability,
                    "basis": "confirmed_stimulus",
                    "source_refs": source_refs,
                }
            )

    return sorted(
        evidence,
        key=lambda item: (
            item["local_date"],
            item["exposure_ref"],
            item["capability"],
        ),
    )


def materialize_observed_training_document(
    *,
    canonical_activities: list[dict[str, Any]],
    canonical_athlete_state: dict[str, Any],
    canonical_catalog: dict[str, Any],
    coverage_from: date,
    coverage_through: date,
) -> dict[str, Any]:
    if coverage_through < coverage_from:
        raise ObservedTrainingMaterializationError(
            "INVALID_OBSERVED_TRAINING_SOURCE",
            "coverage_through cannot precede coverage_from",
        )

    state = _mapping(canonical_athlete_state, "canonical_athlete_state")
    by_sport, dimension_universe = _catalog_dimensions(canonical_catalog)
    recent_sessions, roster = _activity_roster(
        canonical_activities,
        coverage_from=coverage_from,
        coverage_through=coverage_through,
    )

    load_exposures = []
    for row in recent_sessions:
        source_id = row["id"]
        family = row["sport_family"]
        dimensions = by_sport.get(family, dimension_universe)
        load_exposures.append(
            {
                "exposure_id": f"activity:{source_id}",
                "local_date": row["date"],
                "load_dimensions": [
                    {
                        "dimension": dimension,
                        "level": "unknown",
                        "provenance_refs": [
                            f"activity:{source_id}",
                            (
                                f"workout_catalog:sport:{family}:load_dimension:{dimension}"
                                if family in by_sport
                                else f"workout_catalog:dimension_universe:{dimension}"
                            ),
                            "planning_v1:categorical_level:unknown",
                        ],
                    }
                    for dimension in dimensions
                ],
                "quantitative_load": [
                    {
                        "scope": "session",
                        "subject": "all_training",
                        "metric": "duration_minutes",
                        "unit": "minutes",
                        "min_value": row["elapsed_time_s"] / 60.0,
                        "max_value": row["elapsed_time_s"] / 60.0,
                        "provenance_refs": [
                            f"activity:{source_id}",
                            "canonical_activity:elapsed_time_s",
                        ],
                    }
                ],
                "source_refs": [
                    f"activity:{source_id}",
                    "planning_activity_source:supabase_db",
                ],
            }
        )

    evidence = _confirmed_capability_evidence(
        state,
        roster,
        coverage_from=coverage_from,
        coverage_through=coverage_through,
    )

    semantic = {
        "coverage_from": coverage_from.isoformat(),
        "coverage_through": coverage_through.isoformat(),
        "recent_sessions": recent_sessions,
        "capability_evidence": evidence,
        "load_exposures": load_exposures,
        "capability_states": state.get("capability_states"),
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
        "fact_window": {
            "start": coverage_from.isoformat(),
            "end": coverage_through.isoformat(),
            "lookback_days": (coverage_through - coverage_from).days + 1,
        },
        "recent_sessions": recent_sessions,
        "capability_states": state.get("capability_states"),
        "planning_engine_v1": {
            "schema_version": 1,
            "observed_training_revision": {
                "revision_id": f"observed:{digest}",
                "coverage_from": coverage_from.isoformat(),
                "coverage_through": coverage_through.isoformat(),
                "capability_evidence": evidence,
                "load_exposures": load_exposures,
                "source_refs": [
                    "planning_activity_source:supabase_db",
                    "athlete_state:confirmed_stimuli",
                    "workout_catalog:load_dimension_vocabulary",
                ],
            },
        },
    }
