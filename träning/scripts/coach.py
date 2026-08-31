#!/usr/bin/env python3
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from coach_rules import (
    allowed_target_dates,
    canonical_facts,
    decision_ready_target_dates,
    normalize_assessment_confidence,
    normalize_deferred_future_action,
    normalize_no_remaining_plan,
    plan_for_coach,
    planning_window,
    remaining_training_dates,
    validate_plan_action,
)
from strategy_contracts import validate_training_strategy
from wellness_context import signature_payload, validate_context

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
PERFORMANCE_FILE = ROOT / "data" / "performance_history.json"
COACH_FILE = ROOT / "data" / "coach.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"
PROMPT_FILE = ROOT / "coach_prompt.md"
WELLNESS_CONTEXT_FILE = Path(
    os.environ.get("WELLNESS_CONTEXT_FILE", "/tmp/training_wellness_context.json")
)

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
COACH_CONTRACT_VERSION = 13
PRIVATE_WELLNESS_PATTERN = re.compile(
    r"\b(?:hrv|vilopuls|restinghr|sömn(?:poäng|score)?|sleep(?:secs|score|quality)?|wellness|garmin|intervals\.icu)\b"
    r"(?:\s*[:=]?\s*[-+]?\d+(?:[.,]\d+)?)?",
    re.IGNORECASE,
)

_RELATIVE_LEVEL = r"(?:ovanligt\s+|relativt\s+)?(?:hög(?:t)?|låg(?:t)?|måttlig(?:t)?)(?:\s+till\s+(?:hög(?:t)?|låg(?:t)?|måttlig(?:t)?))?"
_LOAD_NOUN = (
    r"(?:(?:kardiovaskulär|kardiovaskulärt|mekanisk|mekaniskt|neuromuskulär|"
    r"neuromuskulärt|samlad|samlat)\s+)?"
    r"(?:träningsbelastning(?:en)?|träningsvolym(?:en)?|volym(?:en)?|"
    r"belastning(?:en)?|intensitet(?:en)?|återhämtningsbehov(?:et)?|kostnad(?:en)?)"
)
RELATIVE_LOAD_PREFIX_PATTERN = re.compile(
    rf"\b{_RELATIVE_LEVEL}\s+(?={_LOAD_NOUN}\b)",
    re.IGNORECASE,
)
RELATIVE_LOAD_NEGATED_PREDICATE_PATTERN = re.compile(
    rf"\b({_LOAD_NOUN})\s+inte\s+(?:är|var|ser\s+ut\s+att\s+vara|bedöms\s+som)\s+{_RELATIVE_LEVEL}\b",
    re.IGNORECASE,
)
RELATIVE_LOAD_PREDICATE_PATTERN = re.compile(
    rf"\b({_LOAD_NOUN})\s+(?:är|var|ser\s+ut\s+att\s+vara|bedöms\s+som)\s+{_RELATIVE_LEVEL}\b",
    re.IGNORECASE,
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "load_interpretation": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "facts": {"type": "array", "items": {"type": "string"}},
                "interpretations": {"type": "array", "items": {"type": "string"}},
                "unknowns": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "summary",
                "load_interpretation",
                "confidence",
                "facts",
                "interpretations",
                "unknowns",
            ],
        },
        "plan_action": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "action": {"type": "string", "enum": ["keep", "reduce", "rest", "review"]},
                "target_date": {"type": "string"},
                "reason": {"type": "string"},
                "recommendation": {"type": "string"},
                "dose_option_id": {"type": "string"},
                "requires_approval": {"type": "boolean"},
            },
            "required": ["action", "target_date", "reason", "recommendation", "dose_option_id", "requires_approval"],
        },
    },
    "required": ["assessment", "plan_action"],
}


def load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def load_private_wellness_context(path=None):
    path = path or WELLNESS_CONTEXT_FILE
    if not path.exists():
        return {}
    context = json.loads(path.read_text(encoding="utf-8"))
    validate_context(context)
    return context


