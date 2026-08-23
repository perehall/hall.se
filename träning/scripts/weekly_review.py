#!/usr/bin/env python3
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from coach_rules import activity_family, activity_local_date, planned_families
from week_review_contracts import (
    REVIEW_CONTRACT_VERSION,
    REVIEW_SCHEMA_VERSION,
    validate_week_assessment,
    validate_week_review_document,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PLAN_FILE = DATA_DIR / "plan.json"
ACTIVITIES_FILE = DATA_DIR / "activities.json"
WEEKS_DIR = DATA_DIR / "weeks"
REVIEWS_DIR = DATA_DIR / "week_reviews"
PROMPT_FILE = ROOT / "week_review_prompt.md"

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
INITIAL_REVIEW_GRACE_DAYS = 3

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "worked": {"type": "array", "items": {"type": "string"}},
        "not_as_planned": {"type": "array", "items": {"type": "string"}},
        "load_continuity": {"type": "string"},
        "key_lesson": {"type": "string"},
        "next_week_implication": {"type": "string"},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "worked",
        "not_as_planned",
        "load_continuity",
        "key_lesson",
        "next_week_implication",
        "uncertainties",
    ],
}


def load_json(path, fallback=None):
    if not path.exists():
        return {} if fallback is None else fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def week_key_from_plan(plan):
    meta = plan.get("meta") or {}
    start_text = meta.get("week_start")
    end_text = meta.get("week_end")
    if not start_text or not end_text:
        raise RuntimeError("Veckoutvärdering: plan.meta saknar week_start/week_end")
    start = date.fromisoformat(start_text)
    end = date.fromisoformat(end_text)
    if (end - start).days != 6:
        raise RuntimeError("Veckoutvärdering: planen omfattar inte exakt sju dagar")
    iso = start.isocalendar()
    if end.isocalendar()[:2] != iso[:2]:
        raise RuntimeError("Veckoutvärdering: week_start/week_end ligger inte i samma ISO-vecka")
    return f"{iso.year}-W{iso.week:02d}", start_text, end_text


def activity_duration_s(activity):
    elapsed = activity.get("elapsed_time_s")
    if elapsed is not None:
        return max(0, int(elapsed))
    return max(0, int(activity.get("moving_time_s") or 0))


def activity_label(activity):
    return activity.get("display_label") or activity.get("sport_type") or "Aktivitet"


def source_activities_for_week(week_start, week_end, primary, fallback=None):
    merged = {}
    for activity in fallback or []:
        local = activity_local_date(activity)
        if local and week_start <= local <= week_end and activity.get("id") is not None:
            merged[str(activity["id"])] = activity
    for activity in primary or []:
        local = activity_local_date(activity)
        if local and week_start <= local <= week_end and activity.get("id") is not None:
            merged[str(activity["id"])] = activity
    return sorted(
        merged.values(),
        key=lambda item: (activity_local_date(item), item.get("start_date") or "", str(item.get("id"))),
    )


def plan_outcome(day, day_activities):
    sport = str(day.get("sport") or "").strip().lower()
    families = planned_families(day)
    matching = [activity for activity in day_activities if activity_family(activity) in families]

    if sport in {"rest", "open"}:
        outcome = "no_activity_planned" if not day_activities else "unplanned_activity"
    elif matching:
        outcome = "fulfilled"
    elif day_activities:
        outcome = "different_activity"
    elif day.get("status") == "completed":
        outcome = "completed_without_synced_activity"
    else:
        outcome = "not_completed"
    return outcome, matching


