#!/usr/bin/env python3
"""Architecture-v2 dependency guard.

This test deliberately constrains *new* core code. Legacy code may violate these
rules while it is being strangled, but training_core must not acquire dependencies
on the compatibility data directory, rendered HTML, or subprocess orchestration.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "träning" / "training_core"

FORBIDDEN_IMPORTS = {"subprocess"}
FORBIDDEN_TEXT = (
    'träning/data',
    'training/data',
    'finalize_',
)


def python_files() -> list[Path]:
    return sorted(CORE.rglob("*.py")) if CORE.exists() else []


def test_core_does_not_import_process_or_legacy_mutators() -> None:
    violations: list[str] = []
    for path in python_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".", 1)[0] for alias in node.names}
                bad = names & FORBIDDEN_IMPORTS
                if bad:
                    violations.append(f"{path}: imports {sorted(bad)}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in FORBIDDEN_IMPORTS:
                    violations.append(f"{path}: imports {root}")

        for token in FORBIDDEN_TEXT:
            if token in source:
                violations.append(f"{path}: contains forbidden legacy dependency {token!r}")

    assert not violations, "\n".join(violations)


def test_core_exists_as_explicit_migration_boundary() -> None:
    assert CORE.is_dir(), "training_core must exist before v2 implementation starts"