def stable_hash(plan, latest_activity, local_date, strategy=None, wellness_context=None, rolling_context=None, performance_context=None):
    payload = {
        "coach_contract_version": COACH_CONTRACT_VERSION,
        "plan": plan,
        "latest_activity": latest_activity,
        "local_date": local_date,
        "strategy": strategy or {},
        "rolling_context": rolling_context or {},
        "performance_context": performance_context or {},
        "private_wellness": signature_payload(wellness_context or {}),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def performance_context_for_activity(history, activity_id):
    if activity_id is None:
        return {}
    for entry in history.get("entries") or []:
        if str(entry.get("activity_id")) == str(activity_id):
            return entry
    return {}


def fmt_pace(seconds):
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
        return ""
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}/km"


def signed(value, suffix=""):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    sign = "+" if value > 0 else ""
    text = f"{sign}{value:.1f}".replace(".", ",")
    return text + suffix


def performance_facts(context):
    if not context:
        return []
    work = context.get("work_intervals") or []
    summary = context.get("summary") or {}
    comparison = context.get("comparison") or {}
    facts = []

    paces = [fmt_pace(row.get("pace_s_per_km")) for row in work]
    paces = [value for value in paces if value]
    hrs = [
        str(round(row["average_heartrate"]))
        for row in work
        if isinstance(row.get("average_heartrate"), (int, float))
    ]
    if paces:
        line = f"Arbetsintervall {context.get('protocol_key', '')}: fart " + " / ".join(paces)
        if hrs and len(hrs) == len(paces):
            line += "; snittpuls " + " / ".join(hrs) + " bpm"
        facts.append(line + ".")

    within_bits = []
    pace_delta = summary.get("first_to_last_pace_delta_s_per_km")
    hr_delta = summary.get("first_to_last_hr_delta")
    if isinstance(pace_delta, (int, float)):
        within_bits.append("fart sista−första " + signed(pace_delta, " s/km"))
    if isinstance(hr_delta, (int, float)):
        within_bits.append("puls sista−första " + signed(hr_delta, " bpm"))
    if within_bits:
        facts.append("Inom passet: " + "; ".join(within_bits) + ".")

    if comparison:
        bits = []
        pace_change = comparison.get("mean_pace_delta_s_per_km")
        hr_change = comparison.get("mean_hr_delta")
        watts_change = comparison.get("mean_watts_delta")
        if isinstance(pace_change, (int, float)):
            bits.append("medelfart " + signed(pace_change, " s/km"))
        if isinstance(hr_change, (int, float)):
            bits.append("medelpuls " + signed(hr_change, " bpm"))
        if isinstance(watts_change, (int, float)):
            bits.append("medeleffekt " + signed(watts_change, " W"))
        if bits:
            facts.append(
                f"Mot föregående samma protokoll {comparison.get('previous_activity_date', '')}: "
                + "; ".join(bits) + "."
            )
    return facts[:3]


def rolling_load_context(activities, plan, local_date, strategy):
    """Build the factual multi-day window used for plan-change decisions."""
    today = datetime.fromisoformat(local_date).date()
    load_model = strategy.get("load_model") or {}
    lookback_days = int(load_model.get("lookback_days") or 3)
    lookahead_days = int(load_model.get("lookahead_days") or 3)
    actual_start = today - timedelta(days=lookback_days)
    planned_end = today + timedelta(days=lookahead_days)

    actuals = []
    for activity in activities:
        value = activity.get("start_date_local") or activity.get("start_date") or ""
        day_text = value[:10] if isinstance(value, str) and len(value) >= 10 else ""
        if not day_text:
            continue
        try:
            activity_day = datetime.fromisoformat(day_text).date()
        except ValueError:
            continue
        if actual_start <= activity_day <= today:
            actuals.append(activity)

    planned = []
    for day in plan.get("days", []):
        day_text = day.get("date") or ""
        try:
            planned_day = datetime.fromisoformat(day_text).date()
        except (TypeError, ValueError):
            continue
        if today <= planned_day <= planned_end:
            planned.append(day)

    return {
        "lookback_days": lookback_days,
        "lookahead_days": lookahead_days,
        "actual_activities": sorted(
            actuals,
            key=lambda item: item.get("start_date_local") or item.get("start_date") or "",
        ),
        "planned_days": sorted(planned, key=lambda item: item.get("date") or ""),
        "load_dimensions": load_model.get("dimensions") or [],
        "rules": load_model.get("rules") or [],
    }


