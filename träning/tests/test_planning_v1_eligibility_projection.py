#!/usr/bin/env python3
"""Evidence-to-dose eligibility tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_catalog_projection import (  # noqa: E402
    DoseEvidenceMode,
    OptionDoseEvidence,
    PlanningCatalogProjection,
)
from training_core.application.planning_eligibility_projection import (  # noqa: E402
    project_option_eligibility,
)
from training_core.planning.models import (  # noqa: E402
    ApprovedWorkoutOption,
    EligibilityKind,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    WorkoutComponentIntent,
)


def option(dose_id, capability, *, minutes=50):
    return ApprovedWorkoutOption(
        recipe_id=capability,
        dose_option_id=dose_id,
        capabilities=(capability,),
        components=(WorkoutComponentIntent("run", 1),),
        load_dimensions=(
            LoadDimensionExposure(
                dimension="cardiovascular",
                level=LoadDimensionLevel.LOW,
                provenance_refs=("catalog:test",),
            ),
        ),
        quantitative_load=(
            LoadEstimate(
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                min_value=minutes,
                max_value=minutes,
                provenance_refs=("catalog:test",),
            ),
        ),
        source_refs=("catalog:test",),
    )


def numeric_catalog(capability, metric, values):
    options = []
    bases = []
    for value in values:
        dose_id = f"{capability}-{value}"
        options.append(option(dose_id, capability))
        bases.append(
            OptionDoseEvidence(
                recipe_id=capability,
                dose_option_id=dose_id,
                capability=capability,
                mode=DoseEvidenceMode.NUMERIC,
                metric=metric,
                value=value,
                source_refs=("catalog:test",),
            )
        )
    return PlanningCatalogProjection(
        revision_id="catalog-test",
        approved_options=tuple(options),
        eligibility_basis=tuple(bases),
        source_refs=("catalog:test",),
    )


def state(capability, **row):
    return {
        "capability_states": {
            "by_capability": {
                capability: {
                    "metric": row.pop("metric", None),
                    "evidence_state": row.pop("evidence_state", "missing"),
                    "absorbed_value": row.pop("absorbed_value", None),
                    "tolerated_value": row.pop("tolerated_value", None),
                    "demonstrated_value": row.pop("demonstrated_value", None),
                    "progression_ready": row.pop("progression_ready", False),
                    "verified_exposures": row.pop("verified_exposures", []),
                    **row,
                }
            }
        }
    }


def kinds(result):
    return {
        item.dose_option_id: item.kind
        for item in result.option_eligibility
    }


def reasons(result):
    return {
        item.dose_option_id: item.reason_code
        for item in result.decisions
    }


class V1EligibilityProjectionTests(unittest.TestCase):
    def test_absorbed_dose_holds_highest_supported_step_and_reduces_lower(self):
        catalog = numeric_catalog(
            "run_threshold",
            "work_minutes",
            (24, 32, 36),
        )
        result = project_option_eligibility(
            catalog,
            state(
                "run_threshold",
                metric="work_minutes",
                evidence_state="absorbed",
                absorbed_value=32,
                tolerated_value=32,
                demonstrated_value=32,
                progression_ready=False,
            ),
        )
        self.assertTrue(result.ready)
        self.assertEqual(
            kinds(result),
            {
                "run_threshold-24": EligibilityKind.REDUCE,
                "run_threshold-32": EligibilityKind.HOLD,
            },
        )
        self.assertEqual(
            reasons(result)["run_threshold-36"],
            "PROGRESSION_NOT_READY",
        )

    def test_progression_opens_exactly_one_next_catalog_step(self):
        catalog = numeric_catalog(
            "run_threshold",
            "work_minutes",
            (24, 32, 36, 40),
        )
        result = project_option_eligibility(
            catalog,
            state(
                "run_threshold",
                metric="work_minutes",
                evidence_state="absorbed",
                absorbed_value=32,
                tolerated_value=32,
                demonstrated_value=32,
                progression_ready=True,
            ),
        )
        self.assertEqual(
            kinds(result),
            {
                "run_threshold-24": EligibilityKind.REDUCE,
                "run_threshold-32": EligibilityKind.HOLD,
                "run_threshold-36": EligibilityKind.PROGRESS,
            },
        )
        self.assertEqual(
            reasons(result)["run_threshold-40"],
            "ABOVE_NEXT_PROGRESS_STEP",
        )

    def test_demonstrated_only_evidence_caps_establishment_at_supported_step(self):
        catalog = numeric_catalog(
            "run_easy_distance",
            "duration_minutes",
            (60, 75, 90, 105, 120),
        )
        result = project_option_eligibility(
            catalog,
            state(
                "run_easy_distance",
                metric="duration_minutes",
                evidence_state="demonstrated",
                demonstrated_value=80.07,
                progression_ready=False,
            ),
        )
        self.assertEqual(
            kinds(result),
            {
                "run_easy_distance-60": EligibilityKind.REDUCE,
                "run_easy_distance-75": EligibilityKind.ESTABLISH,
            },
        )
        self.assertEqual(
            reasons(result)["run_easy_distance-90"],
            "PROGRESSION_NOT_READY",
        )

    def test_tolerated_and_demonstrated_disagreement_uses_lower_ceiling(self):
        catalog = numeric_catalog(
            "mtb_technical",
            "duration_minutes",
            (60, 75, 90),
        )
        result = project_option_eligibility(
            catalog,
            state(
                "mtb_technical",
                metric="duration_minutes",
                evidence_state="tolerated",
                tolerated_value=75,
                demonstrated_value=90,
            ),
        )
        self.assertEqual(
            kinds(result),
            {
                "mtb_technical-60": EligibilityKind.REDUCE,
                "mtb_technical-75": EligibilityKind.ESTABLISH,
            },
        )
        self.assertNotIn("mtb_technical-90", kinds(result))

    def test_metric_mismatch_blocks_projection_instead_of_comparing_numbers(self):
        catalog = numeric_catalog(
            "run_threshold",
            "work_minutes",
            (32,),
        )
        result = project_option_eligibility(
            catalog,
            state(
                "run_threshold",
                metric="duration_minutes",
                evidence_state="absorbed",
                absorbed_value=32,
            ),
        )
        self.assertFalse(result.ready)
        self.assertEqual(
            result.blockers[0].code,
            "CAPABILITY_METRIC_MISMATCH",
        )
        self.assertEqual(result.option_eligibility, ())

    def test_qualitative_evidence_can_establish_but_never_numeric_progress(self):
        capability = "swim_technique"
        approved = option("technique-base", capability)
        catalog = PlanningCatalogProjection(
            revision_id="catalog-test",
            approved_options=(approved,),
            eligibility_basis=(
                OptionDoseEvidence(
                    recipe_id=capability,
                    dose_option_id="technique-base",
                    capability=capability,
                    mode=DoseEvidenceMode.QUALITATIVE,
                    source_refs=("catalog:test",),
                ),
            ),
            source_refs=("catalog:test",),
        )
        result = project_option_eligibility(
            catalog,
            state(
                capability,
                metric=None,
                evidence_state="observed",
                progression_ready=True,
            ),
        )
        self.assertEqual(
            kinds(result),
            {"technique-base": EligibilityKind.ESTABLISH},
        )
        self.assertIsNone(result.decisions[0].next_progress_value)

    def test_projection_does_not_import_legacy_planner(self):
        import training_core.application.planning_eligibility_projection as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("choose_option", source)
        self.assertNotIn("starting_state_value_for_recipe", source)


if __name__ == "__main__":
    unittest.main()
