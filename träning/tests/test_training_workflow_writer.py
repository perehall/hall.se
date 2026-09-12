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

    def test_writer_is_serialized_and_refreshes_from_current_main(self):
        workflow = self.workflow_text()
        update = self.update_job_text()

        self.assertIn("group: training-pages", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("- name: Checkout current main", update)
        self.assertIn("ref: main", update)
        self.assertIn("- name: Pin writable base to latest main", update)
        self.assertIn("git checkout -B main origin/main", update)
        self.assertLess(
            update.index("- name: Pin writable base to latest main"),
            update.index("- name: Run canonical training update pipeline"),
        )

    def test_generated_snapshots_are_never_rebased(self):
        update = self.update_job_text()

        self.assertNotIn("git pull --rebase", update)
        self.assertIn("git ls-remote origin refs/heads/main", update)
        self.assertIn("Refusing to rebase generated training snapshots", update)
        self.assertIn("git push origin HEAD:main", update)


if __name__ == "__main__":
    unittest.main()