def neutralize_unbased_load_text(value):
    """Remove unsupported relative load levels from model-generated prose.

    The coach may describe observed facts, but without an explicit personal
    baseline it may not classify load/volume/intensity/recovery need as high,
    low or moderate. This guard changes only derived prose; canonical facts are
    never passed through it.
    """
    text = str(value or "")
    text = RELATIVE_LOAD_NEGATED_PREDICATE_PATTERN.sub(
        lambda match: f"{match.group(1)} inte ger sakligt stöd för en konservativ planändring",
        text,
    )
    text = RELATIVE_LOAD_PREDICATE_PATTERN.sub(
        lambda match: f"{match.group(1)} kan inte nivåklassas mot personlig baslinje",
        text,
    )
    text = RELATIVE_LOAD_PREFIX_PATTERN.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def neutralize_unbased_load_labels(result):
    """Calibrate derived AI fields while preserving source facts verbatim."""
    assessment = result.get("assessment") or {}
    for field in ("summary", "load_interpretation"):
        if isinstance(assessment.get(field), str):
            assessment[field] = neutralize_unbased_load_text(assessment[field])
    for field in ("interpretations", "unknowns"):
        values = assessment.get(field)
        if isinstance(values, list):
            assessment[field] = [
                neutralize_unbased_load_text(item) if isinstance(item, str) else item
                for item in values
            ]

    action = result.get("plan_action") or {}
    for field in ("reason", "recommendation"):
        if isinstance(action.get(field), str):
            action[field] = neutralize_unbased_load_text(action[field])
    return result


def scrub_private_wellness_output(value):
    """Prevent private wellness source names/metrics from being persisted in public coach state."""
    if isinstance(value, str):
        return PRIVATE_WELLNESS_PATTERN.sub("återhämtningsunderlaget", value)
    if isinstance(value, list):
        return [scrub_private_wellness_output(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_private_wellness_output(item) for key, item in value.items()}
    return value


def extract_output_text(response):
    chunks = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "refusal":
                raise RuntimeError(f"OpenAI avböjde analysen: {part.get('refusal', 'okänd orsak')}")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    if not chunks:
        raise RuntimeError("OpenAI-svaret saknar output_text")
    return "".join(chunks)


def build_openai_body(system_prompt, input_data, max_tokens, model=None):
    return {
        "model": model or MODEL,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)},
        ],
        "reasoning": {"effort": "minimal"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "training_coach",
                "strict": True,
                "schema": SCHEMA,
            },
        },
        "max_output_tokens": max_tokens,
        "store": False,
    }


def request_openai(body, api_key=None):
    key = (api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY saknas")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def parse_completed_response(response):
    text = extract_output_text(response)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"OpenAI markerade svaret completed men JSON kunde inte parsas: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI-svaret måste vara ett JSON-objekt")
    return parsed


