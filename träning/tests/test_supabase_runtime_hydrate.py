#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import supabase_runtime_state as runtime  # noqa: E402


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((" ".join(str(query).split()), params))

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Conn:
    def __init__(self, rows):
        self.cursor_instance = Cursor(rows)
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Driver:
    def __init__(self, rows):
        self.conn = Conn(rows)

    def connect(self, *args, **kwargs):
        return self.conn


class RuntimeHydrationTests(unittest.TestCase):
    def test_hydrate_is_read_only_and_materializes_verified_documents(self):
        payloads = {
            key: {"document": key, "value": 1}
            for key in runtime.SCOPE_KEYS["final"]
        }
        rows = [
            (key, runtime.canonical_hash(payload), payload)
            for key, payload in payloads.items()
        ]
        driver = Driver(rows)

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runtime.psycopg, "connect", driver.connect
        ):
            result = runtime.hydrate_runtime_scope(
                "final",
                data_dir=Path(tmp),
            )
            for key, payload in payloads.items():
                filename = runtime.DOCUMENT_FILES[key]
                actual = json.loads(
                    (Path(tmp) / filename).read_text(encoding="utf-8")
                )
                self.assertEqual(actual, payload)

        self.assertTrue(driver.conn.rolled_back)
        statements = [query.lower() for query, _ in driver.conn.cursor_instance.executed]
        self.assertTrue(any("set transaction read only" in query for query in statements))
        self.assertFalse(
            any(
                token in query
                for query in statements
                for token in ("insert ", "update ", "delete ")
            )
        )
        self.assertTrue(result["verified"])

    def test_hydrate_rejects_payload_hash_mismatch(self):
        key = runtime.SCOPE_KEYS["athlete"][0]
        driver = Driver([(key, "wrong", {"document": key})])
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runtime.psycopg, "connect", driver.connect
        ):
            with self.assertRaisesRegex(RuntimeError, "payload hash mismatch"):
                runtime.hydrate_runtime_scope(
                    "athlete",
                    data_dir=Path(tmp),
                )


if __name__ == "__main__":
    unittest.main()
