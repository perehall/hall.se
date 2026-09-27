#!/usr/bin/env python3
"""Report or enforce v2 presentation cutover readiness."""

from __future__ import annotations

import argparse

from training_core.presentation.cutover import (
    SURFACES,
    assert_contract_complete,
    blocker_keys,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="fail when any retained cutover blocker remains",
    )
    args = parser.parse_args()

    assert_contract_complete()
    blockers = blocker_keys()
    for surface in SURFACES:
        print(
            f"V2_SURFACE {surface.state.upper():8s} "
            f"{surface.key}: {surface.rationale}"
        )
    if blockers:
        print("V2_CUTOVER_BLOCKED " + ",".join(blockers))
        return 1 if args.require_ready else 0
    print("V2_CUTOVER_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