def call_openai(system_prompt, input_data, *, request_fn=None, sleep_fn=None, model=None):
    request_fn = request_fn or request_openai
    sleep_fn = sleep_fn or time.sleep
    token_budgets = [4000, 8000]

    for attempt, max_tokens in enumerate(token_budgets, start=1):
        body = build_openai_body(system_prompt, input_data, max_tokens, model=model)
        try:
            response = request_fn(body)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < len(token_budgets):
                sleep_fn(4 * attempt)
                continue
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI HTTP {exc.code}: {details[:1200]}") from exc

        status = response.get("status")
        if status == "completed":
            return parse_completed_response(response)

        if status == "incomplete":
            reason = (response.get("incomplete_details") or {}).get("reason")
            if reason in ("max_output_tokens", "max_tokens") and attempt < len(token_budgets):
                print(f"AI coach: svar avkortat vid {max_tokens} tokens; försöker igen med större budget.")
                continue
            raise RuntimeError(f"OpenAI-svaret blev incomplete: {reason or 'okänd orsak'}")

        if status == "failed":
            err = response.get("error") or {}
            raise RuntimeError(f"OpenAI-svaret misslyckades: {err.get('message') or err}")

        raise RuntimeError(f"Oväntad OpenAI-status: {status!r}")

    raise RuntimeError("AI coach: kunde inte få ett komplett strukturerat svar.")


def normalize_dose_option_field(action):
    normalized = dict(action)
    if normalized.get("action") not in {"keep", "reduce"} or not str(normalized.get("target_date") or "").strip():
        normalized["dose_option_id"] = ""
    return normalized


def normalize_same_day_open_dose_action(plan, action, today_local):
    normalized = dict(action)
    target = str(normalized.get("target_date") or "").strip()
    if target != today_local or normalized.get("action") not in {"keep", "reduce"}:
        return normalized

    day = next((item for item in plan.get("days", []) if item.get("date") == target), None)
    if not day or day.get("dose_open") is not True:
        return normalized

    options = day.get("dose_options") or []
    option_id = str(normalized.get("dose_option_id") or "").strip()
    valid_ids = {str(option.get("id") or "") for option in options}
    if options and option_id in valid_ids:
        return normalized

    normalized["action"] = "review"
    normalized["target_date"] = ""
    normalized["dose_option_id"] = ""
    normalized["reason"] = (
        "Dagens pass har fortfarande öppen dos men ingen giltig förhandsgodkänd dos valdes."
    )
    normalized["recommendation"] = (
        "Lås inte passet som färdigt. Fastställ en konkret duration, distans eller struktur "
        "från godkända alternativ när underlaget räcker."
    )
    normalized["requires_approval"] = False
    return normalized


def normalize_resolved_dose_reselection(plan, action):
    normalized = dict(action)
    option_id = str(normalized.get("dose_option_id") or "").strip()
    target = str(normalized.get("target_date") or "").strip()
    if not option_id or not target or normalized.get("action") not in {"keep", "reduce"}:
        return normalized

    day = next((item for item in plan.get("days", []) if item.get("date") == target), None)
    if not day or day.get("dose_open") is True:
        return normalized

    resolved_id = str((day.get("dose_resolution") or {}).get("option_id") or "").strip()
    if resolved_id and option_id == resolved_id:
        normalized["dose_option_id"] = ""
    return normalized


def validate_dose_option_action(plan, action, today_local):
    option_id = str(action.get("dose_option_id") or "").strip()
    target = str(action.get("target_date") or "").strip()
    kind = action.get("action")
    day = next((d for d in plan.get("days", []) if d.get("date") == target), None) if target else None

    if option_id:
        if not day:
            raise RuntimeError("AI coach: dose_option_id kräver en giltig target_date")
        if kind not in {"keep", "reduce"}:
            raise RuntimeError("AI coach: dose_option_id får bara kombineras med keep eller reduce")
        options = day.get("dose_options") or []
        option = next((item for item in options if item.get("id") == option_id), None)
        if option is None:
            raise RuntimeError(
                f"AI coach: okänt dose_option_id {option_id!r} för {target}; "
                f"tillåtna är {[item.get('id') for item in options]!r}"
            )
        if day.get("dose_open") is not True:
            if kind != "reduce":
                raise RuntimeError("AI coach: en redan löst dos får bara ändras konservativt med reduce")
            current = day.get("dose_resolution") or {}
            current_kind = current.get("kind")
            current_value = current.get("value")
            new_kind = option.get("kind")
            new_value = option.get("value")
            if (
                current_kind != new_kind
                or not isinstance(current_value, (int, float))
                or not isinstance(new_value, (int, float))
                or new_value >= current_value
            ):
                raise RuntimeError("AI coach: en redan löst dos får endast sänkas till ett mindre godkänt alternativ")

    if (
        day
        and target == today_local
        and day.get("dose_open") is True
        and kind in {"keep", "reduce"}
        and (day.get("dose_options") or [])
        and not option_id
    ):
        raise RuntimeError(
            "AI coach: dagens öppna dos har förhandsgodkända dose_options; "
            "keep/reduce måste välja ett alternativ eller använda review."
        )
    return True


