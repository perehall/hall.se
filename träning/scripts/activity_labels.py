#!/usr/bin/env python3
"""Canonical public names for normalized activity types.

Provider sport types remain untouched in source data. Any user-visible surface
must resolve its label through this module so deterministic facts, coach copy
and rendered activity rows use the same terminology.
"""

PUBLIC_ACTIVITY_LABELS = {
    "Run": "Löpning",
    "TrailRun": "Löpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "MountainBikeRide": "MTB/XC",
    "EMountainBikeRide": "MTB/XC",
    "Ride": "Cykel",
    "VirtualRide": "Cykel",
    "WeightTraining": "Styrka",
}


def public_activity_label(activity):
    raw_label = str(activity.get("sport_type") or "Aktivitet").strip() or "Aktivitet"
    semantic_label = str(activity.get("display_label") or "").strip()
    if semantic_label:
        return semantic_label
    return PUBLIC_ACTIVITY_LABELS.get(raw_label, raw_label)
