#!/usr/bin/env python3
"""Canonical planning-relevant goal contract helpers.

Only fields that should invalidate an active mesocycle belong in the contract
hash. Editorial status, phase labels and display metadata may change without
forcing a training-direction review.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy


def planning_goal_payload(goal: dict) -> dict:
    return {
        "goal": str(goal.get("goal") or "").strip(),
        "performance_goals": deepcopy(goal.get("performance_goals") or []),
    }


def planning_goal_hash(goal: dict) -> str:
    payload = planning_goal_payload(goal)
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
