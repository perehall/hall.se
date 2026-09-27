#!/usr/bin/env python3
"""Failure-isolated publication transaction for the training site.

The canonical training pipeline may have produced valid data before presentation
rendering starts. A renderer failure must therefore never leave partially
mutated HTML/data in the workspace. Snapshot the training tree immediately
before rendering and restore it exactly on failure.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TRAINING_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_ROOT.parent
RENDERER = TRAINING_ROOT / "scripts" / "render_training_site.py"


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def render_transaction(*, runner=subprocess.run) -> int:
    with tempfile.TemporaryDirectory(prefix="training-render-") as tmp:
        snapshot = Path(tmp) / "training"
        _copy_tree(TRAINING_ROOT, snapshot)
        result = runner([sys.executable, str(RENDERER)], cwd=REPO_ROOT, check=False)
        if result.returncode == 0:
            print("PUBLICATION_TRANSACTION_OK", flush=True)
            return 0

        failed = Path(tmp) / "failed-render"
        _copy_tree(TRAINING_ROOT, failed)
        shutil.rmtree(TRAINING_ROOT)
        _copy_tree(snapshot, TRAINING_ROOT)
        print(
            "PUBLICATION_TRANSACTION_ROLLBACK "
            f"renderer_exit={result.returncode} canonical_state_preserved=true",
            file=sys.stderr,
            flush=True,
        )
        return result.returncode


def main() -> int:
    return render_transaction()


if __name__ == "__main__":
    raise SystemExit(main())
