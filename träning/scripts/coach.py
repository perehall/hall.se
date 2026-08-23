#!/usr/bin/env python3
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from coach_rules import (
    allowed_target_dates,
    canonical_facts,
    normalize_assessment_confidence,
    normalize_no_remaining_plan,
    plan_for_coach,
    validate_plan_action,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
COACH_FILE = ROOT / "data" / "coach.json"
PROMPT_FILE = ROOT / "coach_prompt.md"

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
COACH_CONTRACT_VERSION = 3

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
                "requires_approval": {"type": "boolean"},
            },
            "required": ["action", "target_date", "reason", "recommendation", "requires_approval"],
        },
    },
    "required": ["assessment", "plan_action"],
}


def load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def stable_hash(plan, latest_activity, local_date):
    payload = {
        "coach_contract_version": COACH_CONTRACT_VERSION,
        "plan": plan,
        "latest_activity": latest_activity,
        "local_date": local_date,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


def apply_conservative_action(plan, action, *, now_utc=None):
    kind = action.get("action")
    target = action.get("target_date") or ""
    if kind not in ("reduce", "rest") or not target:
        return False, "Ingen automatisk planändring."

    day = next((d for d in plan.get("days", []) if d.get("date") == target), None)
    if not day or day.get("status") == "completed":
        return False, "Måldagen saknas eller är redan genomförd."

    reason = action.get("reason", "")
    if "original_session" not in day:
        day["original_session"] = day.get("session", "")
    applied_at = now_utc or datetime.now(timezone.utc).isoformat()
    day["auto_coach"] = {
        "action": kind,
        "reason": reason,
        "applied_at_utc": applied_at,
    }

    if kind == "rest":
        day["session"] = "Vila eller mycket lätt"
        day["sport"] = "rest"
        day["status"] = "conditional"
        day["reason"] = f"AI-coach: {reason}"
    elif kind == "reduce":
        if day.get("status") in ("planned", "preliminary"):
            day["status"] = "conditional"
        day["coach_adjustment"] = f"Skala ned passet. {action.get('recommendation', '')}".strip()

    return True, f"Konservativ ändring applicerad på {target}: {kind}."


def main():
    plan = load_json(PLAN_FILE, {})
    activities_state = load_json(ACTIVITIES_FILE, {"activities": []})
    coach = load_json(COACH_FILE, {"analyses": [], "last_trigger_hash": None, "last_run_utc": None})
    activities = activities_state.get("activities", [])

    if not activities:
        print("AI coach: inga aktiviteter att analysera.")
        return 0

    latest = max(activities, key=lambda activity: activity.get("start_date") or "")
    tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
    local_date = datetime.now(tz).date().isoformat()
    trigger_hash = stable_hash(plan, latest, local_date)

    if coach.get("last_trigger_hash") == trigger_hash:
        print("AI coach: inget nytt underlag; hoppar över API-anrop.")
        return 0

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("AI coach: OPENAI_API_KEY saknas; hoppar över AI-analys.")
        return 0

    latest_date = (latest.get("start_date_local") or latest.get("start_date") or "")[:10]
    recent = sorted(activities, key=lambda activity: activity.get("start_date") or "", reverse=True)[:10]
    coach_plan, fulfilled_dates = plan_for_coach(plan, activities)
    allowed_dates = allowed_target_dates(plan, activities, local_date)

    input_data = {
        "today_local": local_date,
        "latest_activity": latest,
        "latest_activity_date": latest_date,
        "recent_activities": recent,
        "current_plan": coach_plan,
        "fulfilled_plan_dates": sorted(fulfilled_dates),
        "allowed_target_dates": allowed_dates,
        "instruction": (
            "Analysera senaste passet mot faktisk närbelastning och aktuell plan. Kontrollera särskilt "
            "föregående och kommande 2–3 dagar. Dagar i fulfilled_plan_dates är redan genomförda och "
            "får aldrig ordineras igen. target_date får endast väljas ur allowed_target_dates. Om listan "
            "är tom ska target_date vara tomt och ingen ytterligare träning ordineras idag. Föreslå endast "
            "konservativ automatisk ändring; allt som kan innebära ökad belastning ska vara review och "
            "kräva godkännande."
        ),
    }

    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    result = call_openai(system_prompt, input_data)
    result["assessment"] = normalize_assessment_confidence(result["assessment"])
    result["assessment"]["facts"] = canonical_facts(latest, latest_date, fulfilled_dates)
    result["plan_action"] = normalize_no_remaining_plan(
        result["plan_action"],
        allowed_dates=allowed_dates,
        latest_date=latest_date,
        fulfilled_dates=fulfilled_dates,
    )
    validate_plan_action(result["plan_action"], allowed_dates)

    changed, apply_note = apply_conservative_action(plan, result["plan_action"])
    if changed:
        PLAN_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    now_utc = datetime.now(timezone.utc).isoformat()
    entry = {
        "activity_id": latest.get("id"),
        "activity_date": latest_date,
        "activity_name": latest.get("name"),
        "generated_at_utc": now_utc,
        "model": MODEL,
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
    coach["last_trigger_hash"] = stable_hash(plan, latest, local_date)
    coach["contract_version"] = COACH_CONTRACT_VERSION
    COACH_FILE.write_text(json.dumps(coach, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"AI coach: analyserade aktivitet {latest.get('id')} med {MODEL}. "
        f"Fulfilled={sorted(fulfilled_dates)} allowed_targets={allowed_dates}. {apply_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