def apply_conservative_action(plan, action, *, now_utc=None):
    kind = action.get("action")
    target = action.get("target_date") or ""
    option_id = str(action.get("dose_option_id") or "").strip()
    if not target:
        return False, "Ingen automatisk planändring."

    day = next((d for d in plan.get("days", []) if d.get("date") == target), None)
    if not day or day.get("status") == "completed":
        return False, "Måldagen saknas eller är redan genomförd."

    if kind not in ("keep", "reduce", "rest"):
        return False, "Ingen automatisk planändring."

    reason = action.get("reason", "")
    applied_at = now_utc or datetime.now(timezone.utc).isoformat()
    changed = False

    if option_id:
        option = next(
            (item for item in (day.get("dose_options") or []) if item.get("id") == option_id),
            None,
        )
        if option is None:
            raise RuntimeError(f"AI coach: okänt dose_option_id {option_id!r} för {target}")
        revising = day.get("dose_open") is not True
        if revising:
            current = day.get("dose_resolution") or {}
            current_value = current.get("value")
            new_value = option.get("value")
            if (
                kind != "reduce"
                or current.get("kind") != option.get("kind")
                or not isinstance(current_value, (int, float))
                or not isinstance(new_value, (int, float))
                or new_value >= current_value
            ):
                raise RuntimeError("AI coach: redan löst dos får endast sänkas konservativt")
        if "original_session" not in day:
            day["original_session"] = day.get("session", "")
        day["session"] = option["session"]
        day["dose_open"] = False
        day["dose_resolution"] = {
            "state": "resolved",
            "kind": option.get("kind"),
            "value": option.get("value"),
            "source": "near_term_ai_revision" if revising else "near_term_ai",
            "option_id": option_id,
            "basis": reason,
            "applied_at_utc": applied_at,
        }
        changed = True

    if kind == "keep":
        if changed:
            day["auto_coach"] = {
                "action": kind,
                "reason": reason,
                "applied_at_utc": applied_at,
            }
            return True, f"Dagens dos löstes konservativt på {target}: {option_id}."
        return False, "Ingen automatisk planändring."

    if "original_session" not in day:
        day["original_session"] = day.get("session", "")
    day["auto_coach"] = {
        "action": kind,
        "reason": reason,
        "applied_at_utc": applied_at,
    }

    if kind == "rest":
        day["session"] = "Vila eller mycket lätt"
        day["sport"] = "rest"
        day["status"] = "conditional"
        day["dose_open"] = False
        day["reason"] = f"AI-coach: {reason}"
        changed = True
    elif kind == "reduce":
        if day.get("status") in ("planned", "preliminary"):
            day["status"] = "conditional"
        day["coach_adjustment"] = f"Skala ned passet. {action.get('recommendation', '')}".strip()
        changed = True

    return changed, f"Konservativ ändring applicerad på {target}: {kind}."



