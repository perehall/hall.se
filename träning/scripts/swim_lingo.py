#!/usr/bin/env python3
"""Canonical Swedish swim-equipment terminology for prescriptions and UI."""

from __future__ import annotations

from typing import Any


EQUIPMENT_LABELS = {
    "paddles": "paddlar",
    "pull_buoy": "dolme",
    "fins": "fenor",
    "snorkel": "snorkel",
    "kickboard": "platta",
}

EQUIPMENT_ALIASES = {
    **{key: key for key in EQUIPMENT_LABELS},
    "paddlar": "paddles",
    "dolme": "pull_buoy",
    "fenor": "fins",
    "platta": "kickboard",
}

NO_EQUIPMENT = {"none", "inga", "utan redskap"}


class SwimEquipmentError(ValueError):
    pass


def normalize_equipment(value: Any) -> list[str]:
    if value is None:
        raise SwimEquipmentError("simredskap saknas")
    if isinstance(value, str):
        key = value.strip().lower()
        if key in NO_EQUIPMENT:
            return []
        value = [key]
    if not isinstance(value, list):
        raise SwimEquipmentError(f"ogiltigt simredskap: {value!r}")

    normalized = []
    for raw in value:
        key = str(raw).strip().lower()
        if not key:
            continue
        canonical = EQUIPMENT_ALIASES.get(key)
        if canonical is None:
            raise SwimEquipmentError(f"okänt simredskap: {raw!r}")
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def equipment_lingo(value: Any) -> str:
    equipment = normalize_equipment(value)
    if not equipment:
        return "utan redskap"
    return " + ".join(EQUIPMENT_LABELS[item] for item in equipment)
