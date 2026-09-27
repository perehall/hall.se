#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_transaction  # noqa: E402


class RenderTransactionTests(unittest.TestCase):
    def test_failed_render_restores_exact_pre_render_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            training = repo / "träning"
            scripts = training / "scripts"
            scripts.mkdir(parents=True)
            renderer = scripts / "render_training_site.py"
            renderer.write_text("# fixture", encoding="utf-8")
            index = training / "index.html"
            index.write_text("known-good", encoding="utf-8")
            canonical = training / "data.json"
            canonical.write_text('{"state":"committed"}', encoding="utf-8")

            def failing_runner(command, *, cwd, check):
                index.write_text("half-rendered", encoding="utf-8")
                (training / "partial.html").write_text("partial", encoding="utf-8")
                return SimpleNamespace(returncode=17)

            with patch.object(render_transaction, "TRAINING_ROOT", training), \
                 patch.object(render_transaction, "REPO_ROOT", repo), \
                 patch.object(render_transaction, "RENDERER", renderer), \
                 patch.object(render_transaction, "STATUS_FILE", Path(tmp) / "status"):
                result = render_transaction.render_transaction(runner=failing_runner)

            self.assertEqual(result, 17)
            self.assertEqual(index.read_text(encoding="utf-8"), "known-good")
            self.assertEqual(canonical.read_text(encoding="utf-8"), '{"state":"committed"}')
            self.assertFalse((training / "partial.html").exists())

    def test_successful_render_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            training = repo / "träning"
            scripts = training / "scripts"
            scripts.mkdir(parents=True)
            renderer = scripts / "render_training_site.py"
            renderer.write_text("# fixture", encoding="utf-8")
            index = training / "index.html"
            index.write_text("old", encoding="utf-8")

            def successful_runner(command, *, cwd, check):
                index.write_text("new", encoding="utf-8")
                return SimpleNamespace(returncode=0)

            with patch.object(render_transaction, "TRAINING_ROOT", training), \
                 patch.object(render_transaction, "REPO_ROOT", repo), \
                 patch.object(render_transaction, "RENDERER", renderer):
                result = render_transaction.render_transaction(runner=successful_runner)

            self.assertEqual(result, 0)
            self.assertEqual(index.read_text(encoding="utf-8"), "new")


if __name__ == "__main__":
    unittest.main()