def main():
    plan = load_json(PLAN_FILE, {})
    upcoming = load_json(UPCOMING_FILE, {})
    decision_plan = planning_window(plan, upcoming)
    activities_state = load_json(ACTIVITIES_FILE, {"activities": []})
    performance_history = load_json(PERFORMANCE_FILE, {"schema_version": 1, "entries": []})
    coach = load_json(COACH_FILE, {"analyses": [], "last_trigger_hash": None, "last_run_utc": None})
    strategy = load_json(STRATEGY_FILE, {})
    validate_training_strategy(strategy)
    wellness_context = load_private_wellness_context()
    activities = activities_state.get("activities", [])

    if not activities:
        print("AI coach: inga aktiviteter att analysera.")
        return 0

    latest = max(activities, key=lambda activity: activity.get("start_date") or "")
    tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
    local_date = datetime.now(tz).date().isoformat()
    rolling_context = rolling_load_context(activities, decision_plan, local_date, strategy)
    performance_context = performance_context_for_activity(performance_history, latest.get("id"))
    trigger_hash = stable_hash(
        decision_plan,
        latest,
        local_date,
        strategy,
        wellness_context,
        rolling_context,
        performance_context,
    )

    if coach.get("last_trigger_hash") == trigger_hash:
        print("AI coach: inget nytt underlag; hoppar över API-anrop.")
        return 0

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("AI coach: OPENAI_API_KEY saknas; hoppar över AI-analys.")
        return 0

    latest_date = (latest.get("start_date_local") or latest.get("start_date") or "")[:10]
    recent = sorted(activities, key=lambda activity: activity.get("start_date") or "", reverse=True)[:10]
    coach_plan, fulfilled_dates = plan_for_coach(decision_plan, activities)
    candidate_dates = allowed_target_dates(decision_plan, activities, local_date)
    ready_dates = decision_ready_target_dates(decision_plan, activities, local_date)
    deferred_dates = [date for date in candidate_dates if date not in ready_dates]
    remaining_dates = remaining_training_dates(decision_plan, activities, local_date)

    input_data = {
        "today_local": local_date,
        "latest_activity": latest,
        "latest_activity_date": latest_date,
        "recent_activities": recent,
        "rolling_load_context": rolling_context,
        "performance_context": performance_context,
        "current_plan": coach_plan,
        "current_strategy": strategy,
        "private_wellness_context": wellness_context,
        "fulfilled_plan_dates": sorted(fulfilled_dates),
        "allowed_target_dates": ready_dates,
        "deferred_target_dates": deferred_dates,
        "instruction": (
            "Analysera senaste passet mot rolling_load_context, performance_context, aktuell plan och current_strategy. "
            "Om performance_context finns är dess arbetsintervall och jämförelsedelta deterministiska fakta: tolka dem, men rekonstruera eller ändra aldrig siffrorna. "
            "Skilj inom-pass-trend från jämförelse mot tidigare samma protokoll och respektera comparison_limits. "
            "Beslut ska utgå från fler-dagarsmönstret; normal variation i ett enskilt pass ska normalt absorberas av grundplanen. "
            "Skilj kardiovaskulär, mekanisk/muskulär, neuromuskulär och teknisk belastning när underlaget stödjer det och skapa aldrig ett ogrundat totalscore. "
            "private_wellness_context är ett privat, tillfälligt faktalager från Garmin via Intervals.icu. "
            "Använd det endast för att kalibrera återhämtningsbedömning mot individens egen trend; det får aldrig "
            "motivera ökad belastning och dess råvärden eller käll-/fältnamn får inte återges i synlig output. "
            "Skydda den aktuella mesocykelns prioriterade stimuli och använd mikrocykeln för att organisera dem när det går utan att ignorera faktisk belastning. "
            "Kontrollera särskilt föregående och kommande 2–3 dagar. Dagar i fulfilled_plan_dates är redan "
            "genomförda och får aldrig ordineras igen. target_date får endast väljas ur allowed_target_dates. "
            "Datum i deferred_target_dates ligger längre fram men är inte beslutsmogna eftersom mellanliggande "
            "dagars faktiska utfall ännu saknas; skriv inte om dem nu. Om allowed_target_dates är tom ska "
            "target_date vara tomt och ingen automatisk framtidsändring göras. Föreslå endast konservativ "
            "automatisk ändring; allt som kan innebära ökad belastning ska vara review och kräva godkännande. "
            "Om dagens pass har dose_open=true och dose_options ska en keep/reduce-åtgärd välja exakt ett "
            "dose_option_id från dagens alternativ. Hitta aldrig på en egen dos utanför dessa alternativ. "
            "Om underlaget inte räcker för att välja ska action vara review och dose_option_id vara tomt."
        ),
    }

    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    result = call_openai(system_prompt, input_data)
    if wellness_context.get("daily"):
        result = scrub_private_wellness_output(result)
    result = neutralize_unbased_load_labels(result)
    result["assessment"] = normalize_assessment_confidence(result["assessment"])
    result["assessment"]["facts"] = (
        canonical_facts(latest, latest_date, fulfilled_dates)
        + performance_facts(performance_context)
    )[:7]
    result["plan_action"] = normalize_deferred_future_action(
        result["plan_action"],
        candidate_dates=candidate_dates,
        ready_dates=ready_dates,
    )
    result["plan_action"] = normalize_no_remaining_plan(
        result["plan_action"],
        allowed_dates=ready_dates,
        latest_date=latest_date,
        fulfilled_dates=fulfilled_dates,
        remaining_dates=remaining_dates,
    )
    result["plan_action"] = normalize_dose_option_field(result["plan_action"])
    result["plan_action"] = normalize_resolved_dose_reselection(
        decision_plan,
        result["plan_action"],
    )
    result["plan_action"] = normalize_same_day_open_dose_action(
        decision_plan,
        result["plan_action"],
        local_date,
    )
    validate_plan_action(result["plan_action"], ready_dates)
    validate_dose_option_action(decision_plan, result["plan_action"], local_date)

    target_date = str(result["plan_action"].get("target_date") or "")
    target_plan = plan
    target_file = PLAN_FILE
    if target_date and not any(day.get("date") == target_date for day in plan.get("days", [])):
        if any(day.get("date") == target_date for day in upcoming.get("days", [])):
            target_plan = upcoming
            target_file = UPCOMING_FILE

    changed, apply_note = apply_conservative_action(target_plan, result["plan_action"])
    if changed:
        target_file.write_text(
            json.dumps(target_plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    now_utc = datetime.now(timezone.utc).isoformat()
    entry = {
        "activity_id": latest.get("id"),
        "activity_date": latest_date,
        "activity_name": latest.get("name"),
        "generated_at_utc": now_utc,
        "model": MODEL,
        "performance_marker_id": performance_context.get("marker_id") if performance_context else None,
        "performance_protocol_key": performance_context.get("protocol_key") if performance_context else None,
        "assessment": result["assessment"],
        "plan_action": result["plan_action"],
        "auto_apply": {
            "applied": changed,
            "note": apply_note,
        },
    }

    analyses = [analysis for analysis in coach.get("analyses", []) if analysis.get("activity_id") != latest.get("id")]
    analyses.insert(0, entry)
    coach["analyses"] = analyses[:30]
    coach["last_run_utc"] = now_utc
    decision_plan = planning_window(plan, upcoming)
    coach["last_trigger_hash"] = stable_hash(
        decision_plan,
        latest,
        local_date,
        strategy,
        wellness_context,
        rolling_context,
        performance_context,
    )
    coach["contract_version"] = COACH_CONTRACT_VERSION
    COACH_FILE.write_text(json.dumps(coach, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    wellness_note = "med privat återhämtningskontext" if wellness_context.get("daily") else "utan återhämtningskontext"
    print(
        f"AI coach: analyserade aktivitet {latest.get('id')} med {MODEL} {wellness_note}. "
        f"Fulfilled={sorted(fulfilled_dates)} ready_targets={ready_dates} deferred={deferred_dates}. {apply_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
