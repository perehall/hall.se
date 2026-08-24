#!/usr/bin/env python3
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "finalize_yoda_ui.py"


class YodaEmptyWeekTests(unittest.TestCase):
    def test_no_coach_block_is_valid_on_new_active_week(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(SOURCE, scripts / SOURCE.name)
            original = "<!doctype html><html><head><style>body{}</style></head><body><main>Vecka 35</main></body></html>"
            (root / "index.html").write_text(original, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(scripts / SOURCE.name)],
                cwd=root,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0 coachblock", result.stdout)
            self.assertEqual((root / "index.html").read_text(encoding="utf-8"), original)

    def test_malformed_raw_coach_block_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(SOURCE, scripts / SOURCE.name)
            (root / "index.html").write_text(
                '<html><head><style></style></head><body><div class="coach">trasigt</div></body></html>',
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(scripts / SOURCE.name)],
                cwd=root,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("matchar inte UI-kontraktet", result.stderr)


if __name__ == "__main__":
    unittest.main()
