import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from finalize_backend_status_ui import PROJECT_URL, patch_page


SHELL = """<html><body>
<dialog id="trainingSystemSheet"><div><ul class="system-list">
<li><strong>Data:</strong> test</li>
</ul></div></dialog>
<footer></footer>
</body></html>"""


class BackendStatusUiTests(unittest.TestCase):
    def test_patch_is_idempotent(self):
        first = patch_page(SHELL, "sb_publishable_test")
        second = patch_page(first, "sb_publishable_test")
        self.assertEqual(first, second)
        self.assertEqual(first.count("backend-status-ui-v1:start"), 2)

    def test_public_key_is_used_but_server_secret_names_are_not(self):
        rendered = patch_page(SHELL, "sb_publishable_test")
        self.assertIn("sb_publishable_test", rendered)
        self.assertIn(PROJECT_URL, rendered)
        self.assertNotIn("SUPABASE_DB_URL", rendered)
        self.assertNotIn("service_role", rendered)
        self.assertNotIn("sb_secret_", rendered)

    def test_missing_public_key_hides_status_row(self):
        rendered = patch_page(SHELL, "")
        self.assertIn("row.hidden = true", rendered)

    def test_status_uses_sanitized_rpc_only(self):
        rendered = patch_page(SHELL, "sb_publishable_test")
        self.assertIn("/rest/v1/rpc/training_backend_status", rendered)
        self.assertNotIn("/rest/v1/activities", rendered)
        self.assertNotIn("training.activities", rendered)


if __name__ == "__main__":
    unittest.main()
