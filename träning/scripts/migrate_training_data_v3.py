#!/usr/bin/env python3
"""Offline canonical-plan guard retained for explicit forensic migrations.

This module is not part of runtime or deployment. It deliberately refuses to
infer physical workouts from calendar rows. Pre-canonical documents require an
explicit reviewed migration artifact; schema-v3 documents may only be cleaned
so `days` remains presentation geometry.
"""
from __future__ import annotations

import json
from pathlib import Path

from training_contracts import PLAN_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILES = [ROOT / "data" / "plan.json", ROOT / "data" / "upcoming_week.json"]
COACH_FILE = ROOT / "data" / "coach.json"


def materialize_physical_workouts(document, catalog=None):
    workouts = document.get("planned_workouts")
    if not isinstance(workouts, list):
        raise RuntimeError(
            "Offline migration: planned_workouts saknas; fysisk träningsidentitet "
            "får inte härledas från days"
        )
    return False


def _calendar_axis_only(document):
    days = document.get("days")
    if not isinstance(days, list):
        raise RuntimeError("Offline migration: days måste vara en lista")
    cleaned = []
    for row in days:
        if not isinstance(row, dict):
            raise RuntimeError("Offline migration: days innehåller icke-objekt")
        date_value = str(row.get("date") or "").strip()
        label = str(row.get("label") or "").strip()
        if not date_value or not label:
            raise RuntimeError("Offline migration: kalenderaxel saknar date/label")
        cleaned.append({"date": date_value, "label": label})
    changed = cleaned != days
    document["days"] = cleaned
    return changed


def migrate_plan(path, catalog=None):
    if not path.exists():
        return False
    document = json.loads(path.read_text(encoding="utf-8"))
    version = document.get("schema_version")
    if version != PLAN_SCHEMA_VERSION:
        raise RuntimeError(
            f"Offline migration: {path.name} schema_version {version!r} är pre-canonical; "
            "automatisk datum-/sportmappning är förbjuden"
        )
    materialize_physical_workouts(document)
    changed = _calendar_axis_only(document)
    if changed:
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def migrate_coach_history():
    if not COACH_FILE.exists():
        return False
    document = json.loads(COACH_FILE.read_text(encoding="utf-8"))
    changed = False
    for entry in document.get("analyses") or []:
        assessment = entry.get("assessment") or {}
        if assessment.get("confidence") == "high" and assessment.get("unknowns"):
            assessment["confidence"] = "medium"
            changed = True
    if changed:
        COACH_FILE.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def main():
    changed = [path.name for path in PLAN_FILES if migrate_plan(path)]
    if migrate_coach_history():
        changed.append(COACH_FILE.name)
    print(
        "Offline canonical migration: "
        + (", ".join(changed) if changed else "inga ändringar")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
