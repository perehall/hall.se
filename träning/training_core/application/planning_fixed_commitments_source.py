"""Resolve typed Planning Engine v1 fixed commitments without text inference.

An explicit typed commitment document is accepted as the authoritative source.
When no such document exists, the canonical athlete profile may prove that the
declared fixed-commitment field is empty. Non-empty legacy free text is never
parsed into dates, sports or load semantics; it blocks V1 readiness until it is
migrated through an explicit typed/user-confirmed path.
"""

from __future__ import annotations

from typing import Any


class FixedCommitmentSourceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FixedCommitmentSourceError(
            "INVALID_FIXED_COMMITMENT_SOURCE",
            f"{field} must be object",
        )
    return value


def resolve_fixed_commitments_document(
    *,
    canonical_profile_record: dict[str, Any],
    explicit_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one typed fixed-commitment document or fail closed.

    This function deliberately has no natural-language parser. An explicit V1
    document is passed through to the strict execution-facts materializer,
    which validates its schema and load semantics. Without one, only an
    explicitly empty profile field can establish an empty commitment set.
    """

    if explicit_document:
        if not isinstance(explicit_document, dict):
            raise FixedCommitmentSourceError(
                "INVALID_FIXED_COMMITMENT_SOURCE",
                "explicit fixed commitments must be an object",
            )
        return explicit_document

    root = _mapping(canonical_profile_record, "canonical_profile_record")
    if root.get("status") != "found":
        raise FixedCommitmentSourceError(
            "MISSING_CANONICAL_ATHLETE_PROFILE",
            "cannot establish fixed commitments without canonical athlete profile",
        )

    profile = _mapping(root.get("profile"), "canonical_profile_record.profile")
    if profile.get("status") != "complete":
        raise FixedCommitmentSourceError(
            "ATHLETE_PROFILE_NOT_COMPLETE",
            "fixed-commitment readiness requires a completed athlete profile",
        )

    revision = root.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise FixedCommitmentSourceError(
            "INVALID_FIXED_COMMITMENT_SOURCE",
            "profile revision must be a positive integer",
        )

    constraints = _mapping(profile.get("constraints"), "profile.constraints")
    declared = constraints.get("fixed_commitments", "")
    if declared is None:
        declared = ""
    if not isinstance(declared, str):
        raise FixedCommitmentSourceError(
            "INVALID_FIXED_COMMITMENT_SOURCE",
            "profile.constraints.fixed_commitments must be text",
        )
    if declared.strip():
        raise FixedCommitmentSourceError(
            "UNTYPED_FIXED_COMMITMENTS_REQUIRE_MIGRATION",
            (
                "non-empty fixed-commitment text cannot be converted into typed "
                "dates/load semantics without explicit user-confirmed data"
            ),
        )

    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "fixed_commitments_revision": {
                "revision_id": f"athlete-profile-empty:{revision}",
                "source_refs": [
                    f"athlete_profile:revision:{revision}",
                    "athlete_profile:constraints:fixed_commitments:explicitly_empty",
                ],
                "commitments": [],
            },
        },
    }
