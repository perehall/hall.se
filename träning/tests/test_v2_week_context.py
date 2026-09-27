#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.domain.planning import (  # noqa: E402
    MesocycleContext,
    MicrocycleContext,
    WeekPlanningContext,
)
from training_core.presentation.week_context import (  # noqa: E402
    build_week_context_read_model,
)
from training_core.repositories.context import (  # noqa: E402
    PostgresPlanningContextRepository,
)


class Cursor:
    def __init__(self, row):
        self.row = row
        self.query = ""
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Conn:
    def __init__(self, row):
        self.cursor_instance = Cursor(row)

    def cursor(self):
        return self.cursor_instance

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Factory:
    def __init__(self, row):
        self.row = row
        self.last = None

    def __call__(self):
        self.last = Conn(self.row)
        return self.last


class WeekContextTests(unittest.TestCase):
    def test_repository_reads_relational_meso_microcycle_context(self):
        row = (
            "meso:mc1",
            "meso",
            1,
            date(2026, 9, 21),
            "Mikrocykelrational.",
            {"plan_meta": {"microcycle_total": 4}},
            "meso",
            "Fortsatt byggblock — prioritet sim + kontrollerad löptröskel",
            "continue",
            date(2026, 9, 21),
            date(2026, 10, 18),
            4,
            "Utveckla sim och bibehåll löptröskel.",
            "Kapaciteten talar för ett konservativt byggblock.",
            {"primary_capabilities": ["swim_aerobic", "swim_technique", "run_threshold"]},
        )
        factory = Factory(row)
        repository = PostgresPlanningContextRepository(factory)
        context = repository.week_context(date(2026, 9, 21))

        self.assertEqual(context.microcycle.microcycle_index, 1)
        self.assertEqual(context.mesocycle.duration_weeks, 4)
        self.assertIn("training.microcycles", factory.last.cursor_instance.query)
        self.assertIn("training.mesocycles", factory.last.cursor_instance.query)
        self.assertEqual(factory.last.cursor_instance.params, (date(2026, 9, 21),))

    def test_current_context_matches_production_information_hierarchy(self):
        source = WeekPlanningContext(
            mesocycle=MesocycleContext(
                mesocycle_id="meso",
                title="Fortsatt byggblock — prioritet sim + kontrollerad löptröskel",
                decision="continue",
                start_date=date(2026, 9, 21),
                end_date=date(2026, 10, 18),
                duration_weeks=4,
                goal_contribution="Utveckla simmens aeroba kapacitet och teknik.",
                hypothesis="Stabil sim- och löpkontinuitet stödjer ett konservativt byggblock.",
                payload={
                    "primary_capabilities": [
                        "swim_aerobic",
                        "swim_technique",
                        "run_threshold",
                    ],
                    "secondary_capabilities": [
                        "run_easy_distance",
                        "mtb_aerobic",
                        "mtb_technical",
                    ],
                },
            ),
            microcycle=MicrocycleContext(
                microcycle_id="meso:mc1",
                mesocycle_id="meso",
                microcycle_index=1,
                week_start=date(2026, 9, 21),
                rationale="",
                payload={
                    "plan_meta": {
                        "principle": "Fortsätt utveckla sim och löptålighet med kontrollerad belastning.",
                        "mesocycle_contract": {
                            "maintenance": ["swim_threshold"],
                            "protected_capacity": [
                                "strength_unilateral",
                                "strength_core",
                                "plyometric",
                            ],
                        },
                    }
                },
            ),
        )
        model = build_week_context_read_model(source)

        self.assertEqual(
            model.focus,
            "Sim aerob/teknik + kontrollerad löptröskel",
        )
        self.assertEqual(model.meta_line, "Byggblock · mikrocykel 1 av 4")
        self.assertEqual(model.maintenance, ("kontrollerad simtröskel",))
        self.assertEqual(
            model.protected,
            ("unilateral styrka", "core", "plyometri"),
        )
        self.assertTrue(model.principle)
        self.assertTrue(model.hypothesis)


if __name__ == "__main__":
    unittest.main()
