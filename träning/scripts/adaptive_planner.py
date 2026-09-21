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

from rollover_week import (
    build_mesocycle_next_week,
    is_enduro_school_date,
    promote_upcoming,
)
from strategy_contracts import validate_training_strategy

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

CAPABILITY_TO_RECIPE = {
    "run_threshold": "run_threshold",
    "run_hill_quality": "run_hill_quality",
    "run_easy_distance": "run_easy_distance",
    "mtb_technical": "mtb_technical",
    "mtb_aerobic": "mtb_technical",
    "swim_aerobic": "swim_aerobic_technique",
    "swim_technique": "swim_aerobic_technique",
    "strength_unilateral": "swim_strength",
    "strength_core": "swim_strength",
    "plyometric": "swim_strength",
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
}
SUPPORT_ONLY_RECIPES = {"swim_strength"}


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
    # Must match validate_training_data.py: the canonical north-star string is
    # the goal contract. Status labels/phases may change without silently
    # redefining the long-term goal hash.
    canonical_goal = str(goal.get("goal") or "").strip()
    return hashlib.sha256(canonical_goal.encode("utf-8")).hexdigest()


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
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


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
            "hypothesis": {"type": "string"},
            "primary_capabilities": {
                "type": "array", "minItems": 1, "maxItems": 3, "uniqueItems": True, "items": primary_cap
            },
            "secondary_capabilities": {
                "type": "array", "maxItems": 4, "uniqueItems": True, "items": cap
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
                "maxItems": 6,
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


def fallback_mesocycle(goal, policy, previous):
    primary = []
    refs = []
    for index, text in enumerate(goal.get("next_steps") or []):
        lower = str(text).lower()
        candidate = None
        if "trösk" in lower:
            candidate = "run_threshold"
        elif "mtb" in lower or "xc" in lower:
            candidate = "mtb_technical"
        elif "distans" in lower and "löp" in lower:
            candidate = "run_easy_distance"
        # "Håll simningen frekvent och teknisk" is a protection/maintenance
        # instruction in the current goal, not by itself evidence that swimming
        # should displace a development focus in the next mesocycle.
        if candidate and candidate not in primary:
            primary.append(candidate)
            refs.append(f"goal.next_steps[{index}]")
        if len(primary) == 3:
            break
    if "run_easy_distance" not in primary and len(primary) < 3:
        primary.append("run_easy_distance")
        refs.append("goal.goal")
    if not primary:
        primary = ["run_threshold", "mtb_technical"]
        refs = ["goal.goal"]

    previous_primary = set(previous.get("protected_stimuli") or [])
    decision = "continue" if set(primary) == previous_primary else "modify"
    secondary = [
        key
        for key in ("run_hill_quality", "mtb_aerobic")
        if key not in primary
    ]
    return {
        "decision": decision,
        "title": "Mesocykel · " + " + ".join(
            {
                "run_threshold": "kontrollerad löptröskel",
                "run_easy_distance": "löptålighet",
                "mtb_technical": "MTB-teknik",
                "swim_technique": "simteknik",
            }.get(key, key)
            for key in primary
        ),
        "duration_weeks": 4,
        "goal_contribution": (
            "Föra målbilden framåt genom att utveckla de prioriterade kapaciteterna "
            "utan att låsa träningen mot ett enskilt lopp och samtidigt skydda simning och styrka/core."
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
            "Deterministisk fallback används eftersom ingen giltig modellbedömning fanns tillgänglig."
        ],
    }


def generate_mesocycle(goal, policy, athlete_state, previous, target_start, *, request_fn=None):
    caps = capability_keys(policy)
    source_payload = {
        "goal": goal,
        "policy": {
            "mesocycle_policy": policy.get("mesocycle_policy"),
            "microcycle_policy": policy.get("microcycle_policy"),
            "decision_guards": policy.get("decision_guards"),
            "capability_portfolio": policy["strategy_base"].get("capability_portfolio"),
            "current_priorities": policy["strategy_base"].get("current_priorities"),
        },
        "athlete_state": sanitize_athlete_state(athlete_state),
        "previous_mesocycle": previous,
        "target_start": target_start.isoformat(),
    }
    digest = canonical_hash(source_payload)
    system = (
        "Du är mesocykelplaneraren i ett uthållighets-/allroundsystem. "
        "Välj vad som ska utvecklas nu; skriv inte en veckoplan och ordinera inte exakta pass. "
        "Utgå endast från målbild, athlete_state och policy i underlaget. Föregående veckomall är inte evidens i sig. "
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
        result = fallback_mesocycle(goal, policy, previous)
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
    for key in result.get("secondary_capabilities") or []:
        if key in allowed and key not in primary and key not in secondary:
            secondary.append(key)
    result["primary_capabilities"] = primary
    result["secondary_capabilities"] = secondary[:4]
    result["duration_weeks"] = max(
        int(policy["mesocycle_policy"]["min_weeks"]),
        min(int(result.get("duration_weeks") or 4), int(policy["mesocycle_policy"]["max_weeks"])),
    )

    end = target_start + timedelta(days=result["duration_weeks"] * 7 - 1)
    result.update(
        {
            "schema_version": MESO_SCHEMA_VERSION,
            "source": source,
            "source_hash": digest,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "goal_hash": goal_hash(goal),
            "start_date": target_start.isoformat(),
            "end_date": end.isoformat(),
            "evaluation_date": (end + timedelta(days=1)).isoformat(),
        }
    )
    result["id"] = (
        target_start.strftime("%Y%m%d")
        + "-"
        + "-".join(result["primary_capabilities"])
    )
    return result


def mesocycle_is_valid(decision, goal, target_start):
    if not isinstance(decision, dict):
        return False
    try:
        return (
            decision.get("schema_version") == MESO_SCHEMA_VERSION
            and decision.get("goal_hash") == goal_hash(goal)
            and iso(decision["start_date"]) <= target_start <= iso(decision["end_date"])
            and bool(decision.get("primary_capabilities"))
        )
    except (KeyError, TypeError, ValueError):
        return False


def fallback_microcycle(meso, policy, catalog, target_start):
    primaries = set(meso.get("primary_capabilities") or [])
    secondaries = set(meso.get("secondary_capabilities") or [])
    wanted = primaries | secondaries
    slots = []

    def add(day, recipe, rationale):
        if recipe in catalog["recipes"] and not any(row["day_index"] == day for row in slots):
            caps = recipe_capabilities(catalog["recipes"][recipe])
            action = "consolidate" if caps.intersection(primaries) else "establish"
            slots.append(
                {
                    "day_index": day,
                    "recipe_key": recipe,
                    "action": action,
                    "rationale": rationale,
                    "evidence_refs": ["mesocycle.primary_capabilities" if caps.intersection(primaries) else "planning_policy.microcycle_policy"],
                }
            )

    if "run_threshold" in wanted:
        add(2, "run_threshold", "Placera kontrollerad löpkvalitet med marginal efter mikrocykelstarten.")
    add(3, "swim_aerobic_technique", "Skydda simfrekvens med låg mekanisk benkostnad.")
    if {"mtb_technical", "mtb_aerobic"}.intersection(wanted) or "mtb_technical" in primaries:
        add(4, "mtb_technical", "Ge MTB/XC en egen teknisk/aerob exponering.")
    if "run_hill_quality" in wanted:
        add(5, "run_hill_quality", "Separera mekanisk backkvalitet från tröskelstimuluset.")
    add(6, "swim_strength", "Kombinera andra simexponeringen med skyddad styrka/core.")
    if "run_easy_distance" in wanted or "run_easy_distance" in primaries:
        add(7, "run_easy_distance", "Lägg lugn löptålighet sist i mikrocykeln.")

    used_caps = set()
    for row in slots:
        used_caps |= recipe_capabilities(catalog["recipes"][row["recipe_key"]])
    free_days = [day for day in range(2 if is_enduro_school_date(target_start) else 1, 8) if day not in {r["day_index"] for r in slots}]
    for cap in meso.get("primary_capabilities") or []:
        if cap in used_caps:
            continue
        recipe = CAPABILITY_TO_RECIPE.get(cap)
        if recipe and free_days and recipe in catalog["recipes"]:
            day = free_days.pop(0)
            add(day, recipe, f"Säkerställ mesocykelns primära stimulus {cap}.")
            used_caps |= recipe_capabilities(catalog["recipes"][recipe])

    return {
        "rationale": "Deterministisk reservkomposition som realiserar mesocykelns valda stimuli utan att kopiera föregående vecka som beslutsgrund.",
        "slots": sorted(slots, key=lambda row: row["day_index"]),
    }


def validate_and_normalize_micro(result, meso, policy, catalog, target_start):
    recipes = catalog["recipes"]
    seen_days = set()
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
        if day in seen_days or recipe_key not in recipes:
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
        seen_days.add(day)

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

    required_swims = int(policy["microcycle_policy"].get("normal_swim_exposures", 2))
    valid = (
        primaries.issubset(direct_primary_caps)
        and swim_exposures >= required_swims
        and (not policy["microcycle_policy"].get("protect_strength_core_each_microcycle") or strength_exposures >= 1)
        and run_quality <= int(policy["microcycle_policy"].get("max_run_quality_exposures", 2))
        and 4 <= len(cleaned) <= 6
    )
    if not valid:
        return fallback_microcycle(meso, policy, catalog, target_start), False
    return {"rationale": str(result.get("rationale") or "").strip(), "slots": sorted(cleaned, key=lambda x: x["day_index"])}, True


def generate_microcycle(meso, goal, policy, catalog, athlete_state, target_start, *, request_fn=None):
    source_payload = {
        "week_start": target_start.isoformat(),
        "fixed_enduro_day_1": is_enduro_school_date(target_start),
        "goal": {
            "goal": goal.get("goal"),
            "current_phase": goal.get("current_phase"),
            "next_steps": goal.get("next_steps"),
        },
        "mesocycle": meso,
        "microcycle_policy": policy.get("microcycle_policy"),
        "decision_guards": policy.get("decision_guards"),
        "athlete_state": sanitize_athlete_state(athlete_state),
        "recipe_capabilities": {
            key: sorted(recipe_capabilities(value))
            for key, value in catalog["recipes"].items()
        },
    }
    digest = canonical_hash(source_payload)
    system = (
        "Du komponerar en sjudagars mikrocykel från ett redan fattat mesocykelbeslut. "
        "Välj endast dag, stimulusrecept och åtgärden establish/progress/consolidate/reduce. "
        "Du får inte hitta på exakta farter, pulser, watt eller doser; deterministisk kod väljer sedan dos från observerad historik och receptkatalog. "
        "Föregående veckas schema ska inte kopieras av slentrian. Kontrollera konflikt mellan mekaniska/kardiovaskulära stimuli och fasta åtaganden. "
        "Två simexponeringar är normal grundplan när absorberbart; styrka/core ska skyddas. "
        "Enduro dag 1 är faktisk belastning och blockerar annan planering den dagen. "
        "Progress får bara väljas för ett primärt mesocykelstimulus och ska ha stöd i athlete_state; annars välj consolidate/establish. "
        "En ledig dag är inte ett skäl att fylla kalendern."
    )
    try:
        raw = call_structured(
            system,
            source_payload,
            microcycle_schema(sorted(catalog["recipes"])),
            "microcycle_decision",
            request_fn=request_fn,
        )
        source = "openai"
    except Exception as exc:
        raw = fallback_microcycle(meso, policy, catalog, target_start)
        raw["rationale"] += f" Modellbedömning saknades: {str(exc)[:220]}"
        source = "deterministic_fallback"

    normalized, model_valid = validate_and_normalize_micro(raw, meso, policy, catalog, target_start)
    if source == "openai" and not model_valid:
        source = "deterministic_fallback_after_guard"
    normalized.update(
        {
            "schema_version": MICRO_SCHEMA_VERSION,
            "source": source,
            "source_hash": digest,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "week_start": target_start.isoformat(),
            "week_key": week_key(target_start),
            "mesocycle_id": meso["id"],
        }
    )
    return normalized


def microcycle_is_valid(decision, meso, target_start, source_hash_value=None):
    if not isinstance(decision, dict):
        return False
    return (
        decision.get("schema_version") == MICRO_SCHEMA_VERSION
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
        return float(value) if isinstance(value, (int, float)) else None
    if recipe_key in {"strength_core", "swim_strength"}:
        value = ((facts.get("strength_unilateral") or {}).get("longest_duration") or {}).get("elapsed_time_s")
        return float(value) / 60.0 if isinstance(value, (int, float)) else None
    return None


def choose_option(recipe_key, recipe, action, athlete_state):
    options = [
        item for item in recipe.get("options") or []
        if isinstance(item.get("value"), (int, float))
    ]
    if not options:
        raise RuntimeError(f"Recept {recipe_key!r} saknar numeriska dosalternativ")
    options = sorted(options, key=lambda item: (float(item["value"]), str(item.get("id") or "")))
    observed = demonstrated_value(recipe_key, athlete_state)

    if observed is None:
        floor_index = 0
        evidence = "Ingen verifierad dosmarkör finns i athlete_state; lägsta katalogalternativ används som etableringspunkt, inte som fastställd optimal dos."
    else:
        eligible = [
            index for index, item in enumerate(options)
            if float(item["value"]) <= float(observed) * 1.02
        ]
        floor_index = max(eligible) if eligible else 0
        evidence = (
            f"Valet utgår från ett observerat värde {observed:g} i athlete_state för receptets dosvariabel; "
            "värdet används som kapacitetsfakta, inte som bevis för optimal framtida belastning."
        )

    selected_index = floor_index
    relation = "hold"
    if action == "progress":
        if floor_index + 1 < len(options):
            selected_index = floor_index + 1
            relation = "progress"
        else:
            relation = "hold"
            evidence += " Katalogen innehåller inget högre verifierat steg, därför konsolideras dosen."
    elif action == "reduce":
        if floor_index > 0:
            selected_index = floor_index - 1
            relation = "reduce"
        else:
            relation = "hold"
    elif action == "establish":
        relation = "establish" if observed is None else "hold"
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


def materialize_template(meso, micro, policy, catalog, athlete_state):
    contract = mesocycle_contract(meso, policy)
    primary = set(contract["primary"])
    protected = set(contract["protected_capacity"])
    index = microcycle_index(meso, iso(micro["week_start"]))
    template = []

    for ordinal, decision in enumerate(sorted(micro["slots"], key=lambda x: x["day_index"]), start=1):
        recipe_key = decision["recipe_key"]
        recipe = catalog["recipes"][recipe_key]
        caps = recipe_capabilities(recipe)
        selected, floor, next_option, relation, evidence = choose_option(
            recipe_key, recipe, decision["action"], athlete_state
        )

        if recipe_key in SUPPORT_ONLY_RECIPES:
            role = "protected_support"
        elif caps.intersection(primary):
            role = "anchor"
        elif caps.intersection(protected):
            role = "protected_support"
        else:
            role = recipe.get("priority_role") or "flex"

        slot = {
            "slot": f"{recipe_key}_{ordinal}",
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
                "source": "athlete_state",
                "microcycle_plan": [
                    {
                        "microcycle": index,
                        "option_id": selected["id"],
                        "relation": relation,
                        "reason": (
                            f"Mikrocykelbeslutet valde {decision['action']} och dosen materialiserades "
                            f"från athlete_state utan att höja flera belastningsvariabler samtidigt."
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


def materialize_strategy(goal, policy, meso, micro, catalog, athlete_state):
    strategy = deepcopy(policy["strategy_base"])
    strategy["schema_version"] = int(policy["compatibility_strategy_schema_version"])
    digest = goal_hash(goal)
    strategy["north_star"] = goal.get("goal") or strategy.get("north_star")
    strategy["goal_contract"] = {
        "source_file": "data/goal.json",
        "source_schema_version": goal.get("schema_version"),
        "goal_hash": digest,
        "goal_change_requires_mesocycle_review": True,
        "principle": "Målbilden är kanonisk. Ändring kräver nytt genererat mesocykelbeslut innan planeringen fortsätter.",
    }

    template, contract = materialize_template(meso, micro, policy, catalog, athlete_state)
    required_each = [
        x for x in REQUIRED_EACH_MICROCYCLE
        if x in contract["protected_capacity"]
    ]
    protected_across = [
        x for x in FIXED_PROTECTED_CAPACITY
        if x in contract["protected_capacity"]
    ]

    strategy["current_mesocycle"] = {
        "id": meso["id"],
        "title": meso["title"],
        "start_date": meso["start_date"],
        "end_date": meso["end_date"],
        "evaluation_date": meso["evaluation_date"],
        "goal_basis_hash": digest,
        "goal_contribution": meso["goal_contribution"],
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
            "missing_required_action": "review_and_restore_in_next_absorbable_window",
            "rules": [
                "Simning och styrka/core får inte försvinna som restpost när de är skyddad kapacitet.",
                "Plyometri är skyddad över blocket men genomförs bara när den kan absorberas utan konflikt med löp-/MTB-kvalitet.",
            ],
        },
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
        },
        "success_signals": list(meso.get("success_signals") or []),
        "guardrails": list(meso.get("guardrails") or []) + list(policy.get("decision_guards") or []),
        "review_questions": [
            "Har mesocykelns primära kapaciteter fått återkommande, absorberbara stimuli?",
            "Talar jämförbara pass och uttryckliga användarrapporter för progression, konsolidering eller behov av ändrad riktning?",
            "Har skyddad sim- och styrkekapacitet kunnat behållas utan att tränga undan primära stimuli?",
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
        },
    }
    strategy["generated_planning"] = {
        "source_policy": "data/planning_policy.json",
        "source_goal": "data/goal.json",
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
    goal = load_json(GOAL_FILE, {})
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
    target_start, active_replan = target_week(plan, upcoming, today)

    meso = load_json(MESO_FILE, {})
    if not mesocycle_is_valid(meso, goal, target_start):
        meso = generate_mesocycle(
            goal,
            policy,
            athlete_state,
            previous_mesocycle(current_strategy),
            target_start,
            request_fn=meso_request_fn,
        )
        write_json(MESO_FILE, meso)
        append_decision_log("mesocycle", meso)

    micro_source_payload = {
        "week_start": target_start.isoformat(),
        "mesocycle": meso,
        "goal": goal,
        "microcycle_policy": policy.get("microcycle_policy"),
        "decision_guards": policy.get("decision_guards"),
        "athlete_state": sanitize_athlete_state(athlete_state),
        "recipe_capabilities": {
            key: sorted(recipe_capabilities(value))
            for key, value in catalog["recipes"].items()
        },
        "fixed_enduro_day_1": is_enduro_school_date(target_start),
    }
    micro_digest = canonical_hash(micro_source_payload)
    micro = load_json(MICRO_FILE, {})
    if not microcycle_is_valid(micro, meso, target_start, micro_digest):
        micro = generate_microcycle(
            meso,
            goal,
            policy,
            catalog,
            athlete_state,
            target_start,
            request_fn=micro_request_fn,
        )
        write_json(MICRO_FILE, micro)
        append_decision_log("microcycle", micro)

    strategy = materialize_strategy(goal, policy, meso, micro, catalog, athlete_state)
    write_json(STRATEGY_FILE, strategy)
    scope = rebuild_calendar(plan, strategy, target_start, active_replan)

    print(
        "Adaptive planning OK: "
        f"mesocycle={meso['id']} source={meso['source']} "
        f"microcycle={micro['week_key']} source={micro['source']} "
        f"calendar={scope}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
