#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "update-training.yml"


class TrainingWorkflowWriterTests(unittest.TestCase):
    def workflow_text(self):
        return WORKFLOW.read_text(encoding="utf-8")

    def update_job_text(self):
        workflow = self.workflow_text()
        return workflow.split("  update:\n", 1)[1]

    def test_writer_is_serialized_queued_and_refreshes_from_current_main(self):
        workflow = self.workflow_text()
        update = self.update_job_text()

        self.assertIn("group: training-pages", workflow)
        self.assertIn("queue: max", workflow)
        self.assertNotIn("cancel-in-progress: true", workflow)
        self.assertIn("- name: Checkout current main", update)
        self.assertIn("ref: main", update)
        self.assertIn("- name: Pin writable base to latest main", update)
        self.assertIn("git checkout -B main origin/main", update)
        self.assertLess(
            update.index("- name: Pin writable base to latest main"),
            update.index("- name: Run canonical training update pipeline"),
        )

    def test_generated_snapshots_are_never_rebased_and_conflicts_retry_cleanly(self):
        update = self.update_job_text()

        self.assertNotIn("git pull --rebase", update)
        self.assertIn("git ls-remote origin refs/heads/main", update)
        self.assertIn("Discarding this generated snapshot and queueing one clean retry", update)
        self.assertIn("gh workflow run update-training.yml --ref main", update)
        self.assertIn("git push origin HEAD:main", update)

    def test_push_trigger_is_restricted_to_main(self):
        workflow = self.workflow_text()
        push_block = workflow.split("  push:\n", 1)[1].split("\nconcurrency:", 1)[0]
        self.assertIn("branches:", push_block)
        self.assertIn("- main", push_block)

    def test_planning_authority_changes_trigger_canonical_replan(self):
        workflow = self.workflow_text()
        for path in (
            'träning/data/goal.json',
            'träning/data/planning_policy.json',
            'träning/data/workout_catalog.json',
            'träning/scripts/adaptive_planner.py',
            'träning/scripts/race_contracts.py',
        ):
            self.assertIn(path, workflow)

    def test_generated_training_commit_dispatches_pages_explicitly(self):
        workflow = self.workflow_text()

        self.assertIn("gh workflow run deploy-pages.yml --ref main", workflow)
        self.assertIn("steps.commit_changes.outputs.changed == 'true'", workflow)
        self.assertNotIn("Push to main triggers deploy-pages.yml automatically", workflow)

    def test_supabase_shadow_sync_is_post_update_non_blocking_and_self_healing(self):
        workflow = self.workflow_text()

        self.assertIn("  shadow_sync:\n", workflow)
        shadow = workflow.split("  shadow_sync:\n", 1)[1]
        self.assertIn("needs: update", shadow)
        self.assertIn("needs.update.result == 'success'", shadow)
        self.assertIn("continue-on-error: true", shadow)
        self.assertIn("- name: Checkout latest canonical main", shadow)
        self.assertIn("ref: main", shadow)
        self.assertIn('python "träning/scripts/supabase_shadow_writer.py" --mode write', shadow)
        self.assertIn('python "träning/scripts/supabase_shadow_reader.py"', shadow)
        self.assertLess(
            shadow.index('python "träning/scripts/supabase_shadow_writer.py" --mode write'),
            shadow.index('python "träning/scripts/supabase_shadow_reader.py"'),
        )
        self.assertIn("for attempt in 1 2 3", shadow)
        self.assertIn("shadow state will retry on the next training run", shadow)
        self.assertGreater(
            workflow.index("  shadow_sync:\n"),
            workflow.index("  update:\n"),
        )

    def test_supabase_shadow_sync_is_not_part_of_critical_training_runner(self):
        runner = (REPO_ROOT / "träning" / "scripts" / "training_job_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("supabase_shadow_writer", runner)
        self.assertNotIn("supabase_shadow_reader", runner)


if __name__ == "__main__":
    unittest.main()
