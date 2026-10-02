import unittest

from training_core.application.planning_shadow_evidence import (
    ShadowEvidenceRequirements,
    evaluate_shadow_evidence,
)


def row(
    event: str,
    microcycle: str,
    semantic_hash: str,
    *,
    status: str = "current",
    plan_hash: str | None = "plan-1",
    objective=None,
):
    return {
        "event_key": event,
        "microcycle_key": microcycle,
        "readiness_status": "ready",
        "solver_status": status,
        "semantic_input_hash": semantic_hash,
        "engine_version": "planning-v1",
        "plan_content_hash": plan_hash,
        "objective_vector": objective or {"score": 1},
    }


class ShadowEvidenceTests(unittest.TestCase):
    def test_requires_four_microcycles_and_twenty_distinct_events(self):
        rows = [
            row(f"event-{index}", f"2026-W{40 + index % 4}", f"input-{index}")
            for index in range(20)
        ]
        report = evaluate_shadow_evidence(rows)
        self.assertTrue(report["ready_for_cutover_review"])
        self.assertEqual(report["evidence"]["distinct_events"], 20)
        self.assertEqual(report["evidence"]["distinct_microcycles"], 4)

    def test_blocked_solver_outcome_is_still_fail_closed_evidence(self):
        rows = [
            row(
                f"event-{index}",
                f"2026-W{40 + index % 4}",
                f"input-{index}",
                status="blocked",
                plan_hash=None,
            )
            for index in range(20)
        ]
        report = evaluate_shadow_evidence(rows)
        self.assertTrue(report["ready_for_cutover_review"])
        self.assertEqual(report["evidence"]["blocked_outcomes"], 20)

    def test_readiness_blocked_rows_do_not_count(self):
        rows = [
            {
                **row(f"event-{index}", f"2026-W{40 + index % 4}", f"input-{index}"),
                "readiness_status": "blocked",
                "solver_status": None,
                "semantic_input_hash": None,
            }
            for index in range(20)
        ]
        report = evaluate_shadow_evidence(rows)
        self.assertFalse(report["ready_for_cutover_review"])
        self.assertEqual(report["evidence"]["distinct_events"], 0)

    def test_same_semantic_input_must_be_deterministic(self):
        rows = [
            row("event-1", "2026-W40", "same", plan_hash="plan-a"),
            row("event-2", "2026-W40", "same", plan_hash="plan-b"),
        ]
        report = evaluate_shadow_evidence(
            rows,
            ShadowEvidenceRequirements(min_microcycles=1, min_events=2),
        )
        self.assertFalse(report["ready_for_cutover_review"])
        self.assertEqual(
            report["blockers"][-1]["code"],
            "NONDETERMINISTIC_SHADOW_OUTCOME",
        )


if __name__ == "__main__":
    unittest.main()
