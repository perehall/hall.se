"""Structured append-only coach decision ledger.

This layer does not decide training. It records the already-made planning
decision in a stable, inspectable contract:

trigger -> capability state -> coach decision -> evidence -> affected workouts.

The adaptive planner remains authoritative for what changes. The ledger makes
that decision auditable without inferring new physiology from presentation
strings.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

from canonical_plan import planned_workouts as canonical_planned_workouts


COACH_DECISION_SCHEMA_VERSION = 1
ALLOWED_DECISIONS = {
    "no_change",
    "fulfill",
    "hold",
    "progress",
    "reduce",
    "reschedule",
    "replace",
}
ALLOWED_TRIGGERS = {
    "completed_training",
    "capability_state_update",
    "live_replan",
    "microcycle_planning",
    "profile_regeneration",
}


def _canonical_hash(payload) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _state_snapshot(athlete_state: dict, capability: str) -> dict:
    row = (
        ((athlete_state.get("capability_states") or {}).get("by_capability") or {})
        .get(capability)
        or {}
    )
    return {
        "evidence_state": row.get("evidence_state"),
        "progression_state": row.get("progression_state"),
        "progression_ready": bool(row.get("progression_ready") is True),
        "progression_reason_code": row.get("progression_reason_code"),
        "progression_reason": row.get("progression_reason"),
        "demonstrated_value": row.get("demonstrated_value"),
        "tolerated_value": row.get("tolerated_value"),
        "absorbed_value": row.get("absorbed_value"),
    }


def _latest_capability_state(entries: list[dict], capability: str):
    for row in reversed(entries or []):
        if str(row.get("capability") or "") != capability:
            continue
        state = row.get("new_state")
        if isinstance(state, dict):
            return deepcopy(state)
    return None


def _workout_key(row: dict) -> str:
    explicit = str(row.get("workout_key") or "").strip()
    if explicit:
        return explicit
    slot = str(row.get("microcycle_slot") or "").strip()
    if slot:
        return slot
    recipe = str(row.get("recipe_key") or "").strip()
    sport = str(row.get("sport") or "").strip().lower()
    stimuli = ",".join(sorted(str(value) for value in (row.get("stimuli") or [])))
    return "|".join((recipe, sport, stimuli))


def _workout_snapshot(row: dict | None):
    if not isinstance(row, dict):
        return None
    return {
        "workout_key": _workout_key(row),
        "date": row.get("date"),
        "sport": row.get("sport"),
        "recipe_key": row.get("recipe_key"),
        "session": row.get("session"),
        "stimuli": [
            str(value) for value in (row.get("stimuli") or [])
            if str(value).strip()
        ],
        "planning_status": row.get("planning_status"),
    }


def _identity_candidates(rows: list[dict]):
    by_key = {}
    for index, row in enumerate(rows):
        key = _workout_key(row)
        by_key.setdefault(key, []).append(index)
    return by_key


def diff_planned_workouts(before_plan: dict, after_plan: dict) -> list[dict]:
    """Return semantic plan changes without inventing workout intent."""
    before = list(
        canonical_planned_workouts(
            before_plan or {},
            context="coach-decision before plan",
        )
    )
    after = list(
        canonical_planned_workouts(
            after_plan or {},
            context="coach-decision after plan",
        )
    )
    after_by_key = _identity_candidates(after)
    used_before = set()
    used_after = set()
    changes = []

    # First pass: stable workout identity. This is the only basis on which a
    # calendar move may be called a reschedule.
    for old_index, old in enumerate(before):
        key = _workout_key(old)
        matches = [
            index for index in after_by_key.get(key, [])
            if index not in used_after
        ]
        if not matches:
            continue
        index = min(
            matches,
            key=lambda value: abs(
                (
                    date.fromisoformat(str(after[value].get("date")))
                    - date.fromisoformat(str(old.get("date")))
                ).days
            )
            if old.get("date") and after[value].get("date")
            else 999,
        )
        new = after[index]
        used_before.add(old_index)
        used_after.add(index)
        old_snapshot = _workout_snapshot(old)
        new_snapshot = _workout_snapshot(new)
        if old_snapshot == new_snapshot:
            continue
        moved = old_snapshot["date"] != new_snapshot["date"]
        recipe_changed = (
            old_snapshot["recipe_key"] != new_snapshot["recipe_key"]
            or old_snapshot["session"] != new_snapshot["session"]
        )
        change_type = (
            "replaced"
            if recipe_changed
            else "rescheduled"
            if moved
            else "modified"
        )
        changes.append(
            {
                "change_type": change_type,
                "before": old_snapshot,
                "after": new_snapshot,
            }
        )

    # Second pass: a unique same-day, same-sport, overlapping-stimulus pair may
    # be called a replacement. This supports deliberate recipe changes while
    # failing closed for ambiguous multipass days.
    for old_index, old in enumerate(before):
        if old_index in used_before:
            continue
        old_snapshot = _workout_snapshot(old)
        candidates = []
        old_stimuli = set(old_snapshot.get("stimuli") or [])
        for new_index, new in enumerate(after):
            if new_index in used_after:
                continue
            new_snapshot = _workout_snapshot(new)
            new_stimuli = set(new_snapshot.get("stimuli") or [])
            if old_snapshot.get("date") != new_snapshot.get("date"):
                continue
            if str(old_snapshot.get("sport") or "").lower() != str(
                new_snapshot.get("sport") or ""
            ).lower():
                continue
            if not old_stimuli.intersection(new_stimuli):
                continue
            candidates.append((new_index, new_snapshot))
        if len(candidates) != 1:
            continue
        new_index, new_snapshot = candidates[0]
        used_before.add(old_index)
        used_after.add(new_index)
        changes.append(
            {
                "change_type": "replaced",
                "before": old_snapshot,
                "after": new_snapshot,
            }
        )

    for old_index, old in enumerate(before):
        if old_index in used_before:
            continue
        changes.append(
            {
                "change_type": "removed",
                "before": _workout_snapshot(old),
                "after": None,
            }
        )

    for new_index, row in enumerate(after):
        if new_index in used_after:
            continue
        changes.append(
            {
                "change_type": "added",
                "before": None,
                "after": _workout_snapshot(row),
            }
        )
    return changes


def _capabilities_for_slot(slot: dict, catalog: dict) -> set[str]:
    recipe = (
        (catalog.get("recipes") or {}).get(str(slot.get("recipe_key") or ""))
        or {}
    )
    return {
        str(value)
        for value in (recipe.get("stimuli") or [])
        if str(value).strip()
    }


def _change_capabilities(change: dict) -> set[str]:
    values = set()
    for side in ("before", "after"):
        row = change.get(side)
        if not isinstance(row, dict):
            continue
        values.update(
            str(value)
            for value in (row.get("stimuli") or [])
            if str(value).strip()
        )
    return values


def _decision_for_capability(
    capability: str,
    *,
    completed: set[str],
    slot: dict | None,
    changes: list[dict],
):
    if capability in completed:
        return "fulfill", "completed_capability_credit"

    action = str((slot or {}).get("action") or "")
    if action == "progress":
        return "progress", "progression_ready_and_planned"
    if action == "reduce":
        return "reduce", "planner_reduce"

    types = {str(row.get("change_type") or "") for row in changes}
    if "replaced" in types:
        return "replace", "plan_reconciled_replace"
    if "rescheduled" in types:
        return "reschedule", "plan_reconciled_move"

    if action in {"consolidate", "establish"}:
        return "hold", "microcycle_hold"
    return "no_change", "no_material_change"


def _trigger_for_capability(
    capability: str,
    *,
    completed_refs: dict,
    previous_state,
    new_state,
    active_replan: bool,
    explicit_profile_generation: bool,
):
    if completed_refs.get(capability):
        return "completed_training"
    if previous_state is not None and previous_state != new_state:
        return "capability_state_update"
    if explicit_profile_generation:
        return "profile_regeneration"
    if active_replan:
        return "live_replan"
    return "microcycle_planning"


def _summary(label: str, decision: str, new_state: dict, affected: list[dict]) -> str:
    state = str(new_state.get("evidence_state") or "okänd evidens")
    if decision == "fulfill":
        return (
            f"{label}: genomfört stimulus har krediterats. "
            f"Capability-state är {state}; återstående plan har granskats mot utfallet."
        )
    if decision == "progress":
        return (
            f"{label}: progression materialiseras eftersom plannerbeslutet är progress "
            "och verifierad capability-state tillåter steget."
        )
    if decision == "reduce":
        return f"{label}: belastningen reduceras i den materialiserade mikrocykeln."
    if decision == "reschedule":
        return f"{label}: pass flyttas efter omprövning av aktuell mikrocykel."
    if decision == "replace":
        return f"{label}: passkaraktär eller recept ersätts efter omprövning av mikrocykeln."
    if decision == "hold":
        reason = str(new_state.get("progression_reason") or "").strip()
        return (
            f"{label}: progression hålls."
            + (f" {reason}" if reason else "")
        )
    return (
        f"{label}: inget materiellt planbeslut ändras."
        + (f" {len(affected)} workout-förändringar registrerades." if affected else "")
    )


def build_coach_decisions(
    *,
    today,
    target_start,
    before_plan: dict,
    after_plan: dict,
    micro: dict,
    catalog: dict,
    athlete_state: dict,
    completed_context: dict | None,
    previous_entries: list[dict] | None = None,
    capability_labels: dict | None = None,
    active_replan: bool = False,
    micro_changed: bool = False,
    explicit_profile_generation: bool = False,
    generated_at_utc: str | None = None,
) -> list[dict]:
    """Build deterministic audit decisions from already-resolved planner state."""
    completed_context = completed_context or {}
    previous_entries = previous_entries or []
    capability_labels = capability_labels or {}
    completed = set(completed_context.get("direct_capabilities") or [])
    completed.update(completed_context.get("planning_credits") or [])
    completed_refs = {
        str(key): [str(value) for value in (values or [])]
        for key, values in (completed_context.get("capability_refs") or {}).items()
    }
    for capability in completed:
        completed_refs.setdefault(
            capability,
            [str(value) for value in (completed_context.get("activity_refs") or [])],
        )

    changes = diff_planned_workouts(before_plan, after_plan)
    micro_slots = list(micro.get("slots") or [])
    capabilities = set(completed)
    for slot in micro_slots:
        capabilities.update(_capabilities_for_slot(slot, catalog))
    for change in changes:
        capabilities.update(_change_capabilities(change))

    if not (
        micro_changed
        or active_replan
        or explicit_profile_generation
        or completed
        or changes
    ):
        return []

    now = generated_at_utc or datetime.now(timezone.utc).isoformat()
    rows = []
    for capability in sorted(capabilities):
        new_state = _state_snapshot(athlete_state, capability)
        previous_state = _latest_capability_state(previous_entries, capability)
        matching_slots = [
            slot
            for slot in micro_slots
            if capability in _capabilities_for_slot(slot, catalog)
        ]
        slot = matching_slots[0] if len(matching_slots) == 1 else None
        affected = [
            deepcopy(change)
            for change in changes
            if capability in _change_capabilities(change)
        ]
        decision, reason_code = _decision_for_capability(
            capability,
            completed=completed,
            slot=slot,
            changes=affected,
        )
        if decision == "hold" and new_state.get("progression_reason_code"):
            reason_code = str(new_state["progression_reason_code"])
        state_changed = previous_state is not None and previous_state != new_state
        meaningful = bool(
            capability in completed
            or affected
            or slot
            or state_changed
        )
        if not meaningful:
            continue

        trigger = _trigger_for_capability(
            capability,
            completed_refs=completed_refs,
            previous_state=previous_state,
            new_state=new_state,
            active_replan=active_replan,
            explicit_profile_generation=explicit_profile_generation,
        )
        evidence = {
            "activity_refs": completed_refs.get(capability, []),
            "microcycle_source_hash": micro.get("source_hash"),
            "microcycle_week_key": micro.get("week_key"),
            "slot_action": (slot or {}).get("action"),
            "slot_recipe_key": (slot or {}).get("recipe_key"),
            "slot_evidence_refs": list((slot or {}).get("evidence_refs") or []),
            "capability_reason_code": new_state.get("progression_reason_code"),
            "completed_context_signature": _canonical_hash(
                {
                    "activity_refs": sorted(
                        str(value)
                        for value in (completed_context.get("activity_refs") or [])
                    ),
                    "capability_refs": completed_refs,
                }
            ),
        }
        label = capability_labels.get(capability) or capability
        stable = {
            "week_start": target_start.isoformat()
            if isinstance(target_start, date)
            else str(target_start),
            "capability": capability,
            "trigger": trigger,
            "decision": decision,
            "reason_code": reason_code,
            "previous_state": previous_state,
            "new_state": new_state,
            "evidence": evidence,
            "affected_workouts": affected,
        }
        rows.append(
            {
                "schema_version": COACH_DECISION_SCHEMA_VERSION,
                "decision_id": _canonical_hash(stable),
                "generated_at_utc": now,
                "planning_date": today.isoformat()
                if isinstance(today, date)
                else str(today),
                **stable,
                "summary": _summary(label, decision, new_state, affected),
            }
        )
    return rows


def validate_coach_decision(row: dict) -> None:
    required = {
        "schema_version",
        "decision_id",
        "generated_at_utc",
        "planning_date",
        "week_start",
        "capability",
        "trigger",
        "decision",
        "reason_code",
        "previous_state",
        "new_state",
        "evidence",
        "affected_workouts",
        "summary",
    }
    missing = sorted(required - set(row))
    if missing:
        raise ValueError("coach decision saknar fält: " + ", ".join(missing))
    if int(row.get("schema_version") or 0) != COACH_DECISION_SCHEMA_VERSION:
        raise ValueError("coach decision har fel schema_version")
    if row.get("decision") not in ALLOWED_DECISIONS:
        raise ValueError(f"otillåtet coachbeslut: {row.get('decision')!r}")
    if row.get("trigger") not in ALLOWED_TRIGGERS:
        raise ValueError(f"otillåten coachtrigger: {row.get('trigger')!r}")
    if not str(row.get("decision_id") or "").strip():
        raise ValueError("coach decision saknar decision_id")
    if not isinstance(row.get("new_state"), dict):
        raise ValueError("coach decision new_state måste vara objekt")
    if not isinstance(row.get("evidence"), dict):
        raise ValueError("coach decision evidence måste vara objekt")
    if not isinstance(row.get("affected_workouts"), list):
        raise ValueError("coach decision affected_workouts måste vara lista")


def load_coach_decision_ledger(path: Path) -> dict:
    if not path.exists():
        return {
            "schema_version": COACH_DECISION_SCHEMA_VERSION,
            "append_only": True,
            "entries": [],
        }
    document = json.loads(path.read_text(encoding="utf-8"))
    if int(document.get("schema_version") or 0) != COACH_DECISION_SCHEMA_VERSION:
        raise ValueError("coach decision ledger har fel schema_version")
    if document.get("append_only") is not True:
        raise ValueError("coach decision ledger måste vara append_only")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise ValueError("coach decision ledger entries måste vara lista")
    for row in entries:
        validate_coach_decision(row)
    return document


def append_coach_decisions(path: Path, decisions: list[dict]) -> int:
    document = load_coach_decision_ledger(path)
    entries = list(document.get("entries") or [])
    by_id = {
        str(row.get("decision_id")): row
        for row in entries
        if str(row.get("decision_id") or "").strip()
    }
    appended = 0
    for row in decisions:
        validate_coach_decision(row)
        decision_id = str(row["decision_id"])
        existing = by_id.get(decision_id)
        if existing is not None:
            # Idempotent reruns are allowed; mutating a historical decision is not.
            comparable_existing = {
                key: value for key, value in existing.items()
                if key != "generated_at_utc"
            }
            comparable_new = {
                key: value for key, value in row.items()
                if key != "generated_at_utc"
            }
            if comparable_existing != comparable_new:
                raise ValueError(
                    f"append-only coach decision conflict for {decision_id}"
                )
            continue
        entries.append(deepcopy(row))
        by_id[decision_id] = row
        appended += 1

    document["entries"] = entries
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return appended
