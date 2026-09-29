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
from goal_contracts import planning_goal_hash, planning_goal_set
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
WEEKS_DIR = DATA / "weeks"

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
MESO_SCHEMA_VERSION = 1
MICRO_SCHEMA_VERSION = 1
PLANNER_REVISION = 6
MICRO_PLANNER_REVISION = 12

CAPABILITY_TO_RECIPE = {
    "run_threshold": "run_threshold",
    "run_hill_quality": "run_hill_quality",
    "run_easy_distance": "run_easy_distance",
    "mtb_technical": "mtb_technical",
    "mtb_aerobic": "mtb_technical",
    "swim_aerobic": "swim_aerobic_technique",
    "swim_technique": "swim_aerobic_technique",
    "swim_threshold": "swim_aerobic_threshold",
    "strength_unilateral": "strength_core",
    "strength_core": "strength_core",
    "plyometric": "strength_core",
}

RECIPE_TO_RESPONSE_CAPABILITY = {
    "run_threshold": "run_threshold",
    "run_hill_quality": "run_hill_quality",
    "run_easy_distance": "run_easy_distance",
    "mtb_technical": "mtb_technical",
    "swim_aerobic_technique": "swim_aerobic",
    "swim_aerobic_endurance": "swim_aerobic",
    "swim_aerobic_threshold": "swim_threshold",
    "strength_core": "strength_unilateral",
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
RUN_STRESS_RECIPES = {"run_threshold", "run_hill_quality", "run_easy_distance"}
DAY_AFTER_ENDURO_BLOCKED_RECIPES = RUN_STRESS_RECIPES | {"mtb_technical", "strength_core"}


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

    if recipe_key == "run_easy_distance":
        return numeric("run", "long_run_minutes") or numeric("run", "typical_duration_minutes")
    if recipe_key in {"swim_aerobic_technique", "swim_aerobic_endurance", "swim_aerobic_threshold"}:
        return numeric("swim", "typical_distance_m")
    if recipe_key == "mtb_technical":
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


def resolve_planning_target(plan, upcoming, mesocycle_decision, today, goal=None, microcycle_decision=None):
    """Choose the week the adaptive engine is allowed to plan.

    A generated mesocycle is authoritative for its full declared duration.
    Once a live microcycle has started, planner/schema revisions are not allowed
    to reshuffle that active week. Such revisions apply to the upcoming
    microcycle; near-term coaching and explicit user input own changes inside the
    live week. This keeps planning architecture changes from masquerading as
    athlete-driven adaptation.
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
    for capability, facts in (athlete_state.get("capability_facts") or {}).items():
        if not isinstance(facts, dict):
            continue
        evidence_rows = list(facts.get("evidence") or [])
        for field in ("longest_distance", "longest_duration"):
            item = facts.get(field)
            if isinstance(item, dict):
                evidence_rows.append(item)
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
        "capability_refs": capability_refs,
        "activity_refs": sorted(activity_ids),
        "evidence_note": (
            "Familjeexponeringar kommer från faktiskt registrerade aktiviteter i målveckan. "
            "Direkt kapabilitetskredit kräver daterad athlete_state-evidens från samma aktivitet."
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


def fallback_microcycle(meso, policy, catalog, target_start, completed_context=None, athlete_profile=None):
    """Conservative composition from requirements, not from calendar fill.

    Fixed Enduro consumes a real training day. Secondary capabilities are not a
    checklist and may be omitted from an individual microcycle. The fallback
    first covers direct primary stimuli and protected swim/strength, then adds
    only a useful secondary exposure if there is a safe slot.
    """
    primaries = set(meso.get("primary_capabilities") or [])
    secondaries = set(meso.get("secondary_capabilities") or [])
    fixed_enduro = is_enduro_school_date(target_start)
    completed_context = completed_context or {}
    completed_swims = int(completed_context.get("swim_exposures") or 0)
    completed_strength = int(completed_context.get("strength_exposures") or 0)
    completed_direct = set(completed_context.get("direct_capabilities") or [])
    profile_contract = profile_planning_contract(athlete_profile) if athlete_profile else {}
    allowed_profile_days = (
        set(profile_contract.get("available_days") or [])
        if profile_contract.get("availability_declared")
        else set(range(1, 8))
    )
    slots = []

    recipe_day_preferences = {
        "swim_aerobic_technique": [2, 4, 6, 1, 5, 3, 7] if fixed_enduro else [1, 3, 5, 2, 4, 6, 7],
        "swim_aerobic_threshold": [2, 4, 6, 5, 3, 7] if fixed_enduro else [1, 3, 5, 2, 4, 6, 7],
        "run_threshold": [3, 4, 5, 6, 7] if fixed_enduro else [2, 3, 4, 5, 6, 7, 1],
        "run_hill_quality": [5, 6, 7, 4, 3] if fixed_enduro else [4, 5, 6, 7, 3, 2, 1],
        "run_easy_distance": [7, 6, 5, 4, 3] if fixed_enduro else [7, 6, 5, 4, 3, 2, 1],
        "mtb_technical": [6, 7, 4, 5, 3] if fixed_enduro else [6, 7, 4, 5, 3, 2, 1],
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

    # Low-mechanical swim is the conservative default immediately after fixed
    # Enduro and directly covers both swim_aerobic and swim_technique.
    if fixed_enduro and {"swim_aerobic", "swim_technique"}.intersection(primaries):
        add_recipe(
            "swim_aerobic_technique",
            "Lågmekanisk simexponering dagen efter fast enduro ger konkret plan utan att anta att benen är redo för ny benkvalitet.",
        )

    # Cover each primary with an executable direct recipe.
    for cap in meso.get("primary_capabilities") or []:
        if cap in completed_direct:
            continue
        direct_recipe = CAPABILITY_TO_RECIPE.get(cap)
        if not direct_recipe:
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
        candidates = [
            key
            for key in (
                "swim_aerobic_endurance",
                "swim_aerobic_technique",
                "swim_aerobic_threshold",
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
    if "run_easy_distance" in secondaries or "run_easy_distance" in primaries:
        secondary_added = add_recipe(
            "run_easy_distance",
            "Behåll lugn löptålighet med separation från löpkvalitet.",
            action="consolidate",
        )

    # Add at most one secondary exposure in total. A free slot is not a reason
    # to force MTB/hills into a week that already contains race-relevant
    # secondary long-run work plus fixed Enduro.
    if not secondary_added:
        for cap in ("run_hill_quality", "mtb_technical", "mtb_aerobic"):
            if cap not in secondaries:
                continue
            recipe = CAPABILITY_TO_RECIPE.get(cap)
            if recipe and add_recipe(
                recipe,
                f"Vald sekundär exponering för {cap}; övriga sekundära kapaciteter behöver inte täckas varje mikrocykel.",
                action="consolidate",
            ):
                break

    return {
        "rationale": (
            "Deterministisk reservkomposition som täcker primära stimuli och skyddad kapacitet, "
            "respekterar fast enduro och lämnar återhämtningsutrymme i stället för att fylla kalendern."
        ),
        "slots": sorted(slots, key=lambda row: row["day_index"]),
    }


def microcycle_layout_failures(rows, catalog, target_start, athlete_profile=None):
    """Hard scheduling guards for known planned load adjacency.

    Calendar dates group workouts; they are not unique workout slots. Guards
    therefore evaluate all recipes on each date without collapsing co-located
    sessions.
    """
    failures = []
    fixed_enduro = is_enduro_school_date(target_start)
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

    if fixed_enduro and recipes_on(2).intersection(DAY_AFTER_ENDURO_BLOCKED_RECIPES):
        blocked = sorted(recipes_on(2).intersection(DAY_AFTER_ENDURO_BLOCKED_RECIPES))
        failures.append(
            f"{', '.join(blocked)} får inte ligga direkt dagen efter fast enduro när faktisk benbelastning ännu är okänd"
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


def microcycle_guard_failures(result, meso, policy, catalog, target_start, completed_context=None, athlete_profile=None):
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
        valid_rows, catalog, target_start, athlete_profile=athlete_profile
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

    direct_primary_caps = set()
    swim_exposures = 0
    strength_exposures = 0
    run_quality = 0

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
    total_run_quality = completed_run_quality + run_quality
    if total_run_quality > max_run_quality:
        failures.append(
            f"för många löpkvalitetsexponeringar inklusive faktiskt genomförda: {total_run_quality} > {max_run_quality}"
        )

    return failures


def validate_and_normalize_micro(result, meso, policy, catalog, target_start, completed_context=None, athlete_profile=None):
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
    )
    if not valid:
        return fallback_microcycle(
            meso, policy, catalog, target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
        ), False
    return {"rationale": str(result.get("rationale") or "").strip(), "slots": sorted(cleaned, key=lambda x: x["day_index"])}, True


def response_profile_for_recipe(recipe_key, athlete_state):
    capability = RECIPE_TO_RESPONSE_CAPABILITY.get(recipe_key)
    if not capability:
        return None
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
    return {
        "week_start": target_start.isoformat(),
        "declared_athlete_profile": declared_profile,
        "declared_profile_contract": profile_contract,
        "confirmed_starting_state": planner_starting_state_view(starting_state),
        "competition_context": competition_context,
        "completed_microcycle_context": completed_context,
        "block_context": mesocycle_block_context(meso, target_start, policy),
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
            "completed_direct_capabilities": list(
                completed_context.get("direct_capabilities") or []
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
        "I en develop-mikrocykel ska ett primärt utvecklingsstimulus progressa längs mesocykelns definierade axel eller ha ett uttryckligt datastött skäl att konsolidera. "
        "Samma primära recept och samma passkaraktär får inte upprepas mekaniskt genom utvecklingsveckor. Om två utvecklande simexponeringar planeras och katalogen erbjuder absorberbara alternativ ska de normalt ha olika development_character. "
        "I consolidate/review får ett jämförbart pass medvetet återkomma för stabilisering eller utvärdering, men skälet ska framgå. "
        "Output måste uppfylla hard_requirements i underlaget: alla primära kapaciteter ska täckas direkt, "
        "normalantalet simexponeringar ska finnas, minst en styrka/core-exponering ska finnas när policyn kräver det, "
        "och antalet löpkvalitetsexponeringar får inte överskrida maxgränsen. "
        "Sekundära kapaciteter är inte en checklista och behöver inte alla förekomma varje vecka. "
        "completed_microcycle_context är faktisk träning i målveckan och ska krediteras mot krav och primära stimuli när direkt evidens finns. "
        "Planera inte om samma primära stimulus en gång till bara för att den ursprungliga kalenderdagen låg senare i veckan. "
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
        )
        raw["rationale"] += f" Modellbedömning saknades: {str(exc)[:220]}"
        source = "deterministic_fallback"

    repair_metadata = None
    if source == "openai":
        initial_failures = microcycle_guard_failures(
            raw, meso, policy, catalog, target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
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
                )

    normalized, model_valid = validate_and_normalize_micro(
        raw, meso, policy, catalog, target_start,
        completed_context=completed_context,
        athlete_profile=athlete_profile,
    )
    if source in {"openai", "openai_repaired"} and not model_valid:
        # Defensive backstop. A proposal accepted above must still pass the
        # normalizer used by publication.
        source = "deterministic_fallback_after_normalization_guard"
        normalized = fallback_microcycle(
            meso, policy, catalog, target_start,
            completed_context=completed_context,
            athlete_profile=athlete_profile,
        )
        repair_metadata = repair_metadata or {
            "attempted": False,
            "result": "fallback",
        }
        repair_metadata["normalization_guard_failed"] = True
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


def demonstrated_value(recipe_key, athlete_state):
    facts = athlete_state.get("capability_facts") or {}
    if recipe_key == "run_threshold":
        values = [
            item.get("work_minutes")
            for item in (facts.get("run_threshold") or {}).get("evidence") or []
            if isinstance(item.get("work_minutes"), (int, float))
        ]
        return max(values) if values else None
    if recipe_key == "run_hill_quality":
        values = [
            item.get("repetitions")
            for item in (facts.get("run_hill_quality") or {}).get("evidence") or []
            if isinstance(item.get("repetitions"), (int, float))
        ]
        return max(values) if values else None
    if recipe_key == "run_easy_distance":
        value = ((facts.get("run_easy_distance") or {}).get("longest_duration") or {}).get("elapsed_time_s")
        return float(value) / 60.0 if isinstance(value, (int, float)) else None
    if recipe_key == "mtb_technical":
        value = ((facts.get("mtb_technical") or {}).get("longest_duration") or {}).get("elapsed_time_s")
        return float(value) / 60.0 if isinstance(value, (int, float)) else None
    if recipe_key == "swim_aerobic_technique":
        value = ((facts.get("swim_aerobic") or {}).get("longest_distance") or {}).get("distance_m")
        return min(float(value), 3200.0) if isinstance(value, (int, float)) else None
    if recipe_key == "swim_aerobic_endurance":
        value = ((facts.get("swim_aerobic") or {}).get("longest_distance") or {}).get("distance_m")
        return min(float(value), 3600.0) if isinstance(value, (int, float)) else None
    if recipe_key == "swim_aerobic_threshold":
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

    observed = demonstrated_value(recipe_key, athlete_state)
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


def materialize_strategy(goal, policy, meso, micro, catalog, athlete_state, goal_runtime_source=None, starting_state=None):
    strategy = deepcopy(policy["strategy_base"])
    strategy["schema_version"] = int(policy["compatibility_strategy_schema_version"])
    digest = goal_hash(goal)
    strategy["north_star"] = goal.get("goal") or strategy.get("north_star")
    strategy["current_priorities"] = generated_current_priorities(meso)
    strategy["capability_portfolio"] = generated_capability_portfolio(policy, meso)
    strategy["strategic_readiness"] = generated_strategic_readiness(goal, policy)
    goal_rows = planning_goal_set(goal)
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
    completed_capabilities = list(completed_context.get("direct_capabilities") or [])
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
            "competition_context": deepcopy(meso.get("competition_context") or {}),
        },
    }
    strategy["generated_planning"] = {
        "source_policy": "data/planning_policy.json",
        "source_goal": goal_runtime_source_label(runtime_source),
        "source_athlete_state": "data/athlete_state.json",
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


def rebuild_calendar(plan, strategy, target_start, active_replan):
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
        upcoming = build_mesocycle_next_week(rebuilt, strategy)
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
    profile_hash_value = athlete_profile_hash(athlete_profile)
    expected_profile_revision = str(
        os.environ.get("ATHLETE_PROFILE_EXPECTED_REVISION") or ""
    ).strip()
    if explicit_profile_generation and not athlete_profile:
        raise RuntimeError(
            "Adaptive planering: explicit profilgenerering kräver en komplett beständigt sparad atletprofil"
        )
    if (
        explicit_profile_generation
        and expected_profile_revision
        and str(athlete_profile_source.get("revision") or "") != expected_profile_revision
    ):
        raise RuntimeError(
            "Adaptive planering: atletprofilen ändrades efter genereringsbegäran; skapa planen igen från aktuell profil"
        )

    policy = load_json(POLICY_FILE, {})
    catalog = load_json(CATALOG_FILE, {})
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
    target_start, active_replan = resolve_planning_target(
        plan, upcoming, meso, today, goal=goal, microcycle_decision=micro
    )

    if not mesocycle_is_valid(meso, goal, target_start, profile_hash_value):
        meso = generate_mesocycle(
            goal,
            policy,
            athlete_state,
            previous_mesocycle(current_strategy),
            target_start,
            athlete_profile=athlete_profile,
            request_fn=meso_request_fn,
        )
        write_json(MESO_FILE, meso)
        append_decision_log("mesocycle", meso)

    completed_context = completed_microcycle_context(athlete_state, target_start)
    micro_source_payload = build_microcycle_source_payload(
        meso,
        goal,
        policy,
        catalog,
        athlete_state,
        target_start,
        athlete_profile=athlete_profile,
        completed_context=completed_context,
    )
    micro_digest = canonical_hash(micro_source_payload)
    if not microcycle_is_valid(micro, meso, target_start, micro_digest):
        micro = generate_microcycle(
            meso,
            goal,
            policy,
            catalog,
            athlete_state,
            target_start,
            athlete_profile=athlete_profile,
            request_fn=micro_request_fn,
        )
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
    )
    write_json(STRATEGY_FILE, strategy)
    scope = rebuild_calendar(plan, strategy, target_start, active_replan)

    print(
        "Adaptive planning OK: "
        f"mesocycle={meso['id']} source={meso['source']} "
        f"microcycle={micro['week_key']} source={micro['source']} "
        f"goal_source={goal_runtime_source['source']} "
        f"profile_source={athlete_profile_source.get('source')} "
        f"profile_revision={athlete_profile_source.get('revision')} "
        f"calendar={scope}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
