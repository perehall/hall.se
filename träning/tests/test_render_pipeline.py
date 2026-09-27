#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_training_site  # noqa: E402
REPO_ROOT = Path(__file__).resolve().parents[2]


class RenderPipelineTests(unittest.TestCase):
    def test_current_publisher_has_no_legacy_mutation_pipeline(self):
        source = (SCRIPTS / "render_training_site.py").read_text(encoding="utf-8")
        self.assertNotIn("PIPELINE =", source)
        self.assertNotIn("run_pipeline(", source)
        self.assertNotIn("finalize_", source)
        self.assertNotIn("build.py", source)
        self.assertIn("render_document", source)
        self.assertIn("build_snapshot", source)

    def test_pages_deploy_defers_stale_goal_state_without_failure(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Check generated planning freshness", workflow)
        self.assertIn("planning_goal_hash", workflow)
        self.assertIn("Deployment deferred", workflow)
        self.assertIn(
            "if: steps.planning_freshness.outputs.stale != 'true'",
            workflow,
        )
        self.assertIn(
            "if: steps.planning_freshness.outputs.stale == 'true'",
            workflow,
        )

    def test_pages_deploy_builds_and_validates_before_upload(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(
            encoding="utf-8"
        )
        render = 'python "träning/scripts/render_training_site.py"'
        upload = "uses: actions/upload-pages-artifact@v4"
        deploy = "uses: actions/deploy-pages@v4"
        self.assertIn(render, workflow)
        self.assertIn(upload, workflow)
        self.assertIn(deploy, workflow)
        self.assertLess(workflow.index(render), workflow.index(upload))
        self.assertLess(workflow.index(upload), workflow.index(deploy))
        self.assertIn("SUPABASE_PUBLISHABLE_KEY: ${{ vars.SUPABASE_PUBLISHABLE_KEY }}", workflow)


if __name__ == "__main__":
    unittest.main()