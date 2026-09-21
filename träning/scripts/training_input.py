#!/usr/bin/env python3
"""Apply constrained GUI training input to canonical user-controlled training facts.

The browser may submit either an explicit safe operation or NATURAL_LANGUAGE.
A small model is allowed to classify natural language into an allowlisted
operation, but it never writes a plan or invents workout facts. The user's
original text is persisted verbatim as first-class evidence.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
OVERRIDES_FILE = ROOT / "data" / "activity_overrides.json"

MODEL = os.environ.get("TRAINING_INPUT_MODEL", os.environ.get("OPENAI_MODEL", "gpt-5-mini"))

EXPLICIT_OPERATIONS = {
    "ADD_FEEDBACK",
    "UPDATE_COMPLETED_WORKOUT",
    "ADD_SPONTANEOUS_WORKOUT",
    "REPORT_PAIN",
    "REPORT_FATIGUE",
}
INPUT_OPERATIONS = EXPLICIT_OPERATIONS | {"NATURAL_LANGUAGE"}
FEELING_CODES = {
    "fresh": "Pigg",
    "tired": "Trött",
    "strong_legs": "Starka ben",
    "heavy_legs": "Tunga ben",
    "pain": "Smärta",
    "could_do_more": "Kunde gjort mer",
}
MAX_TEXT = 800

CLASSIFIER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "operation": {"type": "string", "enum": sorted(EXPLICIT_OPERATIONS)},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["operation", "confidence"],
}


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, document: dict) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError("Träningsinput måste vara ett JSON-objekt.")

    allowed = {"operation", "activity_id", "text", "rpe", "feeling", "event_key", "submitted_at", "source"}
    extra = set(payload) - allowed
    if extra:
        raise RuntimeError(f"Träningsinput innehåller otillåtna fält: {sorted(extra)!r}")

    operation = str(payload.get("operation") or "").strip().upper()
    if operation not in INPUT_OPERATIONS:
        raise RuntimeError(f"Otillåten träningsoperation: {operation!r}")

    activity_id = payload.get("activity_id")
    if not isinstance(activity_id, int) or isinstance(activity_id, bool) or activity_id <= 0:
        raise RuntimeError("activity_id måste vara ett positivt heltal.")

    text = payload.get("text")
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise RuntimeError("text måste vara en sträng.")
    text = text.strip()
    if len(text) > MAX_TEXT:
        raise RuntimeError(f"text får vara högst {MAX_TEXT} tecken.")

    rpe = payload.get("rpe")
    if rpe is not None:
        if not isinstance(rpe, int) or isinstance(rpe, bool) or not 1 <= rpe <= 10:
            raise RuntimeError("rpe måste vara ett heltal 1–10.")

    feeling = payload.get("feeling") or []
    if not isinstance(feeling, list) or len(feeling) > 6:
        raise RuntimeError("feeling måste vara en lista med högst sex värden.")
    normalized_feeling = []
    for value in feeling:
        code = str(value or "").strip()
        if code not in FEELING_CODES:
            raise RuntimeError(f"Otillåtet feeling-värde: {code!r}")
        if code not in normalized_feeling:
            normalized_feeling.append(code)

    if not text and rpe is None and not normalized_feeling:
        raise RuntimeError("Träningsinput saknar innehåll.")

    return {
        "operation": operation,
        "activity_id": activity_id,
        "text": text,
        "rpe": rpe,
        "feeling": normalized_feeling,
    }


def deterministic_operation(payload: dict) -> str:
    feeling = set(payload.get("feeling") or [])
    text = str(payload.get("text") or "").lower()

    if "pain" in feeling or re.search(r"\b(ont|smärta|smärtade|känning|skadad|skada)\b", text):
        return "REPORT_PAIN"
    if "tired" in feeling or re.search(r"\b(trött|sliten|utmattad|seg|urlakad)\b", text):
        return "REPORT_FATIGUE"
    if re.search(r"\b(spontan|spontant|separat pass|extra pass)\b", text):
        return "ADD_SPONTANEOUS_WORKOUT"
    if re.search(r"\b(blev|körde|gjorde)\b.*\b(i stället|istället|snarare|än planerat)\b", text):
        return "UPDATE_COMPLETED_WORKOUT"
    if re.search(r"\b(ändring|ändrade|korrigera|korrigering)\b", text):
        return "UPDATE_COMPLETED_WORKOUT"
    return "ADD_FEEDBACK"


def extract_output_text(response: dict) -> str:
    chunks = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "refusal":
                raise RuntimeError("Minimodellen avböjde klassificeringen.")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    if not chunks:
        raise RuntimeError("Minimodellen returnerade inget strukturerat svar.")
    return "".join(chunks)


def classify_with_model(payload: dict, activity: dict) -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return deterministic_operation(payload)

    body = {
        "model": MODEL,
        "input": [
            {
                "role": "system",
                "content": (
                    "Du klassificerar användarinput i ett träningssystem. "
                    "Du får endast välja en operation ur schemat. Du får inte coacha, "
                    "ändra träningsplan, hitta på passfakta eller skriva om användarens text. "
                    "UPDATE_COMPLETED_WORKOUT betyder att användaren korrigerar vad som faktiskt gjordes. "
                    "ADD_SPONTANEOUS_WORKOUT betyder att aktiviteten uttryckligen var ett separat/spontant pass. "
                    "REPORT_PAIN och REPORT_FATIGUE används endast när sådant uttrycks. "
                    "I övrigt välj ADD_FEEDBACK."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "text": payload.get("text") or "",
                        "rpe": payload.get("rpe"),
                        "feeling": payload.get("feeling") or [],
                        "activity": {
                            "id": activity.get("id"),
                            "sport_type": activity.get("sport_type"),
                            "display_label": activity.get("display_label"),
                            "start_date_local": activity.get("start_date_local"),
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "reasoning": {"effort": "minimal"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "training_input_intent",
                "strict": True,
                "schema": CLASSIFIER_SCHEMA,
            },
        },
        "max_output_tokens": 200,
        "store": False,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.load(response)
        if result.get("status") != "completed":
            return deterministic_operation(payload)
        parsed = json.loads(extract_output_text(result))
        operation = parsed.get("operation")
        confidence = parsed.get("confidence")
        if operation not in EXPLICIT_OPERATIONS or confidence == "low":
            return deterministic_operation(payload)
        return operation
    except Exception as exc:
        print(f"Träningsinput: minimodell föll tillbaka deterministiskt ({type(exc).__name__}).")
        return deterministic_operation(payload)


def compose_report(payload: dict) -> str:
    parts = []
    text = str(payload.get("text") or "").strip()
    if text:
        parts.append(text.rstrip())

    rpe = payload.get("rpe")
    if isinstance(rpe, int):
        parts.append(f"RPE {rpe}/10.")

    feelings = [FEELING_CODES[code] for code in payload.get("feeling") or []]
    if feelings:
        parts.append("Känsla: " + ", ".join(feelings) + ".")

    return " ".join(parts).strip()


def merge_report(existing: str, incoming: str) -> str:
    existing = str(existing or "").strip()
    incoming = str(incoming or "").strip()
    if not existing:
        return incoming
    if not incoming or incoming in existing:
        return existing
    return existing.rstrip() + " " + incoming


def activity_by_id(activities: dict, activity_id: int) -> dict:
    for activity in activities.get("activities") or []:
        if activity.get("id") == activity_id:
            return activity
    raise RuntimeError(f"activity_id {activity_id} finns inte i activities.json.")


def apply_to_documents(payload: dict, activities: dict, overrides: dict, *, classify_fn=None) -> tuple[dict, str]:
    normalized = validate_payload(payload)
    activity = activity_by_id(activities, normalized["activity_id"])

    operation = normalized["operation"]
    if operation == "NATURAL_LANGUAGE":
        classify_fn = classify_fn or classify_with_model
        operation = classify_fn(normalized, activity)
    if operation not in EXPLICIT_OPERATIONS:
        raise RuntimeError(f"Klassificeraren gav otillåten operation: {operation!r}")

    report = compose_report(normalized)
    if not report:
        raise RuntimeError("Ingen rapporttext kunde materialiseras.")

    document = json.loads(json.dumps(overrides))
    document.setdefault("schema_version", 1)
    mapping = document.setdefault("overrides", {})
    key = str(normalized["activity_id"])
    override = dict(mapping.get(key) or {})

    override["user_report"] = merge_report(override.get("user_report"), report)
    if operation == "ADD_SPONTANEOUS_WORKOUT":
        override["plan_relation"] = "separate"
        override.setdefault(
            "reason",
            "Explicit GUI-input anger att aktiviteten är ett separat/spontant pass och inte ska ersätta dagens planerade pass.",
        )
    else:
        override.setdefault(
            "reason",
            "Explicit GUI-input från användaren ska behandlas som förstaklassdata i analys och fortsatt planering.",
        )

    mapping[key] = override
    return document, operation


def main() -> int:
    raw = os.environ.get("TRAINING_INPUT_PAYLOAD", "").strip()
    if not raw:
        raise RuntimeError("TRAINING_INPUT_PAYLOAD saknas.")
    payload = json.loads(raw)

    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    overrides = load_json(OVERRIDES_FILE, {"schema_version": 1, "overrides": {}})
    updated, operation = apply_to_documents(payload, activities, overrides)
    write_json(OVERRIDES_FILE, updated)

    print(
        f"Träningsinput OK: {operation} för activity_id={payload.get('activity_id')}; "
        "originalrapport sparad i activity_overrides.json."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