def build_week_facts(plan, activities):
    week_key, week_start, week_end = week_key_from_plan(plan)
    week_activities = source_activities_for_week(week_start, week_end, activities)
    by_date = {}
    for activity in week_activities:
        by_date.setdefault(activity_local_date(activity), []).append(activity)

    total_time = 0
    training_time = 0
    recreation_time = 0
    training_count = 0
    recreation_count = 0
    sport_rows = {}
    activity_rows = []

    for activity in week_activities:
        duration = activity_duration_s(activity)
        classification = activity.get("classification") or "training"
        label = activity_label(activity)
        total_time += duration
        if classification == "recreation":
            recreation_count += 1
            recreation_time += duration
        else:
            training_count += 1
            training_time += duration

        row = sport_rows.setdefault(label, {"label": label, "activity_count": 0, "time_s": 0})
        row["activity_count"] += 1
        row["time_s"] += duration

        activity_rows.append(
            {
                "id": activity.get("id"),
                "date": activity_local_date(activity),
                "label": label,
                "sport_type": activity.get("sport_type"),
                "classification": classification,
                "distance_m": activity.get("distance_m"),
                "elapsed_time_s": activity.get("elapsed_time_s"),
                "moving_time_s": activity.get("moving_time_s"),
                "total_elevation_gain_m": activity.get("total_elevation_gain_m"),
                "average_heartrate": activity.get("average_heartrate"),
                "max_heartrate": activity.get("max_heartrate"),
                "user_report": activity.get("user_report"),
                "source_sport_type": activity.get("source_sport_type"),
                "garmin_activity_type": activity.get("garmin_activity_type"),
            }
        )

    outcomes = []
    outcome_counts = {}
    for day in plan.get("days") or []:
        actuals = by_date.get(day.get("date"), [])
        outcome, matching = plan_outcome(day, actuals)
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        outcomes.append(
            {
                "date": day.get("date"),
                "label": day.get("label"),
                "planned_sport": day.get("sport"),
                "recorded_session": day.get("session"),
                "original_session": day.get("original_session"),
                "status": day.get("status"),
                "outcome": outcome,
                "actual_activity_ids": [activity.get("id") for activity in actuals],
                "actual_labels": [activity_label(activity) for activity in actuals],
                "matching_activity_ids": [activity.get("id") for activity in matching],
                "context": {
                    "reason": day.get("reason"),
                    "coach_adjustment": day.get("coach_adjustment"),
                },
            }
        )

    return {
        "week_key": week_key,
        "week_start": week_start,
        "week_end": week_end,
        "activity_count": len(week_activities),
        "training_activity_count": training_count,
        "recreation_activity_count": recreation_count,
        "active_days": len(by_date),
        "total_activity_time_s": total_time,
        "training_time_s": training_time,
        "recreation_time_s": recreation_time,
        "by_sport": sorted(sport_rows.values(), key=lambda item: (-item["time_s"], item["label"])),
        "activities": activity_rows,
        "plan_outcomes": outcomes,
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "plan_meta": {
            "title": (plan.get("meta") or {}).get("title"),
            "principle": (plan.get("meta") or {}).get("principle"),
        },
    }


def source_hash(plan, facts):
    payload = {
        "review_contract_version": REVIEW_CONTRACT_VERSION,
        "plan": plan,
        "facts": facts,
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
                raise RuntimeError(
                    f"OpenAI avböjde veckoutvärderingen: {part.get('refusal', 'okänd orsak')}"
                )
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    if not chunks:
        raise RuntimeError("Veckoutvärdering: OpenAI-svaret saknar output_text")
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
                "name": "training_week_review",
                "strict": True,
                "schema": REVIEW_SCHEMA,
            },
        },
        "max_output_tokens": max_tokens,
        "store": False,
    }


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


def call_openai(system_prompt, input_data, *, request_fn=None, sleep_fn=None, model=None):
    request_fn = request_fn or request_openai
    sleep_fn = sleep_fn or time.sleep
    token_budgets = [2500, 5000]
    for attempt, max_tokens in enumerate(token_budgets, start=1):
        body = build_openai_body(system_prompt, input_data, max_tokens, model=model)
        try:
            response = request_fn(body)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < len(token_budgets):
                sleep_fn(4 * attempt)
                continue
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Veckoutvärdering: OpenAI HTTP {exc.code}: {details[:1200]}") from exc

        status = response.get("status")
        if status == "completed":
            try:
                parsed = json.loads(extract_output_text(response))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Veckoutvärdering: OpenAI JSON kunde inte parsas: {exc}") from exc
            validate_week_assessment(parsed)
            return parsed
        if status == "incomplete":
            reason = (response.get("incomplete_details") or {}).get("reason")
            if reason in {"max_output_tokens", "max_tokens"} and attempt < len(token_budgets):
                continue
            raise RuntimeError(
                f"Veckoutvärdering: OpenAI-svaret blev incomplete: {reason or 'okänd orsak'}"
            )
        if status == "failed":
            error = response.get("error") or {}
            raise RuntimeError(
                f"Veckoutvärdering: OpenAI-svaret misslyckades: {error.get('message') or error}"
            )
        raise RuntimeError(f"Veckoutvärdering: oväntad OpenAI-status {status!r}")
    raise RuntimeError("Veckoutvärdering: kunde inte få ett komplett strukturerat svar")


