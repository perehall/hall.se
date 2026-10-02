#!/usr/bin/env python3
"""Ordering-law tests for Planning Engine v1 lexicographic objectives."""

from __future__ import annotations

import sys
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning.objectives import ObjectiveVector  # noqa: E402


def vector(
    *,
    required=(Fraction(0, 1),),
    unserved=(0,),
    max_deficit=(Fraction(0, 1),),
    target=(Fraction(0, 1),),
    discretionary=(Fraction(0, 1),),
    spacing=0,
    stability=0,
    schedule_distance=0,
    tie=(),
):
    return ObjectiveVector(
        required_deficit_by_tier=tuple(required),
        unserved_required_by_tier=tuple(unserved),
        max_required_deficit_by_tier=tuple(max_deficit),
        target_deficit_by_tier=tuple(target),
        spacing_shortfall_days=spacing,
        spacing_violation_pairs=0,
        stability_identity_churn=stability,
        stability_date_moves=0,
        stability_prescription_changes=0,
        stability_order_changes=0,
        schedule_range_violation=0,
        schedule_preferred_distance=schedule_distance,
        schedule_double_penalty=0,
        variation_repeat_penalty=0,
        discretionary_excess_by_tier=tuple(discretionary),
        canonical_tie_key=tuple(tie),
    )


class ObjectiveOrderingLawTests(unittest.TestCase):
    def test_required_obligation_always_outranks_every_lower_objective(self):
        fulfilled = vector(
            required=(Fraction(0, 1),),
            discretionary=(Fraction(5, 1),),
            spacing=99,
            stability=99,
            schedule_distance=99,
        )
        missing = vector(required=(Fraction(1, 1),))
        self.assertLess(fulfilled.sort_key, missing.sort_key)

    def test_soft_strategy_target_is_preferred_when_spacing_is_equal(self):
        served = vector(target=(Fraction(0, 1),), stability=5)
        omitted = vector(target=(Fraction(1, 1),), stability=0)
        self.assertLess(served.sort_key, omitted.sort_key)

    def test_spacing_can_override_optional_strategy_target(self):
        well_spaced_without_support = vector(
            target=(Fraction(1, 1),),
            spacing=0,
        )
        clustered_with_support = vector(
            target=(Fraction(0, 1),),
            spacing=1,
        )
        self.assertLess(
            well_spaced_without_support.sort_key,
            clustered_with_support.sort_key,
        )

    def test_anti_filler_outranks_calendar_preference(self):
        lean = vector(
            discretionary=(Fraction(0, 1),),
            schedule_distance=6,
        )
        filler = vector(
            discretionary=(Fraction(1, 1),),
            schedule_distance=0,
        )
        self.assertLess(lean.sort_key, filler.sort_key)

    def test_anti_filler_outranks_plan_stability(self):
        lean = vector(
            discretionary=(Fraction(0, 1),),
            stability=10,
        )
        preserved_extra = vector(
            discretionary=(Fraction(1, 1),),
            stability=0,
        )
        self.assertLess(lean.sort_key, preserved_extra.sort_key)

    def test_spacing_outranks_stability_after_equal_training_content(self):
        well_spaced = vector(spacing=0, stability=5)
        sticky_but_clustered = vector(spacing=1, stability=0)
        self.assertLess(well_spaced.sort_key, sticky_but_clustered.sort_key)


if __name__ == "__main__":
    unittest.main()
