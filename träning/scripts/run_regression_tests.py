#!/usr/bin/env python3
"""Run deterministic training tests against a pinned plan fixture.

The production plan is mutable calendar state. Regression tests must not depend
on whichever week happens to be live when CI runs, so this runner temporarily
stages a reviewed plan fixture and restores the exact live bytes afterwards.
"""

from __future__ import annotations

import compileall
import subprocess
import sys
from pathlib import Path

TRAINING_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_ROOT.parent
PLAN_FILE = TRAINING_ROOT / "data" / "plan.json"
FIXTURE_FILE = TRAINING_ROOT / "tests" / "fixtures" / "plan-regression.json"


def compile_sources() -> bool:
    return all(
        (
            compileall.compile_dir(str(TRAINING_ROOT / "scripts"), quiet=1),
            compileall.compile_dir(str(TRAINING_ROOT / "tests"), quiet=1),
        )
    )


def main() -> int:
    if not PLAN_FILE.is_file():
        print(f"REGRESSION_SETUP_FAILED missing live plan: {PLAN_FILE}", file=sys.stderr)
        return 2
    if not FIXTURE_FILE.is_file():
        print(f"REGRESSION_SETUP_FAILED missing fixture: {FIXTURE_FILE}", file=sys.stderr)
        return 2

    original_plan = PLAN_FILE.read_bytes()
    fixture_plan = FIXTURE_FILE.read_bytes()

    print("REGRESSION_FIXTURE_STAGE plan-regression.json")
    try:
        PLAN_FILE.write_bytes(fixture_plan)
        if not compile_sources():
            print("REGRESSION_COMPILE_FAILED", file=sys.stderr)
            return 1

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(TRAINING_ROOT / "tests"),
                "-p",
                "test_*.py",
                "-v",
            ],
            cwd=REPO_ROOT,
            check=False,
        )
        return result.returncode
    finally:
        PLAN_FILE.write_bytes(original_plan)
        print("REGRESSION_FIXTURE_RESTORED live plan")


if __name__ == "__main__":
    raise SystemExit(main())