def candidate_sources(current_plan, current_activities):
    candidates = {}
    if current_plan:
        key, start, end = week_key_from_plan(current_plan)
        candidates[key] = {
            "plan": current_plan,
            "activities": source_activities_for_week(start, end, current_activities),
        }

    if WEEKS_DIR.exists():
        for path in sorted(WEEKS_DIR.glob("????-W??.json")):
            snapshot = load_json(path, {})
            plan = snapshot.get("plan") or {}
            if not plan:
                continue
            key, start, end = week_key_from_plan(plan)
            if key in candidates:
                continue
            merged = source_activities_for_week(
                start,
                end,
                current_activities,
                fallback=snapshot.get("activities") or [],
            )
            candidates[key] = {"plan": plan, "activities": merged}
    return candidates


def should_process(week_end, today_local, review_exists):
    days_since_end = (today_local - date.fromisoformat(week_end)).days
    if days_since_end <= 0:
        return False
    if review_exists:
        return True
    return days_since_end <= INITIAL_REVIEW_GRACE_DAYS


def main(*, today_local=None, request_fn=None):
    current_plan = load_json(PLAN_FILE, {})
    activities_state = load_json(ACTIVITIES_FILE, {"activities": []})
    current_activities = activities_state.get("activities") or []
    timezone_name = (current_plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    tz = ZoneInfo(timezone_name)
    today = today_local or datetime.now(tz).date()
    if isinstance(today, str):
        today = date.fromisoformat(today)

    candidates = candidate_sources(current_plan, current_activities)
    if not candidates:
        print("Veckoutvärdering: inga veckor att bedöma.")
        return 0

    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    generated = 0
    unchanged = 0
    skipped = 0

    for key in sorted(candidates):
        source = candidates[key]
        plan = source["plan"]
        _, _, week_end = week_key_from_plan(plan)
        review_path = REVIEWS_DIR / f"{key}.json"
        previous = load_json(review_path, {})
        if not should_process(week_end, today, bool(previous)):
            skipped += 1
            continue

        facts = build_week_facts(plan, source["activities"])
        digest = source_hash(plan, facts)
        if previous.get("source_hash") == digest:
            unchanged += 1
            continue

        if not os.environ.get("OPENAI_API_KEY", "").strip() and request_fn is None:
            print(
                f"Veckoutvärdering {key}: OPENAI_API_KEY saknas; behåller eventuell tidigare review."
            )
            skipped += 1
            continue

        assessment = call_openai(
            prompt,
            {
                "week": facts,
                "instruction": (
                    "Tolka endast det deterministiska faktalagret. Ändra eller rekonstruera inte siffror. "
                    "Gör ingen numerisk poängsättning och skriv inte om nästa veckas plan."
                ),
            },
            request_fn=request_fn,
        )
        now_utc = datetime.now(timezone.utc).isoformat()
        document = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "contract_version": REVIEW_CONTRACT_VERSION,
            "week_key": key,
            "week_start": facts["week_start"],
            "week_end": facts["week_end"],
            "source_hash": digest,
            "generated_at_utc": now_utc,
            "model": MODEL,
            "facts": facts,
            "assessment": assessment,
        }
        validate_week_review_document(document)
        write_json(review_path, document)
        generated += 1
        print(f"Veckoutvärdering {key}: genererad med {MODEL}.")

    print(
        f"Veckoutvärdering OK: generated={generated} unchanged={unchanged} skipped={skipped}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
