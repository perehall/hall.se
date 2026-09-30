"""Canonical capability registry for planning and athlete-state feedback.

The registry owns stable capability semantics: labels, disciplines, evidence/dose
metrics, allowed progression axes, and workout recipe families. It does not
prescribe load; it defines what the rest of the system is allowed to mean when
it says a capability was trained or progressed.
"""

from __future__ import annotations

from copy import deepcopy


CAPABILITY_REGISTRY = {
    "run_threshold": {
        "label": "Kontrollerad löptröskel",
        "discipline": "run",
        "response_metric": "work_minutes",
        "default_recipe": "run_threshold",
        "recipe_family": ("run_threshold", "run_threshold_short_reps"),
        "progression_axes": ("work_duration", "interval_structure", "consistency"),
        "evidence_policy": "confirmed_or_plan_matched",
    },
    "run_hill_quality": {
        "label": "Backstyrka / löpekonomi",
        "discipline": "run",
        "response_metric": "repetitions",
        "default_recipe": "run_hill_quality",
        "recipe_family": ("run_hill_quality", "run_hill_continuous"),
        "progression_axes": ("repetitions", "set_structure", "consistency"),
        "evidence_policy": "confirmed_or_plan_matched",
    },
    "run_easy_distance": {
        "label": "Lugn löpdistans / tålighet",
        "discipline": "run",
        "response_metric": "duration_minutes",
        "default_recipe": "run_easy_distance",
        "recipe_family": ("run_easy_distance", "run_easy_trail"),
        "progression_axes": ("session_duration", "terrain_specificity", "consistency"),
        "evidence_policy": "plan_matched_or_explicit",
    },
    "mtb_technical": {
        "label": "MTB teknisk fart",
        "discipline": "bike",
        "response_metric": "duration_minutes",
        "default_recipe": "mtb_technical",
        "recipe_family": ("mtb_technical",),
        "progression_axes": ("technical_quality", "session_duration", "specificity"),
        "evidence_policy": "plan_matched_or_explicit",
    },
    "mtb_aerobic": {
        "label": "MTB/XC aerob kapacitet",
        "discipline": "bike",
        "response_metric": "duration_minutes",
        "default_recipe": "mtb_aerobic_endurance",
        "recipe_family": ("mtb_aerobic_endurance", "mtb_technical"),
        "progression_axes": ("session_duration", "consistency", "specificity"),
        "evidence_policy": "plan_matched_or_explicit",
    },
    "swim_aerobic": {
        "label": "Sim aerob kapacitet",
        "discipline": "swim",
        "response_metric": "distance_m",
        "default_recipe": "swim_aerobic_technique",
        "recipe_family": (
            "swim_aerobic_technique",
            "swim_aerobic_endurance",
            "swim_aerobic_skills",
        ),
        "progression_axes": ("distance", "consistency", "technical_quality"),
        "evidence_policy": "plan_matched_or_explicit",
    },
    "swim_technique": {
        "label": "Simteknik",
        "discipline": "swim",
        "response_metric": None,
        "default_recipe": "swim_aerobic_technique",
        "recipe_family": (
            "swim_aerobic_technique",
            "swim_aerobic_skills",
            "swim_aerobic_endurance",
        ),
        "progression_axes": ("technical_quality", "consistency"),
        "evidence_policy": "plan_matched_or_explicit",
    },
    "swim_threshold": {
        "label": "Kontrollerad simtröskel",
        "discipline": "swim",
        "response_metric": "distance_m",
        "default_recipe": "swim_aerobic_threshold",
        "recipe_family": ("swim_aerobic_threshold",),
        "progression_axes": ("threshold_volume", "consistency"),
        "evidence_policy": "confirmed_or_plan_matched",
    },
    "strength_unilateral": {
        "label": "Unilateral benstyrka",
        "discipline": "strength",
        "response_metric": "duration_minutes",
        "default_recipe": "strength_core",
        "recipe_family": ("strength_core",),
        "progression_axes": ("exercise_quality", "volume", "consistency"),
        "evidence_policy": "plan_matched_or_explicit",
    },
    "strength_core": {
        "label": "Core",
        "discipline": "strength",
        "response_metric": "duration_minutes",
        "default_recipe": "strength_core",
        "recipe_family": ("strength_core",),
        "progression_axes": ("exercise_quality", "volume", "consistency"),
        "evidence_policy": "plan_matched_or_explicit",
        "response_alias": "strength_unilateral",
    },
    "plyometric": {
        "label": "Plyometrisk exponering",
        "discipline": "strength",
        "response_metric": None,
        "default_recipe": "strength_core",
        "recipe_family": ("strength_core",),
        "progression_axes": ("contacts", "technical_quality", "reactivity"),
        "evidence_policy": "explicit_only",
    },
    "enduro_technical": {
        "label": "Enduroteknik",
        "discipline": "enduro",
        "response_metric": "duration_minutes",
        "default_recipe": None,
        "recipe_family": (),
        "progression_axes": ("technical_quality", "duration"),
        "evidence_policy": "external_observed",
    },
}


def capability_keys() -> tuple[str, ...]:
    return tuple(CAPABILITY_REGISTRY)


def capability_spec(key: str) -> dict:
    value = CAPABILITY_REGISTRY.get(str(key))
    if value is None:
        raise KeyError(f"unknown capability: {key}")
    return deepcopy(value)


def capability_label(key: str) -> str:
    return str(capability_spec(key)["label"])


def capability_discipline(key: str) -> str:
    return str(capability_spec(key)["discipline"])


def capability_metric(key: str):
    return capability_spec(key).get("response_metric")


def capability_default_recipe(key: str):
    return capability_spec(key).get("default_recipe")


def capability_recipe_family(key: str) -> tuple[str, ...]:
    return tuple(capability_spec(key).get("recipe_family") or ())


def capability_progression_axes(key: str) -> tuple[str, ...]:
    return tuple(capability_spec(key).get("progression_axes") or ())


def capability_evidence_policy(key: str) -> str:
    return str(capability_spec(key).get("evidence_policy") or "")


def response_capability(key: str) -> str:
    spec = capability_spec(key)
    return str(spec.get("response_alias") or key)


def response_capability_for_recipe(recipe_key: str):
    recipe_key = str(recipe_key or "")
    matches = []
    for key, spec in CAPABILITY_REGISTRY.items():
        if recipe_key not in (spec.get("recipe_family") or ()):
            continue
        response_key = str(spec.get("response_alias") or key)
        if spec.get("response_metric") is None:
            continue
        matches.append(response_key)
    # Several capabilities can share one executable recipe (e.g. strength/core
    # or aerobic+technical swim). The response owner must still be unique.
    unique = tuple(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def validate_registry_against_catalog(catalog: dict) -> list[str]:
    failures = []
    recipes = (catalog or {}).get("recipes") or {}
    for key, spec in CAPABILITY_REGISTRY.items():
        default = spec.get("default_recipe")
        family = tuple(spec.get("recipe_family") or ())
        if default and default not in recipes:
            failures.append(f"{key}: default recipe {default!r} saknas")
        for recipe_key in family:
            recipe = recipes.get(recipe_key)
            if not isinstance(recipe, dict):
                failures.append(f"{key}: recipe {recipe_key!r} saknas")
                continue
            stimuli = set(str(value) for value in recipe.get("stimuli") or ())
            if key not in stimuli and not (
                key == "plyometric"
                and key in set(str(value) for value in recipe.get("optional_stimuli") or ())
            ):
                failures.append(
                    f"{key}: recipe {recipe_key!r} deklarerar inte kapaciteten som stimulus"
                )
    return failures
