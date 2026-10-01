#!/usr/bin/env python3
"""Fixed-commitment source ownership for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_fixed_commitments_source import (  # noqa: E402
    FixedCommitmentSourceError,
    resolve_fixed_commitments_document,
)


def profile_record(fixed_text=""):
    return {
        "status": "found",
        "revision": 12,
        "profile": {
            "schema_version": 1,
            "status": "complete",
            "constraints": {
                "fixed_commitments": fixed_text,
            },
        },
    }


def typed_document():
    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "fixed_commitments_revision": {
                "revision_id": "typed-v1",
                "source_refs": ["user-confirmed:typed"],
                "commitments": [],
            },
        },
    }


class FixedCommitmentSourceTests(unittest.TestCase):
    def test_explicit_typed_document_remains_authoritative(self):
        document = typed_document()
        self.assertIs(
            resolve_fixed_commitments_document(
                canonical_profile_record=profile_record("legacy text"),
                explicit_document=document,
            ),
            document,
        )

    def test_explicitly_empty_profile_field_proves_empty_commitment_set(self):
        document = resolve_fixed_commitments_document(
            canonical_profile_record=profile_record(""),
        )
        revision = document["planning_engine_v1"]["fixed_commitments_revision"]
        self.assertEqual(revision["commitments"], [])
        self.assertEqual(revision["revision_id"], "athlete-profile-empty:12")
        self.assertIn(
            "athlete_profile:constraints:fixed_commitments:explicitly_empty",
            revision["source_refs"],
        )

    def test_nonempty_legacy_text_blocks_instead_of_being_interpreted(self):
        with self.assertRaises(FixedCommitmentSourceError) as raised:
            resolve_fixed_commitments_document(
                canonical_profile_record=profile_record("Enduro måndag"),
            )
        self.assertEqual(
            raised.exception.code,
            "UNTYPED_FIXED_COMMITMENTS_REQUIRE_MIGRATION",
        )

    def test_invalid_profile_revision_blocks_empty_commitment_claim(self):
        profile = profile_record("")
        profile["revision"] = None
        with self.assertRaises(FixedCommitmentSourceError) as raised:
            resolve_fixed_commitments_document(
                canonical_profile_record=profile,
            )
        self.assertEqual(
            raised.exception.code,
            "INVALID_FIXED_COMMITMENT_SOURCE",
        )

    def test_source_has_no_legacy_planner_or_text_parser_dependency(self):
        import training_core.application.planning_fixed_commitments_source as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("plan.json", source)
        self.assertNotIn("weekday", source.lower())
        self.assertNotIn("enduro", source.lower())


if __name__ == "__main__":
    unittest.main()
