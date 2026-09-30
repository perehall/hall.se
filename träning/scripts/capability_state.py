"""Capability-level feedback state built from verified completed training.

This module combines quantitative dose-response facts with verified plan/stimulus
matches. It never upgrades a qualitative capability (for example technique) to
"progression ready" from duration or distance alone.
"""

from __future__ import annotations

from capability_registry import (
    CAPABILITY_REGISTRY,
    capability_label,
    capability_metric,
    capability_progression_axes,
    capability_recipe_family,
)


def _verified_profile_exposures(recent_sessions):
    by_capability = {key: [] for key in CAPABILITY_REGISTRY}
    for row in recent_sessions or []:
        profile = row.get("training_profile") or {}
        confirmed = {
            str(item.get("key"))
            for item in (profile.get("stimuli") or [])
            if isinstance(item, dict)
            and item.get("status") == "confirmed"
            and str(item.get("key") or "")
        }
        credits = {
            str(value)
            for value in (profile.get("planning_credits") or [])
            if str(value or "")
        }
        for capability in sorted((confirmed | credits).intersection(CAPABILITY_REGISTRY)):
            source = "confirmed_stimulus" if capability in confirmed else "plan_matched"
            by_capability[capability].append(
                {
                    "activity_id": row.get("id"),
                    "date": row.get("date"),
                    "family": row.get("family"),
                    "source": source,
                    "elapsed_time_s": row.get("elapsed_time_s"),
                    "distance_m": row.get("distance_m"),
                }
            )
    return by_capability


def build_capability_states(recent_sessions, dose_response):
    exposures = _verified_profile_exposures(recent_sessions)
    dose_by_capability = (dose_response or {}).get("by_capability") or {}
    states = {}

    for key in CAPABILITY_REGISTRY:
        metric = capability_metric(key)
        verified = tuple(exposures.get(key) or ())
        dose = dose_by_capability.get(key) or {}

        if metric is not None:
            evidence_state = str(dose.get("evidence_state") or "missing")
            progression_state = str(dose.get("progression_state") or "establish")
            progression_ready = bool(dose.get("progression_ready") is True)
            reason_code = str(
                dose.get("progression_reason_code") or "missing_exposure"
            )
            reason = str(
                dose.get("progression_reason") or "Ingen verifierad exponering finns."
            )
        elif verified:
            evidence_state = "observed"
            progression_state = "qualitative_review"
            progression_ready = False
            reason_code = "qualitative_capability_requires_quality_review"
            reason = (
                "Kapaciteten har verifierad exponering, men progression kan inte "
                "avgöras från tid/distans utan kvalitativ eller specifik teknisk evidens."
            )
        else:
            evidence_state = "missing"
            progression_state = "establish"
            progression_ready = False
            reason_code = "missing_exposure"
            reason = "Ingen verifierad exponering finns."

        states[key] = {
            "label": capability_label(key),
            "metric": metric,
            "evidence_state": evidence_state,
            "progression_state": progression_state,
            "progression_ready": progression_ready,
            "progression_reason_code": reason_code,
            "progression_reason": reason,
            "demonstrated_value": dose.get("demonstrated_value"),
            "tolerated_value": dose.get("tolerated_value"),
            "absorbed_value": dose.get("absorbed_value"),
            "progression_axes": list(capability_progression_axes(key)),
            "recipe_family": list(capability_recipe_family(key)),
            "verified_exposure_count": len(verified),
            "latest_verified_exposure": verified[-1] if verified else None,
            "verified_exposures": list(verified[-8:]),
        }

    return {
        "model": "capability_feedback_state_v1",
        "principle": (
            "Kvantitativ progression kräver verifierad capability-evidens och "
            "dose-response. Teknikförmågor kan vara observerade men blir inte "
            "automatiskt progressionsredo från tid eller distans."
        ),
        "by_capability": states,
    }
