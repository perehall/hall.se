#!/usr/bin/env python3
"""Run deterministic training tests against pinned plan and strategy fixtures.

Production plan and training strategy are mutable state. Regression tests must
not depend on whichever week or demonstrated progression happens to be live
when CI runs. The runner therefore validates the live strategy contract first,
then temporarily stages reviewed fixtures and restores the exact live bytes
afterwards.
"""

from __future__ import annotations

import compileall
import json
import subprocess
import sys
from pathlib import Path

from strategy_contracts import StrategyContractError, validate_training_strategy

TRAINING_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_ROOT.parent
PLAN_FILE = TRAINING_ROOT / "data" / "plan.json"
STRATEGY_FILE = TRAINING_ROOT / "data" / "training_strategy.json"
PLAN_FIXTURE_FILE = TRAINING_ROOT / "tests" / "fixtures" / "plan-regression.json"
STRATEGY_FIXTURE_FILE = TRAINING_ROOT / "tests" / "fixtures" / "training-strategy-regression.json"


def compile_sources() -> bool:
    return all(
        (
            compileall.compile_dir(str(TRAINING_ROOT / "scripts"), quiet=1),
            compileall.compile_dir(str(TRAINING_ROOT / "tests"), quiet=1),
        )
    )


def validate_live_strategy(strategy_bytes: bytes) -> bool:
    try:
        document = json.loads(strategy_bytes.decode("utf-8"))
        validate_training_strategy(document)
    except (UnicodeDecodeError, json.JSONDecodeError, StrategyContractError) as exc:
        print(f"REGRESSION_LIVE_STRATEGY_FAILED {exc}", file=sys.stderr)
        return False
    print("REGRESSION_LIVE_STRATEGY_OK")
    return True


def main() -> int:
    required = (
        ("live plan", PLAN_FILE),
        ("live strategy", STRATEGY_FILE),
        ("plan fixture", PLAN_FIXTURE_FILE),
        ("strategy fixture", STRATEGY_FIXTURE_FILE),
    )
    for label, path in required:
        if not path.is_file():
            print(f"REGRESSION_SETUP_FAILED missing {label}: {path}", file=sys.stderr)
            return 2

    original_plan = PLAN_FILE.read_bytes()
    original_strategy = STRATEGY_FILE.read_bytes()
    if not validate_live_strategy(original_strategy):
        return 1

    fixture_plan = PLAN_FIXTURE_FILE.read_bytes()
    fixture_strategy = STRATEGY_FIXTURE_FILE.read_bytes()

    print("REGRESSION_FIXTURE_STAGE plan-regression.json + training-strategy-regression.json")
    try:
        PLAN_FILE.write_bytes(fixture_plan)
        STRATEGY_FILE.write_bytes(fixture_strategy)
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
        STRATEGY_FILE.write_bytes(original_strategy)
        print("REGRESSION_FIXTURE_RESTORED live plan + strategy")


if __name__ == "__main__":
    raise SystemExit(main())
