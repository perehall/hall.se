#!/usr/bin/env python3
"""Adaptive planning engine.

The fixed planning policy and goal are inputs. Athlete-state facts are inputs.
Mesocycle and microcycle decisions are generated outputs. The compatibility
training_strategy.json is materialized from those outputs so legacy render,
workout-design and near-term coaching layers can continue to operate while the
source of planning authority moves out of the handwritten strategy document.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from athlete_profile_source import load_athlete_profile_for_planner, planner_profile_view
from athlete_starting_state_source import load_starting_state_for_planner, planner_starting_state_view
from canonical_plan import planned_workouts as canonical_planned_workouts
from coach_decisions import (
    append_coach_decisions,
    build_coach_decisions,
    load_coach_decision_ledger,
)
from capability_registry import (
    CAPABILITY_REGISTRY,
    capability_default_recipe,
    capability_evidence_policy,
    capability_label,
    capability_metric,
    capability_progression_axes,
    capability_recipe_family,
    response_capability_for_recipe,
    validate_registry_against_catalog,
)
from goal_contracts import planning_goal_hash, planning_goal_set
from development_roadmap import build_development_roadmap
from race_contracts import build_competition_context
from rollover_week import (
    build_mesocycle_next_week,
    is_enduro_school_date,
    promote_upcoming,
)
from strategy_contracts import validate_training_strategy
from supabase_goal_source import load_goal_for_planner
from openai_usage import log_openai_usage

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GOAL_FILE = DATA / "goal.json"
POLICY_FILE = DATA / "planning_policy.json"
CATALOG_FILE = DATA / "workout_catalog.json"
ATHLETE_STATE_FILE = DATA / "athlete_state.json"
PLAN_FILE = DATA / "plan.json"
UPCOMING_FILE = DATA / "upcoming_week.json"
STRATEGY_FILE = DATA / "training_strategy.json"
MESO_FILE = DATA / "mesocycle_decision.json"
MICRO_FILE = DATA / "microcycle_decision.json"
DECISION_LOG_FILE = DATA / "decision_log.json"
COACH_DECISIONS_FILE = DATA / "coach_decisions.json"
WEEKS_DIR = DATA / "weeks"

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
MESO_SCHEMA_VERSION = 1
MICRO_SCHEMA_VERSION = 1
PLANNER_REVISION = 6
MICRO_PLANNER_REVISION = 17

CAPABILITY_TO_RECIPE = {
    key: capability_default_recipe(key)
    for key in CAPABILITY_REGISTRY
    if capability_default_recipe(key)
}

RECIPE_TO_RESPONSE_CAPABILITY = {
    recipe_key: response_capability_for_recipe(recipe_key)
    for recipe_key in {
        recipe
        for spec in CAPABILITY_REGISTRY.values()
        for recipe in (spec.get("recipe_family") or ())
    }
    if response_capability_for_recipe(recipe_key)
}


FIXED_PROTECTED_CAPACITY = (
    "strength_unilateral",
    "strength_core",
    "swim_aerobic",
    "swim_technique",
    "plyometric",
)
REQUIRED_EACH_MICROCYCLE = (
    "strength_unilateral",
    "strength_core",
    "swim_aerobic",
    "swim_technique",
)
EXTERNAL_LOAD_CAPABILITIES = ("enduro_technical",)

# A capability may be important without being eligible as the primary development
# target today. Primary status requires an executable direct recipe: the planner
# must be able to turn the strategic choice into an inspectable workout without
# inventing missing sets/reps/load. Strength/plyometry stay protected capacity
# until that executable prescription layer exists.
PRIMARY_CAPABILITIES_WITH_EXECUTABLE_RECIPES = {
    "run_threshold",
    "run_hill_quality",
    "run_easy_distance",
    "mtb_technical",
    "mtb_aerobic",
    "swim_aerobic",
    "swim_technique",
    "swim_threshold",
}
SUPPORT_ONLY_RECIPES = {"strength_core"}
RUN_STRESS_RECIPES = {
    "run_threshold",
    "run_threshold_short_reps",
    "run_hill_quality",
    "run_hill_continuous",
    "run_easy_distance",
    "run_easy_trail",
}
DAY_AFTER_ENDURO_BLOCKED_RECIPES = RUN_STRESS_RECIPES | {
    "mtb_technical",
    "mtb_aerobic_endurance",
    "strength_core",
}


def load_json(path: Path, fallback):
    if not path.exists():
        return deepcopy(fallback)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_hash(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def goal_hash(goal) -> str:
    return planning_goal_hash(goal)


WEEKDAY_KEYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
)


def athlete_profile_hash(profile) -> str | None:
    view = planner_profile_view(profile)
    return canonical_hash(view) if view else None


def athlete_starting_state_hash(starting_state) -> str | None:
    view = planner_starting_state_view(starting_state)
    return canonical_hash(view) if view else None


def starting_state_value_for_recipe(recipe_key, starting_state):
    """Return a user-declared establishment marker, never tolerance evidence."""
    view = planner_starting_state_view(starting_state) or {}
    manual = view.get("manual_state") or {}
    disciplines = manual.get("disciplines") or {}

    def numeric(discipline, field):
        value = (disciplines.get(discipline) or {}).get(field)
        return float(value) if isinstance(value, (int, float)) and value > 0 else None

    response_capability = RECIPE_TO_RESPONSE_CAPABILITY.get(recipe_key)
    if response_capability == "run_easy_distance":
        return numeric("run", "long_run_minutes") or numeric("run", "typical_duration_minutes")
    if response_capability in {"swim_aerobic", "swim_threshold"}:
        return numeric("swim", "typical_distance_m")
    if response_capability in {"mtb_technical", "mtb_aerobic"}:
        return numeric("mtb", "typical_duration_minutes") or numeric("bike", "typical_duration_minutes")
    if recipe_key == "strength_core":
        return numeric("strength", "typical_duration_minutes")
    return None


def profile_planning_contract(profile):
    """Normalize only user-declared planning inputs.

    Availability is a hard life constraint. Frequency, double-session and rest
    settings are declared planning preferences; they are never inferred from
    training history. Observed capacity remains exclusively in athlete_state.
    """
    view = planner_profile_view(profile) or {}
    availability = view.get("availability") or {}
    preferences = view.get("preferences") or {}
    frequency = preferences.get("frequency") or {}

    allowed_days = []
    unavailable_days = []
    available_minutes = {}
    for index, key in enumerate(WEEKDAY_KEYS, start=1):
        row = availability.get(key)
        if not isinstance(row, dict):
            continue
        if row.get("available") is False:
            unavailable_days.append(index)
            continue
        allowed_days.append(index)
        minutes = row.get("minutes")
        if isinstance(minutes, int):
            available_minutes[index] = minutes

    def day_value(name):
        value = frequency.get(name)
        return int(value) if isinstance(value, int) and 1 <= value <= 7 else None

    return {
        "availability_declared": bool(availability),
        "available_days": allowed_days,
        "unavailable_days": unavailable_days,
        "available_minutes": available_minutes,
        "preferred_active_days": day_value("preferred_days"),
        "min_active_days": day_value("min_days"),
        "max_active_days": day_value("max_days"),
        "double_sessions": preferences.get("double_sessions"),
        "rest_days": preferences.get("rest_days"),
        "facilities": list(preferences.get("facilities") or []),
        "fixed_commitments": str((view.get("constraints") or {}).get("fixed_commitments") or "").strip(),
        "other_constraints": str((view.get("constraints") or {}).get("other") or "").strip(),
        "coach_autonomy": view.get("coach_autonomy"),
        "declared_goals": list(view.get("goals") or []),
    }


def sanitize_athlete_state(state):
    cleaned = deepcopy(state)
    cleaned.pop("generated_at_utc", None)
    return cleaned


def iso(value):
    return date.fromisoformat(str(value))


def closed_planning_day_indexes(target_start, planning_date):
    """Days strictly before the live planning date are immutable."""
    if planning_date is None:
        return set()
    if isinstance(planning_date, str):
        planning_date = iso(planning_date)
    if not isinstance(planning_date, date):
        return set()
    delta = (planning_date - target_start).days
    if delta <= 0:
        return set()
    return set(range(1, min(delta, 7) + 1))


def week_key(start):
    if isinstance(start, str):
        start = iso(start)
    y, w, _ = start.isocalendar()
    return f"{y}-W{w:02d}"


def mesocycle_block_context(meso, target_start, policy):
    """Return this microcycle's intended role inside the mesocycle.

    The wave is a planning intent, never an automatic load prescription.
    Actual dose still comes from demonstrated athlete state and near-term load.
    """
    try:
        duration = int(meso.get("duration_weeks") or 0)
        index = ((target_start - iso(meso["start_date"])).days // 7) + 1
    except (KeyError, TypeError, ValueError):
        duration = 0
        index = 1

    configured = (
        ((policy.get("periodization_policy") or {}).get("microcycle_wave_by_duration") or {})
        .get(str(duration))
    )
    if isinstance(configured, list) and len(configured) == duration and duration > 0:
        wave = [str(item) for item in configured]
    elif duration == 3:
        wave = ["establish", "develop", "consolidate"]
    elif duration == 5:
        wave = ["establish", "develop", "develop", "consolidate", "review"]
    else:
        wave = ["establish", "develop", "develop", "consolidate"]

    index = max(1, min(index, len(wave)))
    intent = wave[index - 1]
    definitions = (policy.get("periodization_policy") or {}).get("intent_definitions") or {}
    return {
        "microcycle_index": index,
        "microcycle_total": len(wave),
        "block_intent": intent,
        "wave": wave,
        "intent_definition": str(definitions.get(intent) or ""),
        "principle": str((policy.get("periodization_policy") or {}).get("principle") or ""),
    }


def recipe_family_for_capability(catalog, capability):
    recipes = catalog.get("recipes") or {}
    configured = capability_recipe_family(capability)
    valid = [
        key for key in configured
        if key in recipes
        and (
            capability in recipe_capabilities(recipes[key])
            or capability in set(recipes[key].get("optional_stimuli") or [])
        )
    ]
    if valid:
        return valid
    fallback = CAPABILITY_TO_RECIPE.get(capability)
    return [fallback] if fallback in recipes else []


def _blueprint_family_index(block_context, family_size):
    if family_size <= 1:
        return 0
    intent = str(block_context.get("block_intent") or "")
    index = int(block_context.get("microcycle_index") or 1)
    if intent == "establish":
        return 0
    if intent == "develop":
        develop_ordinal = sum(
            1
            for item in (block_context.get("wave") or [])[:index]
            if item == "develop"
        )
        return develop_ordinal % family_size
    return 0


def build_development_blueprint(
    meso,
    policy,
    catalog,
    athlete_state=None,
    starting_state=None,
):
    """Publish the mesocycle's intended workout-character progression.

    This is the coach's ground plan, not a frozen calendar. It deliberately
    separates planned variation/progression from near-term dose authorization:
    future develop weeks may state progress_if_ready even though exact dose is
    decided only when athlete response and adjacent load are known.
    """
    try:
        start = iso(meso["start_date"])
        duration = int(meso.get("duration_weeks") or 0)
    except (KeyError, TypeError, ValueError):
        return []

    recipes = catalog.get("recipes") or {}
    normal_swims = int((policy.get("microcycle_policy") or {}).get("normal_swim_exposures", 2))

    def dose_plan(recipe_key, recipe, progression_intent):
        if athlete_state is None:
            return {}
        try:
            selected, floor, next_option, _, _ = choose_option(
                recipe_key,
                recipe,
                "consolidate",
                athlete_state,
                starting_state,
            )
        except (KeyError, RuntimeError, TypeError, ValueError):
            return {}
        result = {
            "baseline_option_id": str(selected.get("id") or ""),
            "baseline_session": str(selected.get("session") or ""),
        }
        if progression_intent == "progress_if_ready" and next_option is not None:
            result.update(
                {
                    "conditional_target_option_id": str(next_option.get("id") or ""),
                    "conditional_target_session": str(next_option.get("session") or ""),
                    "target_condition": "progression_ready_and_absorbable_context",
                }
            )
        return result
    rows = []
    for offset in range(max(0, duration)):
        week_start = start + timedelta(days=7 * offset)
        context = mesocycle_block_context(meso, week_start, policy)
        intent = context.get("block_intent")
        variants = []
        covered = set()

        for capability in meso.get("primary_capabilities") or []:
            if capability in covered:
                continue
            family = recipe_family_for_capability(catalog, capability)
            if not family:
                continue
            family_index = _blueprint_family_index(context, len(family))
            recipe_key = family[family_index]
            recipe = recipes[recipe_key]
            stimuli = set(recipe_capabilities(recipe))
            covered.update(stimuli.intersection(set(meso.get("primary_capabilities") or [])))
            progression_intent = (
                "establish"
                if intent == "establish"
                else "vary_structure"
                if intent == "develop" and int(context.get("microcycle_index") or 1) == 2
                else "progress_if_ready"
                if intent == "develop"
                else "consolidate"
            )
            variants.append(
                {
                    "role": "primary",
                    "capability": capability,
                    "recipe_key": recipe_key,
                    "development_character": recipe.get("development_character") or recipe_key,
                    "label": recipe.get("blueprint_label") or (recipe.get("options") or [{}])[0].get("session") or recipe_key,
                    "progression_intent": progression_intent,
                    **dose_plan(recipe_key, recipe, progression_intent),
                }
            )

        # When aerobic/technical swim is a primary block objective, the normal
        # two-swim rhythm gets its own planned character variation rather than
        # silently repeating the same recipe.
        swim_primary = {"swim_aerobic", "swim_technique"}.intersection(
            set(meso.get("primary_capabilities") or [])
        )
        if swim_primary and normal_swims >= 2:
            existing_swim = [
                item["recipe_key"]
                for item in variants
                if (recipes.get(item["recipe_key"]) or {}).get("sport") == "swim"
            ]
            swim_family = recipe_family_for_capability(catalog, "swim_aerobic")
            alternatives = [key for key in swim_family if key not in existing_swim]
            if alternatives:
                preferred_index = min(offset, len(alternatives) - 1)
                recipe_key = alternatives[preferred_index]
                recipe = recipes[recipe_key]
                companion_intent = (
                    "establish"
                    if intent == "establish"
                    else "vary_structure"
                    if intent == "develop"
                    else "consolidate"
                )
                variants.append(
                    {
                        "role": "primary_companion",
                        "capability": "swim_aerobic",
                        "recipe_key": recipe_key,
                        "development_character": recipe.get("development_character") or recipe_key,
                        "label": recipe.get("blueprint_label") or (recipe.get("options") or [{}])[0].get("session") or recipe_key,
                        "progression_intent": companion_intent,
                        **dose_plan(recipe_key, recipe, companion_intent),
                    }
                )

        # One rotating supporting candidate makes the broader all-round plan
        # visible without turning every secondary capability into a weekly
        # checklist. Near-term planning may omit it when load does not fit.
        secondary = list(meso.get("secondary_capabilities") or [])
        supporting = []
        if secondary:
            capability = secondary[offset % len(secondary)]
            family = recipe_family_for_capability(catalog, capability)
            if family:
                recipe_key = family[_blueprint_family_index(context, len(family))]
                recipe = recipes[recipe_key]
                supporting.append(
                    {
                        "role": "supporting_candidate",
                        "capability": capability,
                        "recipe_key": recipe_key,
                        "development_character": recipe.get("development_character") or recipe_key,
                        "label": recipe.get("blueprint_label") or (recipe.get("options") or [{}])[0].get("session") or recipe_key,
                        "progression_intent": "support_if_absorbable",
                    }
                )

        protected = []
        if (policy.get("microcycle_policy") or {}).get("protect_strength_core_each_microcycle"):
            recipe = recipes.get("strength_core") or {}
            protected.append(
                {
                    "role": "protected",
                    "capability": "strength_core",
                    "recipe_key": "strength_core",
                    "development_character": recipe.get("development_character") or "strength_core",
                    "label": recipe.get("blueprint_label") or "Styrka/core",
                    "progression_intent": "protect",
                }
            )

        rows.append(
            {
                "microcycle_index": offset + 1,
                "week_start": week_start.isoformat(),
                "week_end": (week_start + timedelta(days=6)).isoformat(),
                "block_intent": intent,
                "intent_definition": context.get("intent_definition"),
                "planned_variants": variants,
                "supporting_candidates": supporting,
                "protected_variants": protected,
                "principle": (
                    "Passkaraktären är planerad på blocknivå. Exakt dag och dos materialiseras nära passet; "
                    "progress_if_ready får bara bli faktisk dosprogression när dose_response och 2–3 dagars "
                    "belastningskontext stödjer det."
                ),
            }
        )
    return rows


def development_blueprint_for_week(
    meso,
    policy,
    catalog,
    target_start,
    athlete_state=None,
    starting_state=None,
):
    for row in build_development_blueprint(
        meso,
        policy,
        catalog,
        athlete_state=athlete_state,
        starting_state=starting_state,
    ):
        if row.get("week_start") == target_start.isoformat():
            return row
    return None


def completed_context_signature(context) -> str:
    """Hash only factual completed-training semantics that may change planning."""
    context = context or {}
    capability_refs = {
        str(capability): sorted(str(value) for value in (refs or []))
        for capability, refs in sorted(
            (context.get("capability_refs") or {}).items(),
            key=lambda item: str(item[0]),
        )
    }
    payload = {
        "activity_refs": sorted(
            str(value) for value in (context.get("activity_refs") or [])
        ),
        "direct_capabilities": sorted(
            str(value) for value in (context.get("direct_capabilities") or [])
        ),
        "planning_credits": sorted(
            str(value)
            for value in (
                context.get("planning_credits")
                or context.get("direct_capabilities")
                or []
            )
        ),
        "capability_refs": capability_refs,
        "capability_day_indexes": {
            str(key): sorted(
                int(value) for value in (values or [])
                if isinstance(value, int)
            )
            for key, values in sorted((context.get("capability_day_indexes") or {}).items())
        },
        "strength_exposures": int(context.get("strength_exposures") or 0),
        "swim_exposures": int(context.get("swim_exposures") or 0),
        "enduro_exposures": int(context.get("enduro_exposures") or 0),
        "completed_slot_days": int(context.get("completed_slot_days") or 0),
        "completed_day_indexes": sorted(
            int(value) for value in (context.get("completed_day_indexes") or [])
        ),
    }
    return canonical_hash(payload)


def target_week(plan, upcoming, today):
    plan_meta = plan.get("meta") or {}
    up_meta = upcoming.get("meta") or {}
    plan_start = iso(plan_meta["week_start"])
    plan_end = iso(plan_meta["week_end"])
    upcoming_start = iso(up_meta["week_start"])

    active_requires_strategy = (
        plan_start <= today <= plan_end
        and (
            plan_meta.get("requires_mesocycle_review") is True
            or not str(plan_meta.get("mesocycle_id") or "").strip()
        )
    )
    if active_requires_strategy:
        return plan_start, True
    return upcoming_start, False


def resolve_planning_target(
    plan,
    upcoming,
    mesocycle_decision,
    today,
    goal=None,
    microcycle_decision=None,
    current_completed_context=None,
):
    """Choose the week the adaptive engine is allowed to plan.

    A generated mesocycle is authoritative for its full declared duration.
    Planner/schema revisions alone must not reshuffle a started week. New
    canonical training evidence is different: when completed activity evidence
    or its interpreted capability changes inside the live week, that week is
    deliberately reopened so the remaining stimuli can be reconciled against
    what was actually done.
    """
    target_start, active_replan = target_week(plan, upcoming, today)
    meta = plan.get("meta") or {}
    try:
        plan_start = iso(meta["week_start"])
        plan_end = iso(meta["week_end"])
        current_index = int(meta.get("microcycle_index") or 0)
        total = int(meta.get("microcycle_total") or 0)
    except (KeyError, TypeError, ValueError):
        return target_start, active_replan

    current_id = str(meta.get("mesocycle_id") or "").strip()
    decision_id = str((mesocycle_decision or {}).get("id") or "").strip()

    # A live plan may never strand an unfulfilled planned workout on an
    # already elapsed date. That means a displaced session has been consumed by
    # presentation time without being executed or deliberately re-homed.
    if plan_start <= today <= plan_end:
        for workout in plan.get("planned_workouts") or []:
            workout_day = _workout_date(workout)
            if workout_day is None or not (plan_start <= workout_day < today):
                continue
            completed = bool(
                workout.get("activity_id")
                or workout.get("activity_ids")
                or workout.get("planning_status") == "completed"
            )
            if not completed:
                return plan_start, True

    # A started microcycle is normally stable, but actual training is first-class
    # state. Reopen the live week whenever the factual completed-context changes.
    # The comparison intentionally includes capability attribution, not only
    # activity ids, so later explicit feedback (for example "4×8 tröskel") can
    # reclassify an already imported generic run and trigger a real replan.
    if plan_start <= today <= plan_end and current_completed_context is not None:
        current_context_hash = completed_context_signature(current_completed_context)
        # The active plan is the durable baseline for the live microcycle.
        # microcycle_decision may legitimately point at the upcoming week after a
        # successful planning pass; using that file as the sole baseline would
        # cause unchanged live-week training to reopen the current week again on
        # the next pipeline run.
        plan_context = (
            ((meta.get("capacity_protection") or {}).get("completed_context"))
            or {}
        )
        micro_context = (
            (microcycle_decision or {}).get("completed_microcycle_context") or {}
        )
        micro_week_start = str(
            (microcycle_decision or {}).get("week_start") or ""
        ).strip()
        previous_context = (
            plan_context
            if plan_context
            else (
                micro_context
                if micro_week_start == plan_start.isoformat()
                else {}
            )
        )
        previous_context_hash = completed_context_signature(previous_context)
        current_has_training = bool(
            (current_completed_context or {}).get("activity_refs")
            or (current_completed_context or {}).get("direct_capabilities")
            or int((current_completed_context or {}).get("strength_exposures") or 0)
            or int((current_completed_context or {}).get("swim_exposures") or 0)
            or int((current_completed_context or {}).get("enduro_exposures") or 0)
        )
        if current_has_training and current_context_hash != previous_context_hash:
            return plan_start, True

    # A canonical goal change is the explicit exception to mesocycle authority.
    # On the first day of the live microcycle we can rebuild the whole week
    # without rewriting already-completed training. Midweek changes start with
    # the upcoming week unless a separate near-term migration is implemented.
    goal_changed = bool(
        goal
        and (mesocycle_decision or {}).get("goal_hash")
        and (mesocycle_decision or {}).get("goal_hash") != goal_hash(goal)
    )
    if goal_changed and today == plan_start:
        return plan_start, True

    # Planner revisions are implementation changes, not new athlete evidence.
    # Never rebuild an already-started live week solely because code/schema
    # changed; generate the upcoming week with the new revision instead.
    decision_start = None
    try:
        if (mesocycle_decision or {}).get("start_date"):
            decision_start = iso(mesocycle_decision["start_date"])
    except (TypeError, ValueError):
        decision_start = None

    live_block_is_midflight = (
        plan_start <= today <= plan_end
        and current_id
        and current_index > 0
        and total > 0
        and current_index < total
        and meta.get("requires_mesocycle_review") is not True
    )
    later_conflicting_decision = (
        decision_id
        and decision_id != current_id
        and decision_start is not None
        and decision_start > plan_start
    )
    if live_block_is_midflight and later_conflicting_decision:
        return plan_start, True
    return target_start, active_replan


def capability_keys(policy):
    return [item["key"] for item in policy["strategy_base"]["capability_portfolio"]]


def recipe_capabilities(recipe):
    return set(recipe.get("stimuli") or []) | set(recipe.get("optional_stimuli") or [])


def request_openai(body, api_key=None):
    key = (api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY saknas")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        log_openai_usage("adaptive_planner", result, body)
        return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail[:1600]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI transport error: {exc.reason}") from exc


def extract_output_text(response):
    chunks = []
    for item in response.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "refusal":
                raise RuntimeError(f"Planeringsmodellen avböjde: {part.get('refusal')}")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    if not chunks:
        raise RuntimeError("Planeringsmodellen returnerade ingen output_text")
    return "".join(chunks)


def call_structured(system_prompt, payload, schema, name, *, request_fn=None):
    request_fn = request_fn or request_openai
    last_error = None
    for attempt, max_tokens in enumerate((3500, 6500), start=1):
        body = {
            "model": MODEL,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "reasoning": {"effort": "medium"},
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "strict": True,
                    "schema": schema,
                },
            },
            "max_output_tokens": max_tokens,
            "store": False,
        }
        try:
            response = request_fn(body)
            if response.get("status") == "completed":
                return json.loads(extract_output_text(response))
            last_error = RuntimeError(
                f"oväntad modellstatus {response.get('status')}: {response.get('error') or response.get('incomplete_details')}"
            )
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt == 1:
            time.sleep(2)
    raise RuntimeError(f"Planeringsmodellen misslyckades: {last_error}")


def mesocycle_schema(capabilities):
    cap = {"type": "string", "enum": capabilities}
    primary_cap = {
        "type": "string",
        "enum": [
            key for key in capabilities
            if key in PRIMARY_CAPABILITIES_WITH_EXECUTABLE_RECIPES
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["continue", "modify", "shift"]},
            "title": {"type": "string"},
            "duration_weeks": {"type": "integer", "minimum": 3, "maximum": 5},
            "goal_contribution": {"type": "string"},
            "goal_contributions": {
                "type": "array",
                "minItems": 2,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "goal_id": {"type": "string"},
                        "goal_type": {"type": "string", "enum": ["development", "performance"]},
                        "contribution": {"type": "string"},
                        "tradeoff": {"type": "string"},
                    },
                    "required": ["goal_id", "goal_type", "contribution", "tradeoff"],
                },
            },
            "hypothesis": {"type": "string"},
            "primary_capabilities": {
                "type": "array", "minItems": 1, "maxItems": 3, "items": primary_cap
            },
            "secondary_capabilities": {
                "type": "array", "maxItems": 4, "items": cap
            },
            "progression_axes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "capability": cap,
                        "axis": {
                            "type": "string",
                            "enum": [
                                "work_duration",
                                "repetitions",
                                "session_duration",
                                "frequency",
                                "technical_quality",
                                "consistency",
                            ],
                        },
                        "objective": {"type": "string"},
                    },
                    "required": ["capability", "axis", "objective"],
                },
            },
            "success_signals": {
                "type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string"}
            },
            "guardrails": {
                "type": "array", "minItems": 2, "maxItems": 8, "items": {"type": "string"}
            },
            "evidence_refs": {
                "type": "array", "minItems": 1, "maxItems": 10, "items": {"type": "string"}
            },
            "uncertainties": {
                "type": "array", "maxItems": 5, "items": {"type": "string"}
            },
        },
        "required": [
            "decision",
            "title",
            "duration_weeks",
            "goal_contribution",
            "goal_contributions",
            "hypothesis",
            "primary_capabilities",
            "secondary_capabilities",
            "progression_axes",
            "success_signals",
            "guardrails",
            "evidence_refs",
            "uncertainties",
        ],
    }


def microcycle_schema(recipe_keys):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rationale": {"type": "string"},
            "slots": {
                "type": "array",
                "minItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "day_index": {"type": "integer", "minimum": 1, "maximum": 7},
                        "recipe_key": {"type": "string", "enum": recipe_keys},
                        "action": {
                            "type": "string",
                            "enum": ["establish", "progress", "consolidate", "reduce"],
                        },
                        "rationale": {"type": "string"},
                        "evidence_refs": {
                            "type": "array", "maxItems": 6, "items": {"type": "string"}
                        },
                    },
                    "required": ["day_index", "recipe_key", "action", "rationale", "evidence_refs"],
                },
            },
        },
        "required": ["rationale", "slots"],
    }


def previous_mesocycle(strategy):
    current = (strategy or {}).get("current_mesocycle")
    return deepcopy(current) if isinstance(current, dict) else {}


def normalize_goal_contributions(goal_rows, provided, summary, competition_context):
    supplied = {
        str(item.get("goal_id") or "").strip(): item
        for item in (provided or [])
        if isinstance(item, dict) and str(item.get("goal_id") or "").strip()
    }
    normalized = []
    stage = str((competition_context or {}).get("horizon_stage") or "unknown")
    for goal_item in goal_rows:
        goal_id = goal_item["id"]
        current = supplied.get(goal_id) or {}
        if goal_item["type"] == "development":
            default_contribution = (
                "Utveckla den aktuella mesocykelns prioriterade kapaciteter samtidigt som allroundprofilens "
                "övriga discipliner behålls som aktiva utvecklings- eller underhållsspår över blocken."
            )
            default_tradeoff = (
                "Det varaktiga allroundmålet får inte ersättas implicit av ett tävlingsmål; eventuell "
                "tillfällig nedprioritering ska vara explicit, tidsbegränsad och omprövas."
            )
        else:
            default_contribution = (
                f"A-målet påverkar kapacitetsbetoning och specificitet i horizon_stage={stage}, men ska "
                "inte ensamt styra träningsidentiteten eller fylla kalendern."
            )
            default_tradeoff = (
                "Tävlingsspecificitet får öka när tidshorisont och faktisk kapacitet motiverar det, "
                "men den får inte automatiskt tränga undan den varaktiga allroundutvecklingen."
            )
        normalized.append(
            {
                "goal_id": goal_id,
                "goal_type": goal_item["type"],
                "contribution": str(current.get("contribution") or default_contribution).strip(),
                "tradeoff": str(current.get("tradeoff") or default_tradeoff).strip(),
            }
        )
    return normalized


def fallback_mesocycle(goal, policy, previous, target_start=None):
    primary = []
    refs = []
    goal_rows = planning_goal_set(goal)

    competition_context = (
        build_competition_context(
            goal,
            target_start,
            policy.get("event_horizon_policy"),
        )
        if target_start is not None
        else {"available": False}
    )
    active_swimrun_goal = next(
        (
            item for item in (goal.get("performance_goals") or [])
            if item.get("status") == "active"
            and str(item.get("sport") or "").lower() == "swimrun"
        ),
        None,
    )
    if active_swimrun_goal:
        stage = competition_context.get("horizon_stage")
        if stage in {"specificity_build", "race_specific", "taper_review"}:
            primary.extend(["run_easy_distance", "swim_aerobic", "swim_threshold"])
        else:
            primary.extend(["run_threshold", "swim_aerobic", "run_easy_distance"])
        refs.extend(
            [
                f"goal.performance_goals[{active_swimrun_goal.get('id')}]",
                "competition_context.race_profile",
                "competition_context.days_to_event",
            ]
        )

    for index, text in enumerate(goal.get("next_steps") or []):
        lower = str(text).lower()
        candidate = None
        if "trösk" in lower:
            candidate = "run_threshold"
        elif "sim" in lower or "swim" in lower:
            candidate = "swim_aerobic"
        elif "mtb" in lower or "xc" in lower:
            candidate = "mtb_technical"
        elif "distans" in lower and "löp" in lower:
            candidate = "run_easy_distance"
        if candidate and candidate not in primary and len(primary) < 3:
            primary.append(candidate)
            refs.append(f"goal.next_steps[{index}]")
        if len(primary) >= 3:
            break
    if "run_easy_distance" not in primary and len(primary) < 3:
        primary.append("run_easy_distance")
        refs.append("goal.goal")
    if not primary:
        primary = ["run_threshold", "mtb_technical"]
        refs = ["goal.goal"]

    previous_primary = set(previous.get("protected_stimuli") or [])
    decision = "continue" if set(primary) == previous_primary else "modify"
    enduring_disciplines = {
        discipline
        for item in goal_rows
        if item.get("type") == "development"
        for discipline in (item.get("disciplines") or [])
    }
    fallback_secondary_candidates = ["run_hill_quality"]
    if "mtb" in enduring_disciplines:
        fallback_secondary_candidates.extend(["mtb_technical", "mtb_aerobic"])
    if not active_swimrun_goal and "swim" in enduring_disciplines:
        fallback_secondary_candidates.append("swim_threshold")
    secondary = [
        key
        for key in fallback_secondary_candidates
        if key not in primary
    ]
    return {
        "decision": decision,
        "title": "Mesocykel · " + " + ".join(
            {
                "run_threshold": "kontrollerad löptröskel",
                "run_easy_distance": "löptålighet",
                "mtb_technical": "MTB-teknik",
                "swim_aerobic": "simkapacitet",
                "swim_technique": "simteknik",
            }.get(key, key)
            for key in primary
        ),
        "duration_weeks": 4,
        "goal_contribution": (
            (
                f"Föra målbilden mot {competition_context.get('event')} genom att bygga kapaciteter som matchar "
                f"den verifierade banprofilen med {competition_context.get('days_to_event')} dagar kvar, utan att "
                "låta kalendern ensam driva belastningsökning."
            )
            if competition_context.get("available")
            else
            "Föra den kanoniska målbilden och dess aktiva prestationsmål framåt genom att utveckla "
            "få tydliga kapaciteter samtidigt som övrig långsiktig allroundkapacitet skyddas."
        ),
        "goal_contributions": normalize_goal_contributions(
            goal_rows,
            [],
            "",
            competition_context,
        ),
        "hypothesis": (
            "Ett block med få tydliga utvecklingsområden och bibehållen bredd ger bättre möjlighet "
            "att skapa faktisk progression än att upprepa en färdig veckomall."
        ),
        "primary_capabilities": primary[:3],
        "secondary_capabilities": secondary,
        "progression_axes": [
            {
                "capability": key,
                "axis": (
                    "work_duration"
                    if key == "run_threshold"
                    else "technical_quality"
                    if key == "mtb_technical"
                    else "consistency"
                    if key in {"swim_aerobic", "swim_technique"}
                    else "session_duration"
                ),
                "objective": "Utveckla kapaciteten stegvis från observerad och absorberad träningsnivå.",
            }
            for key in primary[:3]
        ],
        "success_signals": [
            "Prioriterade stimuli kan genomföras återkommande utan att övriga skyddade kapaciteter systematiskt faller bort.",
            "Jämförbara pass eller uttryckliga användarrapporter ger stöd för progression eller stabil konsolidering.",
            "Mikrocyklerna kan absorberas utan att nyckelstimuli återkommande måste tas bort.",
        ],
        "guardrails": list(policy.get("decision_guards") or [])[:8],
        "evidence_refs": refs or ["goal.goal"],
        "uncertainties": [
            "Deterministisk fallback används eftersom ingen giltig modellbedömning fanns tillgänglig.",
            *(
                [
                    "Tävlingsprofilen kräver senare swimrun-specifik kombinationstålighet och övergångsvana; "
                    "systemet får inte hitta på ett sådant direktrecept innan en exekverbar träningsmall finns."
                ]
                if competition_context.get("available")
                else []
            ),
        ],
    }


def generate_mesocycle(goal, policy, athlete_state, previous, target_start, athlete_profile=None, starting_state=None, *, request_fn=None):
    caps = capability_keys(policy)
    competition_context = build_competition_context(
        goal,
        target_start,
        policy.get("event_horizon_policy"),
    )
    goal_rows = planning_goal_set(goal)
    declared_profile = planner_profile_view(athlete_profile)
    source_payload = {
        "goal": goal,
        "declared_athlete_profile": declared_profile,
        "declared_profile_contract": profile_planning_contract(athlete_profile) if athlete_profile else None,
        "confirmed_starting_state": planner_starting_state_view(starting_state),
        "goal_set": goal_rows,
        "competition_context": competition_context,
        "policy": {
            "mesocycle_policy": policy.get("mesocycle_policy"),
            "microcycle_policy": policy.get("microcycle_policy"),
            "decision_guards": policy.get("decision_guards"),
            "event_horizon_policy": policy.get("event_horizon_policy"),
            "multi_goal_policy": policy.get("multi_goal_policy"),
            "available_capabilities": [
                {"key": item.get("key"), "label": item.get("label")}
                for item in (policy["strategy_base"].get("capability_portfolio") or [])
            ],
        },
        "athlete_state": sanitize_athlete_state(athlete_state),
        "previous_mesocycle": previous,
        "target_start": target_start.isoformat(),
    }
    digest = canonical_hash(source_payload)
    system = (
        "Du är mesocykelplaneraren i ett uthållighets-/allroundsystem. "
        "Välj vad som ska utvecklas nu; skriv inte en veckoplan och ordinera inte exakta pass. "
        "Planeringsauktoriteten består av goal_set tillsammans med declared_athlete_profile.goals. Den deklarerade profilen är användarens förstahandskälla för fria/multipla mål, praktiska ramar och preferenser; den får inte ersättas av AI-antaganden. confirmed_starting_state beskriver bekräftat startläge. Observerad del är fakta från historik; manuell del är självrapport och får användas för konservativ etablering men aldrig behandlas som absorberad dos eller ensam motivera progression. Aktiva development-goals med role=enduring anger vilken atlet som byggs och får inte ersättas implicit av ett prestationsmål. "
        "Aktiva performance-goals, inklusive A-mål, får styra betoning, konfliktlösning och successivt ökande specificitet men läggs ovanpå den varaktiga målbilden. "
        "Du måste fylla goal_contributions för varje aktivt mål och beskriva eventuell trade-off uttryckligen. "
        "competition_context innehåller verifierat tävlingsdatum, publicerad banprofil och exakt tid kvar till loppet; dessa fakta ska användas när du väljer vad som behöver utvecklas nu. "
        "Horizon_stage är en planerings-/reviewpolicy, inte en fysiologisk sanning eller automatisk dosregel. I foundation ska A-målet främst påverka betoning inom en fortsatt bred allroundutveckling. "
        "När loppet närmar sig får stimulusvalet bli mer tävlingsspecifikt när athlete_state stödjer det, men en sådan trade-off mot allroundbredd ska vara explicit och tidsbegränsad. "
        "Tid till loppet får aldrig ensam motivera mer volym, högre intensitet eller fler pass. Hitta inte på tävlingsfart, övergångsantal eller banfakta som saknas. "
        "Om en nödvändig tävlingsspecifik förmåga saknar exekverbart recept ska det anges som osäkerhet/gap, inte fyllas med ett påhittat pass. "
        "Utgå endast från målbild, competition_context, athlete_state och policy i underlaget. Föregående veckomall eller gamla prioriteringslistor är inte evidens i sig. "
        "Skilj observerade fakta från tolkning. Saknas stöd, välj konservativt och skriv osäkerheten. "
        "Kontinuitet, absorberbar belastning och kontrollerad kvalitet går före maximal träningsmängd. "
        "Enduro är faktisk belastning. Wellness får aldrig ensam motivera progression. "
        "Metodiskt ska beslutet vara förenligt med etablerad uthållighetspraktik: tydliga stimuli, "
        "begränsad samtidig progression, specificitet och långsiktig kontinuitet."
    )
    try:
        result = call_structured(
            system,
            source_payload,
            mesocycle_schema(caps),
            "mesocycle_decision",
            request_fn=request_fn,
        )
        source = "openai"
    except Exception as exc:
        result = fallback_mesocycle(goal, policy, previous, target_start)
        source = "deterministic_fallback"
        result.setdefault("uncertainties", []).append(str(exc)[:400])

    allowed = set(caps)
    eligible_primary = allowed.intersection(PRIMARY_CAPABILITIES_WITH_EXECUTABLE_RECIPES)
    requested_primary = list(result.get("primary_capabilities") or [])
    primary = []
    for key in requested_primary:
        if key in eligible_primary and key not in primary:
            primary.append(key)
    rejected_primary = [
        key for key in requested_primary
        if key in allowed and key not in eligible_primary
    ]
    if rejected_primary:
        result.setdefault("uncertainties", []).append(
            "Följande kapaciteter valdes inte som primärt utvecklingsmål eftersom "
            "systemet ännu saknar ett fullständigt exekverbart direktrecept: "
            + ", ".join(rejected_primary)
            + ". De kan fortfarande skyddas eller ligga sekundärt."
        )
    primary = primary[: int(policy["mesocycle_policy"].get("primary_capability_max", 3))]
    if not primary:
        fallback = fallback_mesocycle(goal, policy, previous)
        primary = fallback["primary_capabilities"]

    secondary = []
    protected_role_conflicts = []
    for key in result.get("secondary_capabilities") or []:
        if key not in allowed or key in primary or key in secondary:
            continue
        if key in FIXED_PROTECTED_CAPACITY:
            protected_role_conflicts.append(key)
            continue
        secondary.append(key)
    if protected_role_conflicts:
        result.setdefault("uncertainties", []).append(
            "Kapaciteter med hårt skyddskrav flyttades från secondary till protected_capacity: "
            + ", ".join(protected_role_conflicts)
            + ". De ska finnas kvar varje mikrocykel men får inte byta semantisk roll bara för att modellen placerar dem sekundärt."
        )
    result["primary_capabilities"] = primary
    result["secondary_capabilities"] = secondary[:4]
    result["goal_contributions"] = normalize_goal_contributions(
        goal_rows,
        result.get("goal_contributions"),
        result.get("goal_contribution"),
        competition_context,
    )
    result["duration_weeks"] = max(
        int(policy["mesocycle_policy"]["min_weeks"]),
        min(int(result.get("duration_weeks") or 4), int(policy["mesocycle_policy"]["max_weeks"])),
    )

    end = target_start + timedelta(days=result["duration_weeks"] * 7 - 1)
    result.update(
        {
            "schema_version": MESO_SCHEMA_VERSION,
            "planner_revision": PLANNER_REVISION,
            "source": source,
            "source_hash": digest,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "goal_hash": goal_hash(goal),
            "start_date": target_start.isoformat(),
            "end_date": end.isoformat(),
            "evaluation_date": (end + timedelta(days=1)).isoformat(),
            "competition_context": competition_context,
            "athlete_profile_hash": athlete_profile_hash(athlete_profile),
            "starting_state_hash": athlete_starting_state_hash(starting_state),
        }
    )
    result["id"] = (
        target_start.strftime("%Y%m%d")
        + "-"
        + "-".join(result["primary_capabilities"])
    )
    return result


def mesocycle_is_valid(decision, goal, target_start, profile_hash_value=None, starting_state_hash_value=None):
    if not isinstance(decision, dict):
        return False
    try:
        return (
            decision.get("schema_version") == MESO_SCHEMA_VERSION
            and decision.get("planner_revision") == PLANNER_REVISION
            and decision.get("goal_hash") == goal_hash(goal)
            and decision.get("athlete_profile_hash") == profile_hash_value
            and decision.get("starting_state_hash") == starting_state_hash_value
            and iso(decision["start_date"]) <= target_start <= iso(decision["end_date"])
            and bool(decision.get("primary_capabilities"))
        )
    except (KeyError, TypeError, ValueError):
        return False


def completed_microcycle_context(athlete_state, target_start):
    """Summarize only factual training already completed inside the target microcycle.

    Session-family counts are used for exposure requirements. Direct capability
    credit is stricter: a capability is credited only when athlete_state carries
    dated evidence for that capability in this exact microcycle. This prevents a
    generic run from being silently treated as threshold work.
    """
    end = target_start + timedelta(days=6)
    rows = []
    for session in (athlete_state.get("recent_sessions") or []):
        try:
            session_date = iso(session.get("date"))
        except (TypeError, ValueError):
            continue
        if not target_start <= session_date <= end:
            continue
        if session.get("classification") == "recreation":
            continue
        rows.append(session)

    activity_ids = {
        str(row.get("id"))
        for row in rows
        if row.get("id") is not None
    }
    direct_capabilities = set()
    capability_refs = {}
    capability_day_indexes = {}
    for capability, facts in (athlete_state.get("capability_facts") or {}).items():
        if not isinstance(facts, dict):
            continue
        # Only explicitly capability-labelled evidence belongs in
        # direct_capabilities. Generic longest-distance/duration facts are
        # descriptive sport history and must not silently become physiology.
        evidence_rows = list(facts.get("evidence") or [])
        for item in evidence_rows:
            if not isinstance(item, dict):
                continue
            try:
                evidence_date = iso(item.get("date"))
            except (TypeError, ValueError):
                continue
            activity_id = str(item.get("activity_id") or "")
            if target_start <= evidence_date <= end and activity_id in activity_ids:
                direct_capabilities.add(capability)
                capability_refs.setdefault(capability, []).append(activity_id)
                capability_day_indexes.setdefault(capability, set()).add(
                    (evidence_date - target_start).days + 1
                )

    planning_credits = set(direct_capabilities)
    planning_credit_refs = {
        key: list(values)
        for key, values in capability_refs.items()
    }
    for row in rows:
        profile = row.get("training_profile") or {}
        for capability in profile.get("planning_credits") or []:
            capability = str(capability or "").strip()
            if not capability:
                continue
            planning_credits.add(capability)
            try:
                row_day = iso(row.get("date"))
            except (TypeError, ValueError):
                row_day = None
            if row_day is not None:
                capability_day_indexes.setdefault(capability, set()).add(
                    (row_day - target_start).days + 1
                )
            activity_id = str(row.get("id") or "")
            if activity_id:
                planning_credit_refs.setdefault(capability, []).append(activity_id)

    for key in list(planning_credit_refs):
        planning_credit_refs[key] = sorted(set(planning_credit_refs[key]))

    fixed_enduro = is_enduro_school_date(target_start)
    completed_slot_dates = {
        str(row.get("date"))
        for row in rows
        if not (fixed_enduro and str(row.get("date")) == target_start.isoformat())
    }
    completed_day_indexes = sorted(
        {
            (iso(day_value) - target_start).days + 1
            for day_value in completed_slot_dates
            if day_value
        }
    )
    strength_rows = [row for row in rows if row.get("family") == "strength"]
    swim_rows = [row for row in rows if row.get("family") == "swim"]
    enduro_rows = [row for row in rows if row.get("family") == "enduro"]
    return {
        "strength_exposures": len(strength_rows),
        "swim_exposures": len(swim_rows),
        "enduro_exposures": len(enduro_rows),
        "completed_slot_days": len(completed_slot_dates),
        "completed_day_indexes": completed_day_indexes,
        "direct_capabilities": sorted(direct_capabilities),
        "planning_credits": sorted(planning_credits),
        "capability_refs": capability_refs,
        "planning_credit_refs": planning_credit_refs,
        "capability_day_indexes": {
            key: sorted(values)
            for key, values in sorted(capability_day_indexes.items())
        },
        "activity_refs": sorted(activity_ids),
        "evidence_note": (
            "Familjeexponeringar kommer från faktiskt registrerade aktiviteter i målveckan. "
            "Direct_capabilities kräver explicit daterad kapabilitetsevidens. Planning_credits kan dessutom "
            "komma från en durabel, entydig strukturell match mot ett närliggande planerat intent och används "
            "för att undvika redundant framtida ordination utan att påstå mer fysiologi än underlaget stödjer."
        ),
    }


def infer_recipe_key(workout, catalog):
    explicit = str((workout or {}).get("recipe_key") or "").strip()
    if explicit in (catalog.get("recipes") or {}):
        return explicit
    slot = str((workout or {}).get("microcycle_slot") or "").strip()
    for key in sorted((catalog.get("recipes") or {}), key=len, reverse=True):
        if slot == key or slot.startswith(key + "_"):
            return key
    return None


def mesocycle_history_context(meso, target_start, catalog):
    """Read up to three earlier microcycles in this block as planning memory."""
    try:
        start = iso(meso["start_date"])
    except (KeyError, TypeError, ValueError):
        return []

    current_plan = load_json(PLAN_FILE, {})
    history = []
    week_start = start
    while week_start < target_start:
        document = {}
        current_meta = current_plan.get("meta") or {}
        if current_meta.get("week_start") == week_start.isoformat():
            document = current_plan
        else:
            snapshot = load_json(WEEKS_DIR / f"{week_key(week_start)}.json", {})
            document = snapshot.get("plan") or {}

        meta = document.get("meta") or {}
        if document and (
            not meta.get("mesocycle_id")
            or meta.get("mesocycle_id") == meso.get("id")
        ):
            workouts = []
            for workout in document.get("planned_workouts") or []:
                recipe_key = infer_recipe_key(workout, catalog)
                recipe = ((catalog.get("recipes") or {}).get(recipe_key) or {})
                workouts.append(
                    {
                        "date": workout.get("date"),
                        "sport": workout.get("sport"),
                        "recipe_key": recipe_key,
                        "development_character": (
                            workout.get("development_character")
                            or recipe.get("development_character")
                            or recipe_key
                        ),
                        "baseline_option_id": workout.get("baseline_option_id"),
                        "stimuli": list(workout.get("stimuli") or []),
                        "session": workout.get("session"),
                        "completed": bool(
                            workout.get("activity_id")
                            or workout.get("activity_ids")
                            or workout.get("planning_status") == "completed"
                        ),
                    }
                )
            history.append(
                {
                    "week_start": week_start.isoformat(),
                    "microcycle_index": meta.get("microcycle_index"),
                    "workouts": workouts,
                }
            )
        week_start += timedelta(days=7)

    return history[-3:]


def fallback_microcycle(
    meso,
    policy,
    catalog,
    target_start,
    completed_context=None,
    athlete_profile=None,
    planning_date=None,
    athlete_state=None,
    starting_state=None,
):
    """Conservative composition from requirements, not from calendar fill.

    Fixed Enduro consumes a real training day. Secondary capabilities are not a
    checklist and may be omitted from an individual microcycle. The fallback
    first covers direct primary stimuli and protected swim/strength, then adds
    only a useful secondary exposure if there is a safe slot.
    """
    primaries = set(meso.get("primary_capabilities") or [])
    secondaries = set(meso.get("secondary_capabilities") or [])
    fixed_enduro = is_enduro_school_date(target_start)
    next_fixed_enduro = is_enduro_school_date(target_start + timedelta(days=7))
    completed_context = completed_context or {}
    completed_swims = int(completed_context.get("swim_exposures") or 0)
    completed_strength = int(completed_context.get("strength_exposures") or 0)
    completed_direct = set(completed_context.get("direct_capabilities") or [])
    completed_direct.update(completed_context.get("planning_credits") or [])
    profile_contract = profile_planning_contract(athlete_profile) if athlete_profile else {}
    closed_days = closed_planning_day_indexes(target_start, planning_date)
    allowed_profile_days = (
        set(profile_contract.get("available_days") or [])
        if profile_contract.get("availability_declared")
        else set(range(1, 8))
    )
    slots = []

    recipe_day_preferences = {
        "swim_aerobic_technique": [2, 4, 6, 1, 5, 3, 7] if fixed_enduro else [1, 3, 5, 2, 4, 6, 7],
        "swim_aerobic_endurance": [2, 4, 6, 5, 3, 7] if fixed_enduro else [1, 3, 5, 2, 4, 6, 7],
        "swim_aerobic_skills": [2, 4, 6, 5, 3, 7] if fixed_enduro else [1, 3, 5, 2, 4, 6, 7],
        "swim_aerobic_threshold": [2, 4, 6, 5, 3, 7] if fixed_enduro else [1, 3, 5, 2, 4, 6, 7],
        "run_threshold": [3, 4, 5, 6, 7] if fixed_enduro else [2, 3, 4, 5, 6, 7, 1],
        "run_threshold_short_reps": [3, 4, 5, 6, 7] if fixed_enduro else [2, 3, 4, 5, 6, 7, 1],
        "run_hill_quality": [5, 6, 7, 4, 3] if fixed_enduro else [4, 5, 6, 7, 3, 2, 1],
        "run_hill_continuous": [5, 6, 7, 4, 3] if fixed_enduro else [4, 5, 6, 7, 3, 2, 1],
        "run_easy_distance": (
            [6, 5, 4, 3, 7]
            if fixed_enduro and next_fixed_enduro
            else [7, 6, 5, 4, 3]
            if fixed_enduro
            else [7, 6, 5, 4, 3, 2, 1]
        ),
        "run_easy_trail": (
            [6, 5, 4, 3, 7]
            if fixed_enduro and next_fixed_enduro
            else [7, 6, 5, 4, 3]
            if fixed_enduro
            else [7, 6, 5, 4, 3, 2, 1]
        ),
        "mtb_technical": [6, 7, 4, 5, 3] if fixed_enduro else [6, 7, 4, 5, 3, 2, 1],
        "mtb_aerobic_endurance": [6, 7, 4, 5, 3] if fixed_enduro else [6, 7, 4, 5, 3, 2, 1],
        "strength_core": [5, 6, 4, 3, 7, 2] if fixed_enduro else [5, 6, 4, 3, 7, 2, 1],
    }

    def candidate_rows(day, recipe):
        return slots + [
            {
                "day_index": day,
                "recipe_key": recipe,
                "action": "consolidate",
                "rationale": "",
                "evidence_refs": [],
            }
        ]

    def add_recipe(
        recipe,
        rationale,
        *,
        action=None,
        allow_repeat=False,
        preferred_same_day=None,
    ):
        if recipe not in catalog["recipes"]:
            return False
        if not allow_repeat and any(row["recipe_key"] == recipe for row in slots):
            return True

        configured = list(recipe_day_preferences.get(recipe, range(1, 8)))
        if preferred_same_day in configured:
            configured.remove(preferred_same_day)
            configured.insert(0, preferred_same_day)

        # Prefer unused calendar days, but co-location is a first-class option.
        # A date is not a workout identity; constraints decide whether two
        # independent sessions may share it.
        occupied = {row["day_index"] for row in slots}
        candidate_days = (
            [day for day in configured if day not in occupied]
            + [day for day in configured if day in occupied]
        )
        if preferred_same_day is not None:
            candidate_days = [preferred_same_day] + [
                day for day in candidate_days if day != preferred_same_day
            ]

        for day in candidate_days:
            if day in closed_days:
                continue
            if day not in allowed_profile_days:
                continue
            if fixed_enduro and day == 1:
                continue
            conflicts = microcycle_layout_failures(
                candidate_rows(day, recipe), catalog, target_start, athlete_profile=athlete_profile
            )
            if conflicts:
                continue
            caps = recipe_capabilities(catalog["recipes"][recipe])
            slots.append(
                {
                    "day_index": day,
                    "recipe_key": recipe,
                    "action": action or ("consolidate" if caps.intersection(primaries) else "establish"),
                    "rationale": rationale,
                    "evidence_refs": [
                        "mesocycle.primary_capabilities"
                        if caps.intersection(primaries)
                        else "planning_policy.microcycle_policy"
                    ],
                }
            )
            return True
        return False

    blueprint = development_blueprint_for_week(meso, policy, catalog, target_start) or {}
    blueprint_primary = {
        str(item.get("capability") or ""): str(item.get("recipe_key") or "")
        for item in (blueprint.get("planned_variants") or [])
        if isinstance(item, dict)
    }

    # Low-mechanical swim is the conservative default immediately after fixed
    # Enduro, but choose this microcycle's planned swim character when it is a
    # low-mechanical aerobic/technical recipe.
    if fixed_enduro and {"swim_aerobic", "swim_technique"}.intersection(primaries):
        planned_swim = next(
            (
                str(item.get("recipe_key") or "")
                for item in (blueprint.get("planned_variants") or [])
                if isinstance(item, dict)
                and (catalog.get("recipes") or {}).get(str(item.get("recipe_key") or ""), {}).get("sport") == "swim"
                and "swim_threshold" not in recipe_capabilities(
                    (catalog.get("recipes") or {}).get(str(item.get("recipe_key") or ""), {})
                )
            ),
            "swim_aerobic_technique",
        )
        add_recipe(
            planned_swim if planned_swim in catalog["recipes"] else "swim_aerobic_technique",
            "Lågmekanisk simexponering dagen efter fast enduro följer blockets planerade passkaraktär utan att anta att benen är redo för ny benkvalitet.",
        )

    # Cover each primary with the mesocycle blueprint's intended recipe character.
    for cap in meso.get("primary_capabilities") or []:
        if cap in completed_direct:
            continue
        direct_recipe = blueprint_primary.get(cap) or CAPABILITY_TO_RECIPE.get(cap)
        if not direct_recipe or direct_recipe not in catalog["recipes"]:
            continue
        if any(
            cap in recipe_capabilities(catalog["recipes"][row["recipe_key"]])
            and row["recipe_key"] not in SUPPORT_ONLY_RECIPES
            for row in slots
        ):
            continue
        add_recipe(
            direct_recipe,
            f"Realiserar mesocykelns primära kapacitet {cap} med säker separation från annan benbelastning.",
        )

    # Credit already completed swim and strength before adding future protected work.
    swim_count = completed_swims + sum(
        "swim_aerobic" in recipe_capabilities(catalog["recipes"][row["recipe_key"]])
        for row in slots
    )
    required_swims = int(policy["microcycle_policy"].get("normal_swim_exposures", 2))
    planned_strength = any(
        "strength_core" in recipe_capabilities(catalog["recipes"][row["recipe_key"]])
        for row in slots
    )
    strength_needed = (
        policy["microcycle_policy"].get("protect_strength_core_each_microcycle")
        and completed_strength < 1
        and not planned_strength
    )
    latest_swim_day = None
    while swim_count < required_swims:
        before = len(slots)
        already_planned = {row["recipe_key"] for row in slots}
        blueprint_swims = [
            str(item.get("recipe_key") or "")
            for item in (blueprint.get("planned_variants") or [])
            if isinstance(item, dict)
            and (catalog.get("recipes") or {}).get(str(item.get("recipe_key") or ""), {}).get("sport") == "swim"
        ]
        candidates = [
            key
            for key in (
                blueprint_swims
                + ["swim_aerobic_endurance", "swim_aerobic_skills", "swim_aerobic_technique", "swim_aerobic_threshold"]
            )
            if key in catalog["recipes"] and key not in already_planned
        ]
        if not candidates:
            candidates = [
                key
                for key in ("swim_aerobic_technique", "swim_aerobic_endurance")
                if key in catalog["recipes"]
            ]

        added = False
        for recipe_key in candidates:
            if add_recipe(
                recipe_key,
                (
                    "Lägg en självständig simexponering med en annan utvecklingskaraktär än veckans "
                    "övriga simpass när katalog och belastningsordning stödjer det."
                ),
                action="establish",
                allow_repeat=False,
            ):
                added = True
                break
        if not added:
            break
        swim_count += 1
        if len(slots) > before:
            latest_swim_day = slots[-1]["day_index"]

    if strength_needed:
        add_recipe(
            "strength_core",
            "Skydda styrka/core som ett självständigt pass; samlokalisera med simning endast när mikrocykelns belastningsordning motiverar det.",
            action="establish",
            preferred_same_day=(
                latest_swim_day
                if profile_contract.get("double_sessions") == "normal"
                else None
            ),
        )

    # A race-relevant easy-distance exposure is useful when it fits safely, but
    # other secondary capabilities are deliberately not all forced into the week.
    secondary_added = False
    planned_support = next(
        (
            str(item.get("recipe_key") or "")
            for item in (blueprint.get("supporting_candidates") or [])
            if isinstance(item, dict)
            and str(item.get("recipe_key") or "") in catalog["recipes"]
        ),
        "",
    )
    if (
        ("run_easy_distance" in secondaries or "run_easy_distance" in primaries)
        and "run_easy_distance" not in completed_direct
    ):
        run_support = next(
            (
                str(item.get("recipe_key") or "")
                for item in (blueprint.get("supporting_candidates") or [])
                if isinstance(item, dict)
                and item.get("capability") == "run_easy_distance"
                and str(item.get("recipe_key") or "") in catalog["recipes"]
            ),
            "run_easy_distance",
        )
        secondary_added = add_recipe(
            run_support,
            "Behåll lugn löptålighet med separation från löpkvalitet. Blueprint får variera passkaraktären men skapar inte en extra belastningsexponering.",
            action="consolidate",
        )
    elif planned_support and not recipe_capabilities(
        catalog["recipes"][planned_support]
    ).intersection(completed_direct):
        secondary_added = add_recipe(
            planned_support,
            "Blockets preliminära grundplan föreslår denna stödjande passkaraktär; den tas bara med när ingen redan planerad exponering fyller samma stödroll och belastningsordningen tillåter.",
            action="consolidate",
        )

    # Add at most one secondary exposure in total. A free slot is not a reason
    # to force MTB/hills into a week that already contains race-relevant
    # secondary long-run work plus fixed Enduro.
    if not secondary_added:
        for cap in ("run_hill_quality", "mtb_technical", "mtb_aerobic"):
            if cap not in secondaries or cap in completed_direct:
                continue
            recipe = CAPABILITY_TO_RECIPE.get(cap)
            if recipe and add_recipe(
                recipe,
                f"Vald sekundär exponering för {cap}; övriga sekundära kapaciteter behöver inte täckas varje mikrocykel.",
                action="consolidate",
            ):
                break

    result = {
        "rationale": (
            "Deterministisk reservkomposition som täcker primära stimuli och skyddad kapacitet, "
            "respekterar fast enduro och lämnar återhämtningsutrymme i stället för att fylla kalendern."
        ),
        "slots": sorted(slots, key=lambda row: row["day_index"]),
    }
    if athlete_state is not None:
        result = align_fallback_progression_with_block_intent(
            result,
            meso,
            policy,
            catalog,
            athlete_state,
            target_start,
            starting_state=starting_state,
        )
    return result


def build_forward_planning_horizon(
    meso,
    policy,
    catalog,
    athlete_state,
    anchor_week_start,
    *,
    starting_state=None,
    weeks=5,
):
    """Build a rolling future planning contract with declining commitment.

    Weeks that still belong to the active mesocycle get a provisional
    day-level microcycle projection. Weeks beyond the active mesocycle become a
    block sketch with explicit decision gates instead of empty calendar space or
    invented exact sessions.
    """
    if isinstance(anchor_week_start, str):
        anchor_week_start = iso(anchor_week_start)
    try:
        meso_end = iso(meso["end_date"])
    except (KeyError, TypeError, ValueError):
        return []

    blueprints = {
        str(row.get("week_start") or ""): row
        for row in build_development_blueprint(
            meso,
            policy,
            catalog,
            athlete_state=athlete_state,
            starting_state=starting_state,
        )
        if isinstance(row, dict)
    }
    capability_states = (
        ((athlete_state.get("capability_states") or {}).get("by_capability") or {})
    )
    primary = list(meso.get("primary_capabilities") or [])
    secondary = list(meso.get("secondary_capabilities") or [])
    recipes = catalog.get("recipes") or {}
    rows = []

    def variant_preview(blueprint, recipe_key):
        variants = [
            item
            for group in ("planned_variants", "supporting_candidates", "protected_variants")
            for item in (blueprint.get(group) or [])
            if isinstance(item, dict) and item.get("recipe_key") == recipe_key
        ]
        return variants[0] if variants else {}

    def recipe_label(recipe_key):
        recipe = recipes.get(recipe_key) or {}
        return str(
            recipe.get("blueprint_label")
            or ((recipe.get("options") or [{}])[0].get("session"))
            or recipe_key
        )

    for offset in range(1, int(weeks) + 1):
        week_start = anchor_week_start + timedelta(days=7 * offset)
        week_end = week_start + timedelta(days=6)

        if week_start <= meso_end:
            blueprint = blueprints.get(week_start.isoformat()) or {}
            projected = fallback_microcycle(
                meso,
                policy,
                catalog,
                week_start,
                completed_context={},
                athlete_state=athlete_state,
                starting_state=starting_state,
            )
            slots = []
            if is_enduro_school_date(week_start):
                slots.append(
                    {
                        "day_index": 1,
                        "role": "external_fixed",
                        "sport": "enduro",
                        "recipe_key": "",
                        "label": "Enduroskola · fast tillfälle",
                        "progression_intent": "fixed_external_load",
                        "baseline_session": "",
                        "conditional_target_session": "",
                    }
                )

            for slot in projected.get("slots") or []:
                recipe_key = str(slot.get("recipe_key") or "")
                recipe = recipes.get(recipe_key) or {}
                variant = variant_preview(blueprint, recipe_key)
                progression_intent = str(
                    variant.get("progression_intent")
                    or (
                        "progress_if_ready"
                        if slot.get("action") == "progress"
                        else "consolidate"
                        if slot.get("action") == "consolidate"
                        else "establish"
                    )
                )
                slots.append(
                    {
                        "day_index": int(slot.get("day_index") or 0),
                        "role": str(variant.get("role") or recipe.get("priority_role") or "support"),
                        "sport": str(recipe.get("sport") or ""),
                        "recipe_key": recipe_key,
                        "label": str(variant.get("label") or recipe_label(recipe_key)),
                        "progression_intent": progression_intent,
                        "baseline_session": str(variant.get("baseline_session") or ""),
                        "conditional_target_session": str(
                            variant.get("conditional_target_session") or ""
                        ),
                    }
                )

            rows.append(
                {
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    "planning_level": "preliminary",
                    "planning_label": "Preliminär",
                    "day_precision": "provisional",
                    "block_intent": str(blueprint.get("block_intent") or ""),
                    "title": (
                        f"Preliminär mikrocykel {blueprint.get('microcycle_index')} "
                        f"av {meso.get('duration_weeks')}"
                    ),
                    "slots": sorted(
                        slots,
                        key=lambda item: (
                            int(item.get("day_index") or 99),
                            str(item.get("recipe_key") or item.get("label") or ""),
                        ),
                    ),
                    "decision_gate": (
                        "Exakta dagar och doser får ändras av faktisk belastning och respons. "
                        "Passkaraktär och blockriktning är den planerade utgångspunkten."
                    ),
                    "source": "active_mesocycle_projection",
                }
            )
            continue

        beyond_index = max(1, ((week_start - meso_end).days + 6) // 7)
        capability_directions = []
        for key in primary:
            state = capability_states.get(key) or {}
            ready = state.get("progression_ready") is True
            evidence_state = str(state.get("evidence_state") or "missing")
            if ready:
                direction = (
                    "Om blockreview bekräftar fortsatt absorption: kandidat för nästa "
                    "förgodkända steg eller ny progressionsaxel."
                )
            elif evidence_state == "missing":
                direction = (
                    "Nästa block måste först etablera/verifiera kapaciteten innan "
                    "belastningsprogression kan beslutas."
                )
            else:
                direction = (
                    "Fortsätt eller konsolidera tills blockreview visar stöd för "
                    "progression eller byte av utvecklingsaxel."
                )
            family = [
                recipe_label(recipe_key)
                for recipe_key in capability_recipe_family(key)
                if recipe_key in recipes
            ]
            capability_directions.append(
                {
                    "capability": key,
                    "label": capability_label(key),
                    "direction": direction,
                    "candidate_recipe_characters": family[:3],
                    "progression_ready_now": ready,
                    "evidence_state_now": evidence_state,
                }
            )

        support_candidates = []
        if secondary:
            start_index = (beyond_index - 1) % len(secondary)
            ordered = secondary[start_index:] + secondary[:start_index]
            for key in ordered[:2]:
                family = [
                    recipe_label(recipe_key)
                    for recipe_key in capability_recipe_family(key)
                    if recipe_key in recipes
                ]
                support_candidates.append(
                    {
                        "capability": key,
                        "label": capability_label(key),
                        "candidate_recipe_characters": family[:2],
                    }
                )

        rows.append(
            {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "planning_level": "block_sketch",
                "planning_label": "Blockskiss",
                "day_precision": "none",
                "block_intent": "review" if beyond_index == 1 else "conditional_build",
                "title": (
                    "Blockreview · besluta nästa riktning"
                    if beyond_index == 1
                    else "Nästa block · villkorad riktning"
                ),
                "capability_directions": capability_directions,
                "support_candidates": support_candidates,
                "protected_capabilities": [
                    {
                        "capability": key,
                        "label": capability_label(key),
                    }
                    for key in FIXED_PROTECTED_CAPACITY
                    if key in CAPABILITY_REGISTRY
                    and key not in primary
                    and key not in secondary
                ],
                "decision_gate": (
                    f"Ny mesocykel beslutas tidigast vid checkpoint {meso.get('evaluation_date')}. "
                    "Skissen visar vilka kapaciteter och passfamiljer som står i kön; den "
                    "låser inte dagar, doser eller ett fysiologiskt utfall innan review."
                ),
                "source": "post_mesocycle_conditional_sketch",
            }
        )

    return rows


def microcycle_layout_failures(
    rows, catalog, target_start, athlete_profile=None, planning_date=None
):
    """Hard scheduling guards for known planned load adjacency.

    Calendar dates group workouts; they are not unique workout slots. Guards
    therefore evaluate all recipes on each date without collapsing co-located
    sessions.
    """
    failures = []
    fixed_enduro = is_enduro_school_date(target_start)
    closed_days = closed_planning_day_indexes(target_start, planning_date)
    by_day = {}
    for row in rows:
        if (
            isinstance(row, dict)
            and isinstance(row.get("day_index"), int)
            and row.get("recipe_key") in catalog["recipes"]
        ):
            by_day.setdefault(row["day_index"], []).append(row)

    def recipes_on(day):
        return {
            row["recipe_key"]
            for row in by_day.get(day, [])
        }

    for day in sorted(set(by_day).intersection(closed_days)):
        failures.append(
            f"dag {day} har redan passerat i den aktiva mikrocykeln och får inte få ett nytt planerat pass"
        )

    if fixed_enduro and recipes_on(2).intersection(DAY_AFTER_ENDURO_BLOCKED_RECIPES):
        blocked = sorted(recipes_on(2).intersection(DAY_AFTER_ENDURO_BLOCKED_RECIPES))
        failures.append(
            f"{', '.join(blocked)} får inte ligga direkt dagen efter fast enduro när faktisk benbelastning ännu är okänd"
        )

    next_fixed_enduro = is_enduro_school_date(target_start + timedelta(days=7))
    if next_fixed_enduro:
        blocked_before_enduro = recipes_on(7).intersection(
            RUN_STRESS_RECIPES | {"mtb_technical", "strength_core"}
        )
        if blocked_before_enduro:
            failures.append(
                "tung benbelastning får inte planeras på söndagen direkt före nästa fasta enduro: "
                + ", ".join(sorted(blocked_before_enduro))
            )

    run_days = sorted(
        day for day in by_day if recipes_on(day).intersection(RUN_STRESS_RECIPES)
    )
    for previous, current in zip(run_days, run_days[1:]):
        if current - previous == 1:
            failures.append(
                "löptröskel/backkvalitet/lång löpdistans får inte staplas på två på varandra följande dagar"
            )
            break

    for day in by_day:
        if "run_easy_distance" not in recipes_on(day):
            continue
        for neighbor in (day - 1, day + 1):
            if "mtb_technical" in recipes_on(neighbor):
                failures.append(
                    "lång löpdistans får inte ligga direkt intill MTB/XC; den sekundära cykelexponeringen ska utgå eller flyttas"
                )
                break

    for day in by_day:
        if not recipes_on(day).intersection({"run_threshold", "run_hill_quality"}):
            continue
        for neighbor in (day - 1, day + 1):
            if "mtb_technical" in recipes_on(neighbor):
                failures.append(
                    "MTB/XC får inte ligga direkt intill löpkvalitet; sekundär cykelbelastning ska inte kompromissa primärt löpstimulus"
                )
                break

    profile_contract = profile_planning_contract(athlete_profile) if athlete_profile else {}
    unavailable = set(profile_contract.get("unavailable_days") or [])
    for day in sorted(set(by_day).intersection(unavailable)):
        failures.append(
            f"dag {day} innehåller planerad träning trots att atleten har markerat dagen som otillgänglig"
        )

    occupied = set(by_day)
    if fixed_enduro:
        occupied.add(1)

    double_days = sorted(day for day, items in by_day.items() if len(items) > 1)
    double_preference = profile_contract.get("double_sessions")
    if double_days and double_preference == "avoid":
        failures.append(
            "dubbelpass planeras trots att atleten har valt att dubbelpass helst ska undvikas"
        )
    elif double_days and double_preference == "sometimes":
        available_days = (
            set(profile_contract.get("available_days") or [])
            if profile_contract.get("availability_declared")
            else set(range(1, 8))
        )
        if fixed_enduro:
            available_days.add(1)
        unused_available = sorted(available_days - occupied)
        if unused_available:
            failures.append(
                "dubbelpass klustras samtidigt som en deklarerat tillgänglig träningsdag lämnas oanvänd; "
                "fördela befintliga stimuli innan dubbelpass används"
            )
    return failures


def microcycle_guard_failures(
    result,
    meso,
    policy,
    catalog,
    target_start,
    completed_context=None,
    athlete_profile=None,
    planning_date=None,
):
    """Return explicit structural violations without silently repairing the model output."""
    recipes = catalog["recipes"]
    slots = result.get("slots") or []
    failures = []
    valid_rows = []
    fixed_enduro = is_enduro_school_date(target_start)
    completed_context = completed_context or {}
    completed_swims = int(completed_context.get("swim_exposures") or 0)
    completed_strength = int(completed_context.get("strength_exposures") or 0)
    completed_slot_days = int(completed_context.get("completed_slot_days") or 0)
    completed_direct = set(completed_context.get("direct_capabilities") or [])
    completed_direct.update(completed_context.get("planning_credits") or [])

    for index, row in enumerate(slots):
        if not isinstance(row, dict):
            failures.append(f"slot[{index}] är inte ett objekt")
            continue
        day = row.get("day_index")
        recipe_key = row.get("recipe_key")
        if not isinstance(day, int) or not 1 <= day <= 7:
            failures.append(f"slot[{index}] har ogiltig day_index")
            continue
        if fixed_enduro and day == 1:
            failures.append("dag 1 är blockerad av fast endurobelastning")
            continue
        if recipe_key not in recipes:
            failures.append(f"slot[{index}] använder okänt recipe_key {recipe_key!r}")
            continue
        valid_rows.append(row)

    minimum = max(0, 4 - completed_slot_days)
    if len(valid_rows) < minimum:
        failures.append(f"för få giltiga träningsslots: {len(valid_rows)} < {minimum}")

    for failure in microcycle_layout_failures(
        valid_rows,
        catalog,
        target_start,
        athlete_profile=athlete_profile,
        planning_date=planning_date,
    ):
        if failure not in failures:
            failures.append(failure)

    profile_contract = profile_planning_contract(athlete_profile) if athlete_profile else {}
    active_days = {
        int(day)
        for day in (completed_context.get("completed_day_indexes") or [])
        if isinstance(day, int) and 1 <= day <= 7
    }
    active_days.update(row["day_index"] for row in valid_rows)
    if fixed_enduro:
        active_days.add(1)

    min_active = profile_contract.get("min_active_days")
    max_active = profile_contract.get("max_active_days")
    distributable_exposures = (
        len(valid_rows)
        + len(set(completed_context.get("completed_day_indexes") or []))
        + (1 if fixed_enduro else 0)
    )
    if isinstance(max_active, int) and len(active_days) > max_active:
        failures.append(
            f"planen använder {len(active_days)} aktiva dagar, över atletens deklarerade normala max {max_active}"
        )
    if (
        isinstance(min_active, int)
        and len(active_days) < min_active
        and distributable_exposures >= min_active
    ):
        failures.append(
            f"planen klustrar till {len(active_days)} aktiva dagar trots att befintliga exponeringar kan "
            f"fördelas över atletens deklarerade normala spann från {min_active} dagar"
        )

    primaries = set(meso.get("primary_capabilities") or [])
    secondaries = set(meso.get("secondary_capabilities") or [])
    block_context = mesocycle_block_context(meso, target_start, policy)
    if (
        block_context.get("block_intent") == "develop"
        and policy["microcycle_policy"].get(
            "require_distinct_development_character_in_develop_microcycles"
        )
    ):
        recipe_counts = {}
        for row in valid_rows:
            recipe_key = row["recipe_key"]
            caps = recipe_capabilities(recipes[recipe_key])
            if recipe_key in SUPPORT_ONLY_RECIPES or not caps.intersection(primaries):
                continue
            recipe_counts[recipe_key] = recipe_counts.get(recipe_key, 0) + 1
        for recipe_key, count in recipe_counts.items():
            if count > 1:
                failures.append(
                    f"{recipe_key} upprepas {count} gånger i en develop-mikrocykel; "
                    "samma utvecklingsrecept får inte dupliceras mekaniskt"
                )

    blueprint = development_blueprint_for_week(
        meso, policy, catalog, target_start
    ) or {}
    expected_primary_recipe_keys = {
        str(item.get("recipe_key") or "")
        for item in (blueprint.get("planned_variants") or [])
        if isinstance(item, dict) and str(item.get("recipe_key") or "") in recipes
    }
    if (
        policy["microcycle_policy"].get("require_mesocycle_blueprint_alignment")
        and expected_primary_recipe_keys
    ):
        for capability in sorted(primaries - completed_direct):
            matching = [
                row
                for row in valid_rows
                if row["recipe_key"] in expected_primary_recipe_keys
                and capability in recipe_capabilities(recipes[row["recipe_key"]])
            ]
            if not matching:
                expected = sorted(
                    key
                    for key in expected_primary_recipe_keys
                    if capability in recipe_capabilities(recipes[key])
                )
                if expected:
                    failures.append(
                        f"primär kapacitet {capability} avviker från mesocykelns planerade passkaraktär; "
                        f"förväntat recept ur {', '.join(expected)}"
                    )

    direct_primary_caps = set()
    swim_exposures = 0
    strength_exposures = 0
    run_quality = 0
    secondary_sessions = 0

    for row in valid_rows:
        recipe_key = row["recipe_key"]
        caps = recipe_capabilities(recipes[recipe_key])
        if recipe_key not in SUPPORT_ONLY_RECIPES:
            direct_primary_caps |= caps
        if "swim_aerobic" in caps:
            swim_exposures += 1
        if "strength_core" in caps:
            strength_exposures += 1
        if {"run_threshold", "run_hill_quality"}.intersection(caps):
            run_quality += 1
        if caps.intersection(secondaries) and not caps.intersection(primaries):
            secondary_sessions += 1

        if row.get("action") == "progress" and (
            not caps.intersection(primaries) or recipe_key in SUPPORT_ONLY_RECIPES
        ):
            failures.append(
                f"{recipe_key} får inte progressas eftersom receptet inte realiserar ett direkt primärt stimulus"
            )

        completed_overlap = caps.intersection(primaries).intersection(completed_direct)
        if recipe_key not in SUPPORT_ONLY_RECIPES and completed_overlap:
            failures.append(
                f"{recipe_key} är redundant: primärt stimulus är redan faktiskt genomfört i mikrocykeln "
                + ", ".join(sorted(completed_overlap))
            )
        if (
            completed_strength >= 1
            and recipe_key == "strength_core"
            and not {"strength_unilateral", "strength_core"}.intersection(primaries)
        ):
            failures.append(
                f"{recipe_key} är redundant: styrka/core är redan faktiskt genomförd i mikrocykeln"
            )

    missing_primary = sorted(primaries - direct_primary_caps - completed_direct)
    if missing_primary:
        failures.append(
            "primära kapaciteter saknar direkt recept: " + ", ".join(missing_primary)
        )

    required_swims = int(policy["microcycle_policy"].get("normal_swim_exposures", 2))
    total_swims = completed_swims + swim_exposures
    if total_swims < required_swims:
        failures.append(
            f"för få simexponeringar inklusive faktiskt genomförda: {total_swims} < {required_swims}"
        )

    required_strength = (
        1 if policy["microcycle_policy"].get("protect_strength_core_each_microcycle") else 0
    )
    total_strength = completed_strength + strength_exposures
    if total_strength < required_strength:
        failures.append(
            f"för få styrka/core-exponeringar inklusive faktiskt genomförda: {total_strength} < {required_strength}"
        )

    max_run_quality = int(policy["microcycle_policy"].get("max_run_quality_exposures", 2))
    completed_run_quality = len(completed_direct.intersection({"run_threshold", "run_hill_quality"}))
    # A future fixed Enduro session is real but as-yet unobserved lower-body load.
    # Reserve one quality-capacity slot until that session has actually happened.
    # Once completed, the near-term planner can use the observed outcome instead
    # of permanently treating Enduro as equivalent to a run-quality workout.
    future_fixed_enduro_reserve = (
        1
        if fixed_enduro and int(completed_context.get("enduro_exposures") or 0) == 0
        else 0
    )
    total_run_quality = completed_run_quality + run_quality + future_fixed_enduro_reserve
    if total_run_quality > max_run_quality:
        failures.append(
            "för hög förhandskoncentration av benkvalitet: "
            f"{completed_run_quality + run_quality} löpkvalitet + "
            f"{future_fixed_enduro_reserve} reserverad fast enduro > {max_run_quality}. "
            "Framtida enduro ska räknas som verklig belastning tills utfallet är känt."
        )

    completed_secondary = completed_direct.intersection(secondaries)
    # "Sekundärt stöd" är en funktion i mikrocykeln, inte en taxonomisk
    # skyldighet att alltid lägga till ett recept klassat som secondary.
    # Lugn distans kan redan bära den stödjande uthållighetsrollen även när
    # mesocykeln har gjort run_easy_distance primär. Då ska vi inte tvinga in
    # extra back-/MTB-belastning bara för att uppfylla en etikett.
    planned_supporting_distance = any(
        "run_easy_distance" in recipe_capabilities(recipes[row["recipe_key"]])
        for row in valid_rows
    )
    completed_supporting_distance = "run_easy_distance" in completed_direct
    has_supporting_breadth = bool(
        completed_secondary
        or secondary_sessions >= 1
        or planned_supporting_distance
        or completed_supporting_distance
    )
    if (
        block_context.get("block_intent") == "develop"
        and secondaries
        and not has_supporting_breadth
    ):
        failures.append(
            "develop-mikrocykeln saknar stödjande breddsexponering trots att sekundära kapaciteter är deklarerade; "
            "planera ett absorberbart stödpass i stället för att lämna resten av veckan mekaniskt tom"
        )
    if future_fixed_enduro_reserve and secondary_sessions > 1:
        failures.append(
            "framtida fast enduro begränsar sekundär belastning till ett planerat stödpass tills utfallet är känt"
        )

    return failures


def validate_and_normalize_micro(
    result,
    meso,
    policy,
    catalog,
    target_start,
    completed_context=None,
    athlete_profile=None,
    planning_date=None,
):
    recipes = catalog["recipes"]
    cleaned = []
    primaries = set(meso.get("primary_capabilities") or [])
    fixed_enduro = is_enduro_school_date(target_start)

    for row in result.get("slots") or []:
        day = row.get("day_index")
        recipe_key = row.get("recipe_key")
        if not isinstance(day, int) or not 1 <= day <= 7:
            continue
        if fixed_enduro and day == 1:
            continue
        if recipe_key not in recipes:
            continue
        action = row.get("action")
        if action not in {"establish", "progress", "consolidate", "reduce"}:
            action = "consolidate"
        caps = recipe_capabilities(recipes[recipe_key])
        if action == "progress" and (
            not caps.intersection(primaries) or recipe_key in SUPPORT_ONLY_RECIPES
        ):
            action = "consolidate"
        cleaned.append(
            {
                "day_index": day,
                "recipe_key": recipe_key,
                "action": action,
                "rationale": str(row.get("rationale") or "").strip() or "Realiserar mesocykelns stimulus.",
                "evidence_refs": [str(x) for x in (row.get("evidence_refs") or []) if str(x).strip()][:6],
            }
        )

    used_caps = set()
    direct_primary_caps = set()
    swim_exposures = 0
    strength_exposures = 0
    run_quality = 0
    for row in cleaned:
        caps = recipe_capabilities(recipes[row["recipe_key"]])
        used_caps |= caps
        if row["recipe_key"] not in SUPPORT_ONLY_RECIPES:
            direct_primary_caps |= caps
        if "swim_aerobic" in caps:
            swim_exposures += 1
        if "strength_core" in caps:
            strength_exposures += 1
        if {"run_threshold", "run_hill_quality"}.intersection(caps):
            run_quality += 1

    valid = not microcycle_guard_failures(
        {"rationale": result.get("rationale"), "slots": cleaned},
        meso,
        policy,
        catalog,
        target_start,
        completed_context=completed_context,
        athlete_profile=athlete_profile,
        planning_date=planning_date,
    )
    if not valid:
        return fallback_microcycle(
            meso,
            policy,
            catalog,
            target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
            planning_date=planning_date,
        ), False
    return {"rationale": str(result.get("rationale") or "").strip(), "slots": sorted(cleaned, key=lambda x: x["day_index"])}, True


def response_profile_for_recipe(recipe_key, athlete_state):
    capability = RECIPE_TO_RESPONSE_CAPABILITY.get(recipe_key)
    if not capability:
        return None
    state_profile = (
        ((athlete_state.get("capability_states") or {}).get("by_capability") or {})
        .get(capability)
    )
    if isinstance(state_profile, dict):
        return state_profile
    return (
        ((athlete_state.get("dose_response") or {}).get("by_capability") or {})
        .get(capability)
    )


def normalize_progress_actions_from_absorption(microcycle, athlete_state):
    """Fail closed: requested progression becomes consolidation without absorbed evidence."""
    normalized = deepcopy(microcycle)
    for slot in normalized.get("slots") or []:
        if slot.get("action") != "progress":
            continue
        recipe_key = str(slot.get("recipe_key") or "")
        profile = response_profile_for_recipe(recipe_key, athlete_state)
        if profile and profile.get("progression_ready") is True:
            continue

        reason = (
            str((profile or {}).get("progression_reason") or "").strip()
            or "Absorberad dos med stödjande återkoppling saknas."
        )
        slot["action"] = "consolidate"
        slot["rationale"] = (
            str(slot.get("rationale") or "").rstrip()
            + " Automatisk progression neutraliseras: "
            + reason
        ).strip()
        refs = list(slot.get("evidence_refs") or [])
        marker = "athlete_state.dose_response: progression_ready=false"
        if marker not in refs:
            refs.append(marker)
        slot["evidence_refs"] = refs
    return normalized


def align_fallback_progression_with_block_intent(
    microcycle,
    meso,
    policy,
    catalog,
    athlete_state,
    target_start,
    *,
    starting_state=None,
):
    """Make deterministic fallback respect the mesocycle wave without guessing load.

    A develop microcycle may advance at most one primary dose and only when the
    canonical dose-response model explicitly marks that recipe progression-ready
    and the recipe catalog already contains a higher approved step. Otherwise
    the fallback keeps the dose and records the factual hold reason.
    """
    result = deepcopy(microcycle)
    block_context = mesocycle_block_context(meso, target_start, policy)
    if block_context.get("block_intent") != "develop":
        return result

    recipes = catalog.get("recipes") or {}
    primary_order = {
        key: index
        for index, key in enumerate(meso.get("primary_capabilities") or [])
    }

    candidates = []
    for slot in result.get("slots") or []:
        recipe_key = str(slot.get("recipe_key") or "")
        recipe = recipes.get(recipe_key) or {}
        caps = recipe_capabilities(recipe)
        matched = [
            cap for cap in caps
            if cap in primary_order and recipe_key not in SUPPORT_ONLY_RECIPES
        ]
        if not matched:
            continue
        rank = min(primary_order[cap] for cap in matched)
        candidates.append((rank, int(slot.get("day_index") or 99), slot, recipe_key, recipe))

    candidates.sort(key=lambda item: (item[0], item[1], item[3]))

    # Idempotence matters because a deterministic fallback can pass through
    # normalization more than once. Never create a second progression.
    if any(slot.get("action") == "progress" for _, _, slot, _, _ in candidates):
        return result

    # One progression axis at a time is the conservative deterministic default.
    for _, _, slot, recipe_key, recipe in candidates:
        profile = response_profile_for_recipe(recipe_key, athlete_state)
        if not (profile and profile.get("progression_ready") is True):
            continue
        _, _, _, relation, evidence = choose_option(
            recipe_key,
            recipe,
            "progress",
            athlete_state,
            starting_state,
        )
        if relation != "progress":
            continue
        slot["action"] = "progress"
        slot["rationale"] = (
            str(slot.get("rationale") or "").rstrip()
            + " Develop-vecka: ett primärt stimulus progressas exakt ett förgodkänt "
              "katalogsteg eftersom dose_response anger progression_ready=true."
        ).strip()
        refs = list(slot.get("evidence_refs") or [])
        marker = f"athlete_state.dose_response:{recipe_key}:progression_ready=true"
        if marker not in refs:
            refs.append(marker)
        slot["evidence_refs"] = refs[:6]
        return result

    # No safe catalog progression is available. Keep the planned primary work,
    # but make the hold rationale inspectable rather than silently static.
    for _, _, slot, recipe_key, recipe in candidates:
        if slot.get("action") not in {"consolidate", "establish"}:
            continue
        profile = response_profile_for_recipe(recipe_key, athlete_state)
        reason = str((profile or {}).get("progression_reason") or "").strip()
        if profile and profile.get("progression_ready") is True:
            _, _, _, relation, evidence = choose_option(
                recipe_key,
                recipe,
                "progress",
                athlete_state,
                starting_state,
            )
            if relation == "hold":
                reason = "Ingen högre förgodkänd dos finns i receptkatalogen."
        if not reason:
            reason = "Verifierat stöd för progression saknas."
        refs = list(slot.get("evidence_refs") or [])
        marker = f"athlete_state.dose_response:{recipe_key}:hold"
        if marker in refs:
            continue
        slot["rationale"] = (
            str(slot.get("rationale") or "").rstrip()
            + " Develop-vecka konsolideras för detta primära stimulus: "
            + reason
        ).strip()
        refs.append(marker)
        slot["evidence_refs"] = refs[:6]

    return result


def build_microcycle_source_payload(
    meso,
    goal,
    policy,
    catalog,
    athlete_state,
    target_start,
    athlete_profile=None,
    starting_state=None,
    completed_context=None,
    planning_date=None,
):
    completed_context = completed_context or completed_microcycle_context(
        athlete_state, target_start
    )
    competition_context = build_competition_context(
        goal,
        target_start,
        policy.get("event_horizon_policy"),
    )
    declared_profile = planner_profile_view(athlete_profile)
    profile_contract = (
        profile_planning_contract(athlete_profile) if athlete_profile else {}
    )
    closed_days = sorted(closed_planning_day_indexes(target_start, planning_date))
    return {
        "week_start": target_start.isoformat(),
        "planning_date": planning_date.isoformat() if isinstance(planning_date, date) else None,
        "declared_athlete_profile": declared_profile,
        "declared_profile_contract": profile_contract,
        "confirmed_starting_state": planner_starting_state_view(starting_state),
        "competition_context": competition_context,
        "completed_microcycle_context": completed_context,
        "block_context": mesocycle_block_context(meso, target_start, policy),
        "development_blueprint": build_development_blueprint(
            meso,
            policy,
            catalog,
            athlete_state=athlete_state,
            starting_state=starting_state,
        ),
        "current_microcycle_blueprint": development_blueprint_for_week(
            meso,
            policy,
            catalog,
            target_start,
            athlete_state=athlete_state,
            starting_state=starting_state,
        ),
        "mesocycle_history": mesocycle_history_context(
            meso, target_start, catalog
        ),
        "fixed_enduro_day_1": is_enduro_school_date(target_start),
        "goal": {
            "goal": goal.get("goal"),
            "development_goals": goal.get("development_goals"),
            "performance_goals": goal.get("performance_goals"),
            "current_phase": goal.get("current_phase"),
            "next_steps": goal.get("next_steps"),
        },
        "goal_set": planning_goal_set(goal),
        "multi_goal_policy": policy.get("multi_goal_policy"),
        "mesocycle": meso,
        "microcycle_policy": policy.get("microcycle_policy"),
        "decision_guards": policy.get("decision_guards"),
        "athlete_state": sanitize_athlete_state(athlete_state),
        "recipe_profiles": {
            key: {
                "stimuli": sorted(recipe_capabilities(value)),
                "load_dimensions": list(value.get("load_dimensions") or []),
                "development_focus": value.get("development_focus"),
                "development_character": value.get("development_character") or key,
                "option_ids": [
                    item.get("id") for item in (value.get("options") or [])
                ],
            }
            for key, value in catalog["recipes"].items()
        },
        "hard_requirements": {
            "cover_all_primary_capabilities_directly": True,
            "normal_swim_exposures": int(
                policy["microcycle_policy"].get("normal_swim_exposures", 2)
            ),
            "completed_swim_exposures": int(
                completed_context.get("swim_exposures") or 0
            ),
            "strength_core_exposures_min": (
                1
                if policy["microcycle_policy"].get(
                    "protect_strength_core_each_microcycle"
                )
                else 0
            ),
            "completed_strength_exposures": int(
                completed_context.get("strength_exposures") or 0
            ),
            "completed_direct_capabilities": sorted(
                set(completed_context.get("direct_capabilities") or [])
                | set(completed_context.get("planning_credits") or [])
            ),
            "max_run_quality_exposures": int(
                policy["microcycle_policy"].get(
                    "max_run_quality_exposures", 2
                )
            ),
            "slot_count_min": 4,
            "slot_count_max": 7,
            "day_1_blocked_by_enduro": is_enduro_school_date(target_start),
            "day_after_fixed_enduro_requires_low_leg_load": is_enduro_school_date(
                target_start
            ),
            "adjacent_run_stressors_forbidden": True,
            "declared_unavailable_days": list(
                profile_contract.get("unavailable_days") or []
            ),
            "declared_preferred_active_days": profile_contract.get(
                "preferred_active_days"
            ),
            "declared_normal_active_day_range": [
                profile_contract.get("min_active_days"),
                profile_contract.get("max_active_days"),
            ],
            "declared_double_session_preference": profile_contract.get(
                "double_sessions"
            ),
            "declared_rest_day_preference": profile_contract.get("rest_days"),
            "closed_day_indexes": closed_days,
            "past_days_are_immutable": True,
            "automatic_progress_requires_absorbed_dose": True,
        },
    }


def generate_microcycle(
    meso,
    goal,
    policy,
    catalog,
    athlete_state,
    target_start,
    athlete_profile=None,
    starting_state=None,
    planning_date=None,
    *,
    request_fn=None,
):
    completed_context = completed_microcycle_context(athlete_state, target_start)
    source_payload = build_microcycle_source_payload(
        meso,
        goal,
        policy,
        catalog,
        athlete_state,
        target_start,
        athlete_profile=athlete_profile,
        starting_state=starting_state,
        completed_context=completed_context,
        planning_date=planning_date,
    )
    competition_context = source_payload["competition_context"]
    digest = canonical_hash(source_payload)
    system = (
        "Du komponerar en sjudagars mikrocykel från ett redan fattat mesocykelbeslut. "
        "Mesocykeln har redan vägt hela målportföljen; mikrocykeln får inte omtolka A-målet som enda mål. declared_athlete_profile och declared_profile_contract är atletens egna uppgifter och får inte ersättas av AI-antaganden. confirmed_starting_state är bekräftat startläge: observerad del är fakta, manuell del är självrapport och får styra konservativ etablering men aldrig räknas som absorberad dos eller ensam motivera progression. "
        "Ett enskilt sjudagarsfönster behöver inte uttrycka varje mål eller disciplin, men det får inte systematiskt radera kapaciteter som mesocykeln håller sekundära, underhållna eller skyddade. "
        "competition_context beskriver det verifierade A-loppet och tid kvar. Den får påverka specificitet inom mesocykelns beslut men är aldrig i sig skäl att lägga till träning eller öka dos. "
        "Välj endast dag, stimulusrecept och åtgärden establish/progress/consolidate/reduce. "
        "Du får inte hitta på exakta farter, pulser, watt eller doser; deterministisk kod väljer sedan dos från observerad historik och receptkatalog. "
        "Föregående veckas schema ska inte kopieras av slentrian. Kontrollera konflikt mellan mekaniska/kardiovaskulära stimuli och fasta åtaganden. "
        "block_context anger mikrocykelns roll i blocket och mesocycle_history visar tidigare planerade recept och doser. Historiken är evidens om vad som redan ordinerats, inte ett skäl att automatiskt öka belastningen. "
        "development_blueprint är mesocykelns preliminära grundplan för passkaraktär genom hela blocket. current_microcycle_blueprint ska normalt styra vilket receptformat som används för primära stimuli, så att utvecklingen innehåller planerad variation och inte samma pass av slentrian. Avvik bara när faktisk belastning, återhämtning, tillgänglighet eller hårda guards ger sakligt skäl och förklara avvikelsen. Blueprintens progress_if_ready är en planerad riktning, aldrig tillstånd att öka dos utan progression_ready=true. "
        "I en develop-mikrocykel ska ett primärt utvecklingsstimulus progressa längs mesocykelns definierade axel eller ha ett uttryckligt datastött skäl att konsolidera. "
        "Samma primära recept och samma passkaraktär får inte upprepas mekaniskt genom utvecklingsveckor. Om två utvecklande simexponeringar planeras och katalogen erbjuder absorberbara alternativ ska de normalt ha olika development_character. "
        "I consolidate/review får ett jämförbart pass medvetet återkomma för stabilisering eller utvärdering, men skälet ska framgå. "
        "Output måste uppfylla hard_requirements i underlaget: alla primära kapaciteter ska täckas direkt, "
        "normalantalet simexponeringar ska finnas, minst en styrka/core-exponering ska finnas när policyn kräver det, "
        "och antalet löpkvalitetsexponeringar får inte överskrida maxgränsen. "
        "Sekundära kapaciteter är inte en checklista och behöver inte alla förekomma varje vecka. "
        "completed_microcycle_context är faktisk träning i målveckan och ska krediteras mot krav och primära stimuli när direkt evidens finns. "
        "Planera inte om samma primära stimulus en gång till bara för att den ursprungliga kalenderdagen låg senare i veckan. "
        "hard_requirements.closed_day_indexes är redan passerade dagar i en live-vecka och är immutabla: nya slots får aldrig läggas där. Ett undanträngt pass måste i stället omprövas och vid behov flyttas till en framtida absorberbar dag. "
        "Lägg inte löptröskel, backkvalitet eller lång löpdistans två dagar i rad. När dag 1 är fast enduro ska dag 2 ha låg benbelastning; "
        "lägg inte löp- eller MTB-belastning där innan faktiskt enduroutfall är känt. MTB/XC får inte ligga direkt intill löptröskel eller backkvalitet; "
        "sekundär cykelbelastning ska utgå hellre än att kompromissa ett primärt löpstimulus. "
        "Det finns ingen generell regel om obligatorisk vilodag. Fördela redan motiverade stimuli mot atletens deklarerade frekvens och tillgänglighet utan att lägga till träning bara för att fylla en ledig dag. "
        "Om dubbelpass bara är okej ibland ska befintliga stimuli normalt spridas till en tillgänglig tom dag innan de klustras. "
        "Flera självständiga pass får ligga samma kalenderdag när belastningsordningen eller atletens preferens motiverar det; varje slot är alltid ett eget pass. Datum är inte passidentitet. "
        "Om swim_threshold behövs finns ett separat etablerat 4 000 m-recept; behandla det som kvalitetsrecept, inte som automatisk distansprogression från det aeroba 3 200 m-passet. "
        "Enduro dag 1 är faktisk belastning och blockerar annan planering den dagen. "
        "athlete_state.dose_response skiljer demonstrerad, tolererad och absorberad dos. Progress får bara väljas när relevant capability har progression_ready=true; "
        "ett genomfört maxvärde är aldrig i sig progressionsstöd. 24–72 h-signaler är återhämtningskontext utan antagen kausalitet. "
        "athlete_state.load_windows är faktiska durations-/exponeringsfönster och får användas för att upptäcka ackumulerad belastning, men är inte TSS eller ett återhämtningsmått. "
        "Progress får bara väljas för ett primärt mesocykelstimulus och ska ha stöd i athlete_state; annars välj consolidate/establish. "
        "En ledig dag är inte ett skäl att fylla kalendern. Kontrollera slutligen själv att varje hard_requirement är uppfyllt innan du svarar."
    )
    try:
        raw = call_structured(
            system,
            source_payload,
            microcycle_schema(
                sorted(catalog["recipes"])
            ),
            "microcycle_decision",
            request_fn=request_fn,
        )
        source = "openai"
    except Exception as exc:
        raw = fallback_microcycle(
            meso, policy, catalog, target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
            planning_date=planning_date,
            athlete_state=athlete_state,
            starting_state=starting_state,
        )
        raw["rationale"] += f" Modellbedömning saknades: {str(exc)[:220]}"
        source = "deterministic_fallback"

    repair_metadata = None
    if source == "openai":
        initial_failures = microcycle_guard_failures(
            raw, meso, policy, catalog, target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
            planning_date=planning_date,
        )
        if initial_failures:
            repair_payload = deepcopy(source_payload)
            repair_payload["rejected_proposal"] = raw
            repair_payload["guard_failures"] = initial_failures
            repair_payload["repair_instruction"] = (
                "Reparera förslaget så att varje guard_failure försvinner. Behåll bra val där de inte "
                "orsakar konflikt. Välj fortfarande bara day_index, recipe_key och action; hitta inte på dos."
            )
            try:
                repaired = call_structured(
                    system + " Detta är ett reparationsförsök efter deterministisk guard; varje angivet fel måste lösas.",
                    repair_payload,
                    microcycle_schema(
                        sorted(catalog["recipes"])
                    ),
                    "microcycle_decision_repair",
                    request_fn=request_fn,
                )
                repaired_failures = microcycle_guard_failures(
                    repaired, meso, policy, catalog, target_start,
                    completed_context=completed_context,
                    athlete_profile=athlete_profile,
                    planning_date=planning_date,
                )
                if not repaired_failures:
                    raw = repaired
                    source = "openai_repaired"
                    repair_metadata = {
                        "attempted": True,
                        "initial_failures": initial_failures,
                        "result": "accepted",
                    }
                else:
                    source = "deterministic_fallback_after_repair_guard"
                    repair_metadata = {
                        "attempted": True,
                        "initial_failures": initial_failures,
                        "repair_failures": repaired_failures,
                        "result": "fallback",
                    }
                    raw = fallback_microcycle(
                        meso, policy, catalog, target_start,
                        completed_context=completed_context,
                        athlete_profile=athlete_profile,
                        planning_date=planning_date,
                        athlete_state=athlete_state,
                        starting_state=starting_state,
                    )
            except Exception as exc:
                source = "deterministic_fallback_after_repair_error"
                repair_metadata = {
                    "attempted": True,
                    "initial_failures": initial_failures,
                    "repair_error": str(exc)[:400],
                    "result": "fallback",
                }
                raw = fallback_microcycle(
                    meso, policy, catalog, target_start,
                    completed_context=completed_context,
                    athlete_profile=athlete_profile,
                    planning_date=planning_date,
                    athlete_state=athlete_state,
                    starting_state=starting_state,
                )

    normalized, model_valid = validate_and_normalize_micro(
        raw, meso, policy, catalog, target_start,
        completed_context=completed_context,
        athlete_profile=athlete_profile,
        planning_date=planning_date,
    )
    if source.startswith("deterministic_fallback"):
        normalized = align_fallback_progression_with_block_intent(
            normalized,
            meso,
            policy,
            catalog,
            athlete_state,
            target_start,
            starting_state=starting_state,
        )
    if source in {"openai", "openai_repaired"} and not model_valid:
        # Defensive backstop. A proposal accepted above must still pass the
        # normalizer used by publication.
        source = "deterministic_fallback_after_normalization_guard"
        normalized = fallback_microcycle(
            meso, policy, catalog, target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
            planning_date=planning_date,
            athlete_state=athlete_state,
            starting_state=starting_state,
        )
        repair_metadata = repair_metadata or {
            "attempted": False,
            "result": "fallback",
        }
        repair_metadata["normalization_guard_failed"] = True
    final_failures = microcycle_guard_failures(
        normalized,
        meso,
        policy,
        catalog,
        target_start,
        completed_context=completed_context,
        athlete_profile=athlete_profile,
        planning_date=planning_date,
    )
    if final_failures:
        final_fallback = fallback_microcycle(
            meso,
            policy,
            catalog,
            target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
            planning_date=planning_date,
            athlete_state=athlete_state,
            starting_state=starting_state,
        )
        fallback_failures = microcycle_guard_failures(
            final_fallback,
            meso,
            policy,
            catalog,
            target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
            planning_date=planning_date,
        )
        if fallback_failures:
            raise RuntimeError(
                "Adaptive planering: deterministisk fallback är ogiltig: "
                + " | ".join(fallback_failures)
            )
        normalized = final_fallback
        source = "deterministic_fallback_after_final_guard"
        repair_metadata = repair_metadata or {
            "attempted": False,
            "result": "fallback",
        }
        repair_metadata["final_guard_failures"] = final_failures
    normalized = normalize_progress_actions_from_absorption(
        normalized,
        athlete_state,
    )
    normalized.update(
        {
            "schema_version": MICRO_SCHEMA_VERSION,
            "planner_revision": MICRO_PLANNER_REVISION,
            "source": source,
            "source_hash": digest,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "week_start": target_start.isoformat(),
            "week_key": week_key(target_start),
            "mesocycle_id": meso["id"],
            "competition_context": competition_context,
            "completed_microcycle_context": completed_context,
            "athlete_profile_hash": athlete_profile_hash(athlete_profile),
            "starting_state_hash": athlete_starting_state_hash(starting_state),
        }
    )
    if repair_metadata is not None:
        normalized["guard_repair"] = repair_metadata
    return normalized


def microcycle_is_valid(decision, meso, target_start, source_hash_value=None):
    if not isinstance(decision, dict):
        return False
    return (
        decision.get("schema_version") == MICRO_SCHEMA_VERSION
        and decision.get("planner_revision") == MICRO_PLANNER_REVISION
        and decision.get("week_start") == target_start.isoformat()
        and decision.get("mesocycle_id") == meso.get("id")
        and bool(decision.get("slots"))
        and (source_hash_value is None or decision.get("source_hash") == source_hash_value)
    )


def demonstrated_value(recipe_key, athlete_state, recipe=None):
    facts = athlete_state.get("capability_facts") or {}
    capability = RECIPE_TO_RESPONSE_CAPABILITY.get(recipe_key)
    capability_state = (
        ((athlete_state.get("capability_states") or {}).get("by_capability") or {})
        .get(capability or "") or {}
    )
    state_value = capability_state.get("demonstrated_value")
    if isinstance(state_value, (int, float)):
        return float(state_value)
    if capability == "run_threshold":
        values = [
            item.get("work_minutes")
            for item in (facts.get("run_threshold") or {}).get("evidence") or []
            if isinstance(item.get("work_minutes"), (int, float))
        ]
        return max(values) if values else None
    if capability == "run_hill_quality":
        values = [
            item.get("repetitions")
            for item in (facts.get("run_hill_quality") or {}).get("evidence") or []
            if isinstance(item.get("repetitions"), (int, float))
        ]
        return max(values) if values else None
    if capability == "run_easy_distance":
        value = ((facts.get("run_easy_distance") or {}).get("longest_duration") or {}).get("elapsed_time_s")
        return float(value) / 60.0 if isinstance(value, (int, float)) else None
    if capability in {"mtb_technical", "mtb_aerobic"}:
        fact_key = capability if capability in facts else "mtb_technical"
        value = ((facts.get(fact_key) or {}).get("longest_duration") or {}).get("elapsed_time_s")
        return float(value) / 60.0 if isinstance(value, (int, float)) else None
    if capability == "swim_aerobic":
        value = ((facts.get("swim_aerobic") or {}).get("longest_distance") or {}).get("distance_m")
        option_values = [
            float(item.get("value"))
            for item in ((recipe or {}).get("options") or [])
            if isinstance(item.get("value"), (int, float))
        ]
        ceiling = max(option_values) if option_values else None
        if not isinstance(value, (int, float)):
            return None
        return min(float(value), ceiling) if ceiling is not None else float(value)
    if capability == "swim_threshold":
        values = [
            item.get("distance_m")
            for item in (facts.get("swim_threshold") or {}).get("evidence") or []
            if isinstance(item.get("distance_m"), (int, float))
        ]
        return max(values) if values else None
    if recipe_key == "strength_core":
        value = ((facts.get("strength_unilateral") or {}).get("longest_duration") or {}).get("elapsed_time_s")
        return float(value) / 60.0 if isinstance(value, (int, float)) else None
    return None

def choose_option(recipe_key, recipe, action, athlete_state, starting_state=None):
    options = [
        item for item in recipe.get("options") or []
        if isinstance(item.get("value"), (int, float))
    ]
    if not options:
        raise RuntimeError(f"Recept {recipe_key!r} saknar numeriska dosalternativ")
    options = sorted(options, key=lambda item: (float(item["value"]), str(item.get("id") or "")))

    observed = demonstrated_value(recipe_key, athlete_state, recipe)
    profile = response_profile_for_recipe(recipe_key, athlete_state)
    absorbed = (profile or {}).get("absorbed_value")
    tolerated = (profile or {}).get("tolerated_value")
    absorbed = float(absorbed) if isinstance(absorbed, (int, float)) else None
    tolerated = float(tolerated) if isinstance(tolerated, (int, float)) else None

    # Prefer evidence that a dose has been absorbed. When the new response
    # profile exists, a merely demonstrated maximum must never become the future
    # planning floor. Legacy demonstrated-value fallback is retained only for
    # old/test state that predates dose_response.
    trusted = absorbed if absorbed is not None else tolerated
    if trusted is None and profile is None:
        trusted = float(observed) if isinstance(observed, (int, float)) else None

    starting_value = starting_state_value_for_recipe(recipe_key, starting_state)

    if trusted is None:
        if isinstance(starting_value, (int, float)):
            eligible = [
                index for index, item in enumerate(options)
                if float(item["value"]) <= float(starting_value) * 1.02
            ]
            floor_index = max(eligible) if eligible else 0
            evidence = (
                f"Verifierad tolererad/absorberad dos saknas. Atletens bekräftade startläge anger "
                f"{float(starting_value):g} i receptets dosvariabel; närmaste konservativa katalogsteg används "
                "endast som etableringspunkt. Självrapporten räknas inte som tolererad eller absorberad dos."
            )
        else:
            floor_index = 0
            evidence = (
                (
                    "Dose-response finns men saknar verifierad tolererad/absorberad nivå; "
                    "lägsta katalogalternativ används som konservativ etableringspunkt."
                )
                if profile is not None
                else
                "Ingen verifierad dosmarkör finns; lägsta katalogalternativ används som etableringspunkt, "
                "inte som fastställd optimal dos."
            )
    else:
        eligible = [
            index for index, item in enumerate(options)
            if float(item["value"]) <= trusted * 1.02
        ]
        floor_index = max(eligible) if eligible else 0
        if absorbed is not None:
            evidence = (
                f"Dosgolvet utgår från absorberad nivå {absorbed:g} i athlete_state.dose_response, "
                "inte från högsta genomförda värde."
            )
        elif tolerated is not None:
            evidence = (
                f"Absorberad nivå saknas; dosgolvet utgår konservativt från tolererad nivå {tolerated:g}. "
                "Detta är inte bevis för optimal framtida belastning."
            )
        else:
            evidence = (
                f"Endast demonstrerad nivå {trusted:g} finns; värdet används konservativt som kapacitetsfakta, "
                "inte som bevis för absorberad eller optimal framtida belastning."
            )

    selected_index = floor_index
    relation = "hold"
    progression_ready = bool(profile and profile.get("progression_ready") is True)

    if action == "progress":
        if not progression_ready:
            relation = "hold"
            reason = str((profile or {}).get("progression_reason") or "").strip()
            evidence += (
                " Automatisk progression blockeras eftersom absorberad dos och aktuell respons inte ger "
                "tillräckligt stöd."
                + (f" {reason}" if reason else "")
            )
        elif floor_index + 1 < len(options):
            selected_index = floor_index + 1
            relation = "progress"
            evidence += " Progression tillåts eftersom dose_response markerar progression_ready=true."
        else:
            relation = "hold"
            evidence += " Katalogen innehåller inget högre förgodkänt steg, därför konsolideras dosen."
    elif action == "reduce":
        if floor_index > 0:
            selected_index = floor_index - 1
            relation = "reduce"
        else:
            relation = "hold"
    elif action == "establish":
        relation = "establish" if trusted is None else "hold"
    else:
        relation = "hold"

    selected = options[selected_index]
    floor = options[floor_index]
    next_option = options[selected_index + 1] if selected_index + 1 < len(options) else None
    return selected, floor, next_option, relation, evidence


def mesocycle_contract(meso, policy):
    all_caps = capability_keys(policy)
    primary = list(meso.get("primary_capabilities") or [])
    secondary = [x for x in meso.get("secondary_capabilities") or [] if x not in primary]
    protected_capacity = [
        x for x in FIXED_PROTECTED_CAPACITY
        if x in all_caps and x not in primary and x not in secondary
    ]
    external = [
        x for x in EXTERNAL_LOAD_CAPABILITIES
        if x in all_caps and x not in primary and x not in secondary and x not in protected_capacity
    ]
    used = set(primary + secondary + protected_capacity + external)
    maintenance = [x for x in all_caps if x not in used]
    return {
        "primary": primary,
        "secondary": secondary,
        "maintenance": maintenance,
        "protected_capacity": protected_capacity,
        "external_load": external,
        "principle": (
            "Primära kapaciteter är mesocykelns utvecklingsuppdrag. Sekundära stimuli stödjer riktningen. "
            "Simning och styrka/core skyddas som kapacitet när de inte själva är primära. Enduro behandlas som faktisk extern belastning."
        ),
    }


def microcycle_index(meso, target_start):
    start = iso(meso["start_date"])
    return ((target_start - start).days // 7) + 1


def materialize_template(meso, micro, policy, catalog, athlete_state, starting_state=None):
    contract = mesocycle_contract(meso, policy)
    primary = set(contract["primary"])
    protected = set(contract["protected_capacity"])
    target_start = iso(micro["week_start"])
    index = microcycle_index(meso, target_start)
    block_context = mesocycle_block_context(meso, target_start, policy)
    template = []

    for ordinal, decision in enumerate(sorted(micro["slots"], key=lambda x: x["day_index"]), start=1):
        recipe_key = decision["recipe_key"]
        recipe = catalog["recipes"][recipe_key]
        caps = recipe_capabilities(recipe)
        selected, floor, next_option, relation, evidence = choose_option(
            recipe_key, recipe, decision["action"], athlete_state, starting_state
        )

        if recipe_key in SUPPORT_ONLY_RECIPES:
            role = "protected_support"
        elif caps.intersection(primary):
            role = "anchor"
        elif caps.intersection(protected):
            role = "protected_support"
        else:
            # Recipe metadata describes what the workout *can* be. Mesocycle
            # authority decides whether it is a development anchor in this block.
            role = "flex"

        slot = {
            "slot": f"{recipe_key}_{ordinal}",
            "recipe_key": recipe_key,
            "development_character": recipe.get("development_character") or recipe_key,
            "block_intent": block_context.get("block_intent"),
            "sport": recipe["sport"],
            "priority_role": role,
            "stimuli": deepcopy(recipe.get("stimuli") or []),
            "session": selected["session"],
            "reason": (
                f"{decision['rationale']} {evidence} "
                f"Veckobeslut: {decision['action']}; materialiserad relation: {relation}."
            ),
            "development_focus": recipe["development_focus"],
            "day_index": int(decision["day_index"]),
            "dose_options": deepcopy(recipe["options"]),
            "baseline_option_id": selected["id"],
            "load_dimensions": deepcopy(recipe.get("load_dimensions") or []),
            "progression_criteria": [
                "Ändra bara dos när faktisk träningsrespons eller mesocykelns progressionsbeslut ger sakligt stöd.",
                "Wellness eller en enskild bra dag får inte ensam motivera belastningsökning.",
                "Närliggande 2–3 dagars faktisk belastning ska kunna motivera hold, reduktion eller flytt.",
            ],
        }
        if recipe.get("optional_stimuli"):
            slot["optional_stimuli"] = deepcopy(recipe["optional_stimuli"])
        if recipe.get("performance_marker_id"):
            slot["performance_marker_id"] = recipe["performance_marker_id"]

        if role == "anchor":
            slot["development_progression"] = {
                "mode": "develop",
                "demonstrated_floor_option_id": floor["id"],
                "same_dose_repeat_requires_reason": True,
                "source": (
                    "athlete_state"
                    if (
                        ((response_profile_for_recipe(recipe_key, athlete_state) or {}).get("absorbed_value") is not None)
                        or ((response_profile_for_recipe(recipe_key, athlete_state) or {}).get("tolerated_value") is not None)
                    )
                    else "starting_state"
                    if starting_state_value_for_recipe(recipe_key, starting_state) is not None
                    else "catalog"
                ),
                "microcycle_plan": [
                    {
                        "microcycle": index,
                        "option_id": selected["id"],
                        "relation": relation,
                        "reason": (
                            f"Mikrocykelbeslutet valde {decision['action']} och dosen materialiserades "
                            f"från verifierad träningsrespons, bekräftat startläge eller konservativ katalogbas "
                            f"utan att höja flera belastningsvariabler samtidigt."
                        ),
                    }
                ],
            }
            if next_option is not None:
                slot["progression_target_option_id"] = next_option["id"]
            else:
                slot["progression_ceiling_reason"] = (
                    "Ingen högre förgodkänd dos finns i receptkatalogen. Fortsatt utveckling kräver "
                    "nytt recept eller annan progressionsaxel, inte automatisk extrapolering."
                )
        template.append(slot)
    return template, contract


DISCIPLINE_CAPABILITIES = {
    "run": {"run_threshold", "run_hill_quality", "run_easy_distance"},
    "swim": {"swim_aerobic", "swim_technique", "swim_threshold"},
    "mtb": {"mtb_technical", "mtb_aerobic"},
    "strength": {"strength_unilateral", "strength_core", "plyometric"},
}

DISCIPLINE_LABELS = {
    "run": "Löpning",
    "swim": "Simning",
    "mtb": "MTB/XC",
    "strength": "Styrka / core / plyo",
}


def generated_current_priorities(meso):
    primary = set(meso.get("primary_capabilities") or [])
    secondary = set(meso.get("secondary_capabilities") or [])
    rows = []
    for key, caps in DISCIPLINE_CAPABILITIES.items():
        if caps.intersection(primary):
            rank = 0
            mode = "develop"
            intent = "Primärt utvecklingsområde i aktuell genererad mesocykel."
        elif caps.intersection(secondary):
            rank = 1
            mode = "maintain_develop"
            intent = "Sekundärt utvecklingsområde som stödjer aktuell mesocykel."
        elif key in {"swim", "strength"}:
            rank = 2
            mode = "maintain_develop"
            intent = "Skyddad kapacitet som ska finnas kvar utan att tränga undan mesocykelns primära stimuli."
        else:
            rank = 3
            mode = "supporting"
            intent = "Stödjande kapacitet; får plats när den är absorberbar och förenlig med målbilden."
        rows.append((rank, key, mode, intent))

    rows.sort(key=lambda row: (row[0], row[1]))
    return [
        {
            "key": key,
            "label": DISCIPLINE_LABELS[key],
            "mode": mode,
            "priority": index,
            "intent": intent,
        }
        for index, (_, key, mode, intent) in enumerate(rows, start=1)
    ]


def generated_capability_portfolio(policy, meso):
    primary = set(meso.get("primary_capabilities") or [])
    secondary = set(meso.get("secondary_capabilities") or [])
    result = deepcopy(policy["strategy_base"].get("capability_portfolio") or [])
    for item in result:
        key = item.get("key")
        if key in CAPABILITY_REGISTRY:
            item["response_metric"] = capability_metric(key)
            item["evidence_policy"] = capability_evidence_policy(key)
            item["progression_axes"] = list(capability_progression_axes(key))
            item["recipe_family"] = list(capability_recipe_family(key))
        if key in primary:
            item["mode"] = "develop"
            item["priority"] = 1
        elif key in secondary:
            item["mode"] = "maintain_develop"
            item["priority"] = 2
        elif key == "plyometric":
            item["mode"] = "develop_cautiously"
            item["priority"] = 3
        elif key in FIXED_PROTECTED_CAPACITY:
            item["mode"] = "maintain_develop"
            item["priority"] = 3
        elif key in EXTERNAL_LOAD_CAPABILITIES:
            item["mode"] = "supporting"
            item["priority"] = 5
        else:
            item["mode"] = "supporting"
            item["priority"] = 4
    return result


def generated_strategic_readiness(goal, policy):
    rows = deepcopy(policy["strategy_base"].get("strategic_readiness") or [])
    active_sports = {
        str(item.get("sport") or "").lower()
        for item in (goal.get("performance_goals") or [])
        if item.get("status") == "active"
    }
    for row in rows:
        row["state"] = "active_focus" if row.get("key") in active_sports else "keep_option_open"
    return rows


def goal_runtime_source_label(runtime_source):
    source = str((runtime_source or {}).get("source") or "")
    return (
        "supabase:training_goal_document"
        if source.startswith("supabase")
        else "data/goal.json"
    )


def materialize_strategy(goal, policy, meso, micro, catalog, athlete_state, goal_runtime_source=None, starting_state=None, athlete_profile=None):
    strategy = deepcopy(policy["strategy_base"])
    strategy["schema_version"] = int(policy["compatibility_strategy_schema_version"])
    digest = goal_hash(goal)
    strategy["north_star"] = goal.get("goal") or strategy.get("north_star")
    strategy["current_priorities"] = generated_current_priorities(meso)
    strategy["capability_portfolio"] = generated_capability_portfolio(policy, meso)
    strategy["strategic_readiness"] = generated_strategic_readiness(goal, policy)
    goal_rows = planning_goal_set(goal)
    declared_profile_goals = deepcopy((planner_profile_view(athlete_profile) or {}).get("goals") or [])
    normalized_contributions = normalize_goal_contributions(
        goal_rows,
        meso.get("goal_contributions"),
        meso.get("goal_contribution"),
        meso.get("competition_context") or {},
    )
    runtime_source = goal_runtime_source or {
        "source": "json_fallback",
        "verified": False,
        "reason": "not_supplied",
        "source_hash": digest,
    }
    strategy["goal_contract"] = {
        "source_file": "data/goal.json",
        "runtime_source": runtime_source.get("source"),
        "runtime_source_verified": bool(runtime_source.get("verified")),
        "runtime_source_reason": runtime_source.get("reason"),
        "runtime_source_hash": runtime_source.get("source_hash"),
        "source_schema_version": goal.get("schema_version"),
        "goal_hash": digest,
        "goal_change_requires_mesocycle_review": True,
        "goal_set": deepcopy(goal_rows),
        "declared_profile_goals": declared_profile_goals,
        "competition_context": deepcopy(meso.get("competition_context") or {}),
        "principle": (
            "Målportföljen är kanonisk: varaktiga utvecklingsmål anger vilken atlet som byggs och "
            "tidsatta prestationsmål lägger till prioritering/specificitet. Ett A-mål får inte implicit "
            "ersätta den varaktiga målbilden. Ändring kräver nytt genererat mesocykelbeslut."
        ),
    }

    template, contract = materialize_template(meso, micro, policy, catalog, athlete_state, starting_state)
    required_each = [
        x for x in REQUIRED_EACH_MICROCYCLE
        if x in contract["protected_capacity"]
    ]
    protected_across = [
        x for x in FIXED_PROTECTED_CAPACITY
        if x in contract["protected_capacity"]
    ]
    completed_context = micro.get("completed_microcycle_context") or {}
    completed_capabilities = list(
        dict.fromkeys(
            list(completed_context.get("direct_capabilities") or [])
            + list(completed_context.get("planning_credits") or [])
        )
    )
    if int(completed_context.get("strength_exposures") or 0) > 0:
        completed_capabilities.extend(["strength_unilateral", "strength_core"])
    if int(completed_context.get("swim_exposures") or 0) > 0:
        completed_capabilities.extend(["swim_aerobic"])
    if int(completed_context.get("enduro_exposures") or 0) > 0:
        completed_capabilities.append("enduro_technical")
    completed_capabilities = list(dict.fromkeys(completed_capabilities))

    strategy["current_mesocycle"] = {
        "id": meso["id"],
        "title": meso["title"],
        "start_date": meso["start_date"],
        "end_date": meso["end_date"],
        "evaluation_date": meso["evaluation_date"],
        "goal_basis_hash": digest,
        "goal_contribution": meso["goal_contribution"],
        "goal_contributions": deepcopy(normalized_contributions),
        "hypothesis": meso["hypothesis"],
        "protected_stimuli": list(contract["primary"]),
        "supporting_stimuli": [
            x for group in ("secondary", "maintenance", "protected_capacity", "external_load")
            for x in contract[group]
        ],
        "contract": contract,
        "capacity_protection": {
            "required_each_microcycle": required_each,
            "protected_across_mesocycle": protected_across,
            "completed_current_microcycle": completed_capabilities,
            "completed_context": deepcopy(completed_context),
            "missing_required_action": "review_and_restore_in_next_absorbable_window",
            "rules": [
                "Simning och styrka/core får inte försvinna som restpost när de är skyddad kapacitet.",
                "Plyometri är skyddad över blocket men genomförs bara när den kan absorberas utan konflikt med löp-/MTB-kvalitet.",
            ],
        },
        "periodization": mesocycle_block_context(
            meso,
            iso(micro["week_start"]),
            policy,
        ),
        "development_blueprint": build_development_blueprint(
            meso,
            policy,
            catalog,
            athlete_state=athlete_state,
            starting_state=starting_state,
        ),
        "forward_horizon": build_forward_planning_horizon(
            meso,
            policy,
            catalog,
            athlete_state,
            iso(micro["week_start"]),
            starting_state=starting_state,
            weeks=5,
        ),
        "progression_policy": {
            "automatic_load_increase": False,
            "keep_intensity_controlled": True,
            "dose_decided_near_term": False,
            "preserve_stimulus_before_preserving_exact_session": True,
            "missed_protected_stimulus_requires_review": True,
            "microcycle_may_reorganize_sessions": True,
            "baseline_session_planned_in_microcycle": True,
            "progression_requires_explicit_criteria": True,
            "change_one_load_variable_at_a_time": True,
            "wellness_cannot_trigger_progression": True,
            "normal_variation_does_not_trigger_change": True,
            "development_key_sessions_must_progress_or_justify_hold": True,
            "regression_below_demonstrated_floor_requires_reason": True,
            "maintenance_sessions_may_repeat_without_progression": True,
            "max_consecutive_development_repeats_without_reason": 1,
            "unchanged_development_recipe_repeat_requires_reason": True,
        },
        "success_signals": list(meso.get("success_signals") or []),
        "guardrails": list(meso.get("guardrails") or []) + list(policy.get("decision_guards") or []),
        "review_questions": [
            "Har mesocykelns primära kapaciteter fått återkommande, absorberbara stimuli?",
            "Talar jämförbara pass och uttryckliga användarrapporter för progression, konsolidering eller behov av ändrad riktning?",
            "Har skyddad sim- och styrkekapacitet kunnat behållas utan att tränga undan primära stimuli?",
            "Har utvecklingspassen faktiskt ändrat dos, struktur eller träningskaraktär enligt blockets avsikt, eller har samma pass upprepats utan tillräckligt skäl?",
            "Bör nästa mesocykel fortsätta, modifiera eller byta fokus utifrån faktisk respons snarare än föregående veckomall?",
        ],
        "microcycle_structure": {
            "length_days": 7,
            "calendar_alignment": "monday_sunday",
            "rationale": (
                "Sjudagars mikrocykel används för enkel kalenderpresentation. Innehållet kommer från ett "
                "separat genererat mikrocykelbeslut, inte från en permanent veckomall."
            ),
        },
        "microcycle_template": template,
        "decision_trace": {
            "mesocycle_decision_source": meso.get("source"),
            "mesocycle_source_hash": meso.get("source_hash"),
            "microcycle_decision_source": micro.get("source"),
            "microcycle_source_hash": micro.get("source_hash"),
            "microcycle_week_key": micro.get("week_key"),
            "athlete_profile_hash": meso.get("athlete_profile_hash"),
            "starting_state_hash": meso.get("starting_state_hash"),
            "competition_context": deepcopy(meso.get("competition_context") or {}),
        },
    }
    strategy["development_roadmap"] = build_development_roadmap(strategy, policy, athlete_state)
    strategy["generated_planning"] = {
        "source_policy": "data/planning_policy.json",
        "source_goal": goal_runtime_source_label(runtime_source),
        "source_athlete_state": "data/athlete_state.json",
        "source_starting_state": (
            "supabase:athlete_starting_states"
            if starting_state
            else "none"
        ),
        "source_mesocycle_decision": "data/mesocycle_decision.json",
        "source_microcycle_decision": "data/microcycle_decision.json",
        "principle": "training_strategy.json är en genererad kompatibilitetsprojektion och inte längre planeringens källa.",
    }
    validate_training_strategy(strategy)
    return strategy


def append_decision_log(kind, decision):
    document = load_json(DECISION_LOG_FILE, {"schema_version": 1, "entries": []})
    entries = document.setdefault("entries", [])
    signature = (kind, decision.get("source_hash"), decision.get("id") or decision.get("week_key"))
    if not any(
        (row.get("kind"), row.get("source_hash"), row.get("decision_id")) == signature
        for row in entries
    ):
        entries.append(
            {
                "kind": kind,
                "decision_id": decision.get("id") or decision.get("week_key"),
                "source": decision.get("source"),
                "source_hash": decision.get("source_hash"),
                "generated_at_utc": decision.get("generated_at_utc"),
                "summary": decision.get("title") or decision.get("rationale"),
            }
        )
        document["entries"] = entries[-200:]
        write_json(DECISION_LOG_FILE, document)


def previous_archived_plan(target_start):
    previous_start = target_start - timedelta(days=7)
    path = WEEKS_DIR / f"{week_key(previous_start)}.json"
    snapshot = load_json(path, {})
    plan = snapshot.get("plan") or {}
    if not plan:
        return None
    try:
        if iso((plan.get("meta") or {})["week_end"]) != target_start - timedelta(days=1):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return plan


def _workout_date(workout):
    try:
        return iso(workout.get("date"))
    except (TypeError, ValueError):
        return None


def _workout_identity_match(left, right):
    left_recipe = str(left.get("recipe_key") or "").strip()
    right_recipe = str(right.get("recipe_key") or "").strip()
    if left_recipe and right_recipe:
        return left_recipe == right_recipe
    return (
        str(left.get("sport") or "").lower() == str(right.get("sport") or "").lower()
        and set(left.get("stimuli") or []) == set(right.get("stimuli") or [])
    )


def _actual_context_changed(plan, completed_context):
    previous = (
        (((plan.get("meta") or {}).get("capacity_protection") or {}).get("completed_context"))
        or {}
    )
    return completed_context_signature(previous) != completed_context_signature(
        completed_context or {}
    )


def reconcile_unaffected_future_workouts(
    current_plan,
    rebuilt,
    *,
    target_start,
    today,
    completed_context,
):
    """Preserve unrelated future intents during an actual-driven live replan."""
    if not _actual_context_changed(current_plan, completed_context):
        return rebuilt

    credits = set(completed_context.get("direct_capabilities") or [])
    credits.update(completed_context.get("planning_credits") or [])
    day_map = completed_context.get("capability_day_indexes") or {}
    completed_run_quality_days = {
        int(day)
        for capability in ("run_threshold", "run_hill_quality")
        for day in (day_map.get(capability) or [])
        if isinstance(day, int)
    }

    preserved = []
    for workout in canonical_planned_workouts(
        current_plan,
        context="active-replan current plan",
    ):
        workout_day = _workout_date(workout)
        if workout_day is None or workout_day <= today:
            continue
        if not target_start <= workout_day <= target_start + timedelta(days=6):
            continue
        if (
            workout.get("activity_id")
            or workout.get("activity_ids")
            or workout.get("planning_status") == "completed"
        ):
            continue

        stimuli = {
            str(value)
            for value in (workout.get("stimuli") or [])
            if str(value)
        }
        if stimuli and stimuli.issubset(credits):
            continue

        recipe_key = str(workout.get("recipe_key") or "").strip()
        day_index = (workout_day - target_start).days + 1
        if (
            is_enduro_school_date(target_start)
            and day_index == 2
            and recipe_key in DAY_AFTER_ENDURO_BLOCKED_RECIPES
        ):
            continue
        if (
            recipe_key in (RUN_STRESS_RECIPES | {"mtb_technical"})
            and any(
                abs(day_index - completed_day) <= 1
                for completed_day in completed_run_quality_days
            )
        ):
            continue
        preserved.append(deepcopy(workout))

    if not preserved:
        return rebuilt

    reconciled = deepcopy(rebuilt)
    future = list(
        canonical_planned_workouts(
            reconciled,
            context="active-replan rebuilt plan",
        )
    )
    for old in preserved:
        matching = [
            (index, row)
            for index, row in enumerate(future)
            if _workout_identity_match(old, row)
        ]
        if matching:
            old_day = _workout_date(old)
            index, _ = min(
                matching,
                key=lambda item: (
                    abs((_workout_date(item[1]) - old_day).days)
                    if _workout_date(item[1]) is not None and old_day is not None
                    else 999
                ),
            )
            future[index] = old
        else:
            future.append(old)

    future.sort(
        key=lambda row: (
            str(row.get("date") or ""),
            int(row.get("microcycle_day") or 99),
            str(row.get("microcycle_slot") or row.get("recipe_key") or ""),
        )
    )
    reconciled["planned_workouts"] = future
    reconciled.setdefault("meta", {})["live_reconciliation"] = {
        "policy": "preserve_unaffected_future_intents",
        "preserved_workout_keys": [
            str(
                row.get("workout_key")
                or row.get("microcycle_slot")
                or row.get("recipe_key")
                or ""
            )
            for row in preserved
        ],
        "completed_context_signature": completed_context_signature(
            completed_context or {}
        ),
    }
    return reconciled


def build_target_microcycle(
    *,
    meso,
    goal,
    policy,
    catalog,
    athlete_state,
    target_start,
    athlete_profile=None,
    starting_state=None,
    existing_micro=None,
    planning_date=None,
    request_fn=None,
):
    """Resolve one microcycle against only that week's completed context.

    Completed training is week-scoped. A live-week replan must never carry its
    completed capabilities into the next microcycle merely because both weeks
    belong to the same mesocycle.
    """
    completed_context = completed_microcycle_context(athlete_state, target_start)
    source_payload = build_microcycle_source_payload(
        meso,
        goal,
        policy,
        catalog,
        athlete_state,
        target_start,
        athlete_profile=athlete_profile,
        starting_state=starting_state,
        completed_context=completed_context,
        planning_date=planning_date,
    )
    source_hash_value = canonical_hash(source_payload)
    if microcycle_is_valid(
        existing_micro or {},
        meso,
        target_start,
        source_hash_value,
    ):
        return deepcopy(existing_micro), completed_context, False

    decision = generate_microcycle(
        meso,
        goal,
        policy,
        catalog,
        athlete_state,
        target_start,
        athlete_profile=athlete_profile,
        starting_state=starting_state,
        planning_date=planning_date,
        request_fn=request_fn,
    )
    return decision, completed_context, True


def build_upcoming_strategy_after_active_replan(
    *,
    goal,
    policy,
    meso,
    catalog,
    athlete_state,
    target_start,
    goal_runtime_source,
    athlete_profile=None,
    starting_state=None,
    request_fn=None,
):
    """Build the next week from its own microcycle decision, never the live one."""
    next_start = target_start + timedelta(days=7)
    if not mesocycle_is_valid(
        meso,
        goal,
        next_start,
        athlete_profile_hash(athlete_profile),
        athlete_starting_state_hash(starting_state),
    ):
        return None, None

    future_micro, future_completed, _ = build_target_microcycle(
        meso=meso,
        goal=goal,
        policy=policy,
        catalog=catalog,
        athlete_state=athlete_state,
        target_start=next_start,
        athlete_profile=athlete_profile,
        starting_state=starting_state,
        existing_micro=None,
        request_fn=request_fn,
    )
    future_strategy = materialize_strategy(
        goal,
        policy,
        meso,
        future_micro,
        catalog,
        athlete_state,
        goal_runtime_source=goal_runtime_source,
        starting_state=starting_state,
        athlete_profile=athlete_profile,
    )
    return future_strategy, {
        "week_start": next_start.isoformat(),
        "completed_context": future_completed,
        "microcycle": future_micro,
    }


def rebuild_calendar(
    plan,
    strategy,
    target_start,
    active_replan,
    *,
    today=None,
    completed_context=None,
    upcoming_strategy=None,
):
    if active_replan:
        source = previous_archived_plan(target_start)
        if source is None:
            raise RuntimeError(
                "Adaptive planering: aktiv övergångsvecka behöver föregående arkiverade vecka för gissningsfri återbyggnad."
            )
        preview = build_mesocycle_next_week(source, strategy)
        rebuilt = promote_upcoming(preview)
        if iso(rebuilt["meta"]["week_start"]) != target_start:
            raise RuntimeError("Adaptive planering: återbyggd aktiv vecka fick fel startdatum")
        if today is not None and completed_context is not None:
            rebuilt = reconcile_unaffected_future_workouts(
                plan,
                rebuilt,
                target_start=target_start,
                today=today,
                completed_context=completed_context,
            )
        upcoming = build_mesocycle_next_week(
            rebuilt,
            upcoming_strategy or strategy,
        )
        write_json(PLAN_FILE, rebuilt)
        write_json(UPCOMING_FILE, upcoming)
        return "active_and_upcoming"

    preview = build_mesocycle_next_week(plan, strategy)
    if iso(preview["meta"]["week_start"]) != target_start:
        raise RuntimeError("Adaptive planering: genererad kommande vecka matchar inte målveckan")
    write_json(UPCOMING_FILE, preview)
    return "upcoming"


def main(*, today_local=None, meso_request_fn=None, micro_request_fn=None):
    goal, goal_runtime_source = load_goal_for_planner(GOAL_FILE)
    explicit_profile_generation = (
        str(os.environ.get("ATHLETE_PROFILE_PLAN_REQUEST") or "").strip().lower() == "true"
    )
    generation_request_id = str(
        os.environ.get("ATHLETE_PROFILE_PLAN_REQUEST_ID") or ""
    ).strip()
    if explicit_profile_generation and not generation_request_id:
        raise RuntimeError(
            "Adaptive planering: explicit profilgenerering saknar request-id"
        )
    athlete_profile, athlete_profile_source = load_athlete_profile_for_planner(
        generation_request_id=(
            generation_request_id if explicit_profile_generation else None
        )
    )
    starting_state, starting_state_source = load_starting_state_for_planner(
        generation_request_id=(
            generation_request_id if explicit_profile_generation else None
        )
    )
    profile_hash_value = athlete_profile_hash(athlete_profile)
    starting_state_hash_value = athlete_starting_state_hash(starting_state)
    expected_profile_revision = str(
        os.environ.get("ATHLETE_PROFILE_EXPECTED_REVISION") or ""
    ).strip()
    expected_starting_state_revision = str(
        os.environ.get("ATHLETE_STARTING_STATE_EXPECTED_REVISION") or ""
    ).strip()
    if explicit_profile_generation and not athlete_profile:
        raise RuntimeError(
            "Adaptive planering: explicit profilgenerering kräver en komplett beständigt sparad atletprofil"
        )
    if explicit_profile_generation and not starting_state:
        raise RuntimeError(
            "Adaptive planering: explicit profilgenerering kräver ett bekräftat startläge"
        )
    if (
        explicit_profile_generation
        and expected_profile_revision
        and str(athlete_profile_source.get("revision") or "") != expected_profile_revision
    ):
        raise RuntimeError(
            "Adaptive planering: atletprofilen ändrades efter genereringsbegäran; skapa planen igen från aktuell profil"
        )
    if (
        explicit_profile_generation
        and expected_starting_state_revision
        and str(starting_state_source.get("revision") or "") != expected_starting_state_revision
    ):
        raise RuntimeError(
            "Adaptive planering: startläget ändrades efter genereringsbegäran; skapa planen igen från aktuellt startläge"
        )

    policy = load_json(POLICY_FILE, {})
    catalog = load_json(CATALOG_FILE, {})
    registry_failures = validate_registry_against_catalog(catalog)
    if registry_failures:
        raise RuntimeError(
            "Capability registry/catalog mismatch: " + " | ".join(registry_failures)
        )
    athlete_state = load_json(ATHLETE_STATE_FILE, {})
    plan = load_json(PLAN_FILE, {})
    upcoming = load_json(UPCOMING_FILE, {})
    current_strategy = load_json(STRATEGY_FILE, {})

    if not goal or not policy or not catalog or not athlete_state or not plan or not upcoming:
        raise RuntimeError("Adaptive planering: nödvändigt mål/policy/katalog/athlete_state/planunderlag saknas")

    today = today_local or date.today()
    if isinstance(today, str):
        today = iso(today)
    meso = load_json(MESO_FILE, {})
    micro = load_json(MICRO_FILE, {})

    current_completed_context = None
    try:
        live_start = iso((plan.get("meta") or {})["week_start"])
        live_end = iso((plan.get("meta") or {})["week_end"])
        if live_start <= today <= live_end:
            current_completed_context = completed_microcycle_context(
                athlete_state, live_start
            )
    except (KeyError, TypeError, ValueError):
        current_completed_context = None

    target_start, active_replan = resolve_planning_target(
        plan,
        upcoming,
        meso,
        today,
        goal=goal,
        microcycle_decision=micro,
        current_completed_context=current_completed_context,
    )
    target_calendar_before = deepcopy(plan if active_replan else upcoming)
    coach_ledger_before = load_coach_decision_ledger(COACH_DECISIONS_FILE)

    if not mesocycle_is_valid(
        meso, goal, target_start, profile_hash_value, starting_state_hash_value
    ):
        meso = generate_mesocycle(
            goal,
            policy,
            athlete_state,
            previous_mesocycle(current_strategy),
            target_start,
            athlete_profile=athlete_profile,
            starting_state=starting_state,
            request_fn=meso_request_fn,
        )
        write_json(MESO_FILE, meso)
        append_decision_log("mesocycle", meso)

    micro, completed_context, micro_changed = build_target_microcycle(
        meso=meso,
        goal=goal,
        policy=policy,
        catalog=catalog,
        athlete_state=athlete_state,
        target_start=target_start,
        athlete_profile=athlete_profile,
        starting_state=starting_state,
        existing_micro=micro,
        planning_date=(
            today
            if target_start <= today <= target_start + timedelta(days=6)
            else None
        ),
        request_fn=micro_request_fn,
    )
    if micro_changed:
        write_json(MICRO_FILE, micro)
        append_decision_log("microcycle", micro)

    strategy = materialize_strategy(
        goal,
        policy,
        meso,
        micro,
        catalog,
        athlete_state,
        goal_runtime_source=goal_runtime_source,
        starting_state=starting_state,
        athlete_profile=athlete_profile,
    )
    write_json(STRATEGY_FILE, strategy)

    upcoming_strategy = None
    if active_replan:
        upcoming_strategy, upcoming_trace = build_upcoming_strategy_after_active_replan(
            goal=goal,
            policy=policy,
            meso=meso,
            catalog=catalog,
            athlete_state=athlete_state,
            target_start=target_start,
            goal_runtime_source=goal_runtime_source,
            athlete_profile=athlete_profile,
            starting_state=starting_state,
            request_fn=micro_request_fn,
        )
        if upcoming_trace is not None:
            append_decision_log(
                "upcoming_microcycle",
                upcoming_trace["microcycle"],
            )

    scope = rebuild_calendar(
        plan,
        strategy,
        target_start,
        active_replan,
        today=today,
        completed_context=current_completed_context,
        upcoming_strategy=upcoming_strategy,
    )

    target_calendar_after = load_json(
        PLAN_FILE if active_replan else UPCOMING_FILE,
        {},
    )
    coach_decisions = build_coach_decisions(
        today=today,
        target_start=target_start,
        before_plan=target_calendar_before,
        after_plan=target_calendar_after,
        micro=micro,
        catalog=catalog,
        athlete_state=athlete_state,
        completed_context=completed_context,
        previous_entries=coach_ledger_before.get("entries") or [],
        capability_labels={
            key: capability_label(key)
            for key in CAPABILITY_REGISTRY
        },
        active_replan=active_replan,
        micro_changed=micro_changed,
        explicit_profile_generation=explicit_profile_generation,
    )
    appended_coach_decisions = append_coach_decisions(
        COACH_DECISIONS_FILE,
        coach_decisions,
    )

    print(
        "Adaptive planning OK: "
        f"mesocycle={meso['id']} source={meso['source']} "
        f"microcycle={micro['week_key']} source={micro['source']} "
        f"goal_source={goal_runtime_source['source']} "
        f"profile_source={athlete_profile_source.get('source')} "
        f"profile_revision={athlete_profile_source.get('revision')} "
        f"starting_state_source={starting_state_source.get('source')} "
        f"starting_state_revision={starting_state_source.get('revision')} "
        f"calendar={scope} coach_decisions={appended_coach_decisions}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
