"""Canonical semantic hashing for immutable Planning Engine v1 content."""

from __future__ import annotations

import hashlib
import json

from .models import PlanContent


def _dimension_payload(item):
    return {
        "dimension": item.dimension,
        "level": item.level.value,
    }


def _estimate_payload(item):
    return {
        "scope": item.scope,
        "subject": item.subject,
        "metric": item.metric,
        "unit": item.unit,
        "min_value": float(item.min_value),
        "max_value": float(item.max_value),
    }


def semantic_plan_payload(plan: PlanContent) -> dict:
    """Return order-independent semantic training content.

    Provenance refs and incidental tuple ordering are intentionally excluded.
    Changing date, recipe, dose, components, load semantics or within-day order
    changes the hash. Reordering independent workouts does not.
    """
    workouts = []
    for workout in plan.workouts:
        workouts.append(
            {
                "workout_id": workout.workout_id,
                "local_date": workout.local_date.isoformat(),
                "recipe_id": workout.recipe_id,
                "dose_option_id": workout.dose_option_id,
                "obligation_ids": sorted(workout.obligation_ids),
                "components": [
                    {
                        "discipline": component.discipline,
                        "order": component.order,
                    }
                    for component in sorted(
                        workout.components,
                        key=lambda component: component.order,
                    )
                ],
                "load_dimensions": [
                    _dimension_payload(item)
                    for item in sorted(
                        workout.load_dimensions,
                        key=lambda item: item.dimension,
                    )
                ],
                "quantitative_load": [
                    _estimate_payload(item)
                    for item in sorted(
                        workout.quantitative_load,
                        key=lambda item: (item.scope, item.subject, item.metric, item.unit),
                    )
                ],
                "within_day_order": workout.within_day_order,
            }
        )

    commitments = []
    for item in plan.fixed_commitments:
        commitments.append(
            {
                "commitment_id": item.commitment_id,
                "local_date": item.local_date.isoformat(),
                "load_dimensions": [
                    _dimension_payload(load)
                    for load in sorted(
                        item.load_dimensions,
                        key=lambda load: load.dimension,
                    )
                ],
                "quantitative_load": [
                    _estimate_payload(load)
                    for load in sorted(
                        item.quantitative_load,
                        key=lambda load: (load.scope, load.subject, load.metric, load.unit),
                    )
                ],
                "within_day_order": item.within_day_order,
            }
        )

    return {
        "source_revision": plan.source_revision,
        "strategy_revision_id": plan.strategy_revision_id,
        "affected_from": plan.affected_from.isoformat(),
        "affected_until": plan.affected_until.isoformat(),
        "workouts": sorted(
            workouts,
            key=lambda item: (
                item["local_date"],
                item["within_day_order"] is None,
                item["within_day_order"] or 0,
                item["workout_id"],
            ),
        ),
        "fixed_commitments": sorted(
            commitments,
            key=lambda item: (
                item["local_date"],
                item["within_day_order"] is None,
                item["within_day_order"] or 0,
                item["commitment_id"],
            ),
        ),
    }


def plan_content_hash(plan: PlanContent) -> str:
    payload = semantic_plan_payload(plan)
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
