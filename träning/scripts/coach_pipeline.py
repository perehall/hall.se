#!/usr/bin/env python3
"""Robust orchestration for the AI workout coach.

Raw provider data is preserved, but the model receives deterministic workout
facts and a deterministic planned-versus-actual comparison before interpretation.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import coach as legacy
from coach_output_guard import guard_result
from coach_rules import matching_activity
from workout_plan_context import (
    PLAN_COMPARISON_CONTRACT_VERSION,
    build_plan_comparison,
    plan_comparison_fact,
)


COACH_PIPELINE_CONTRACT_VERSION = 3
SCRIPTS = Path(__file__).resolve().parent
ANALYSIS_CODE_FILES = (
    SCRIPTS / "coach_pipeline.py",
    SCRIPTS / "coach_output_guard.py",
    SCRIPTS / "workout_plan_context.py",
    SCRIPTS / "workout_analysis_context.py",
)
DEFERRED_REVIEW_REASON = (
    "Beslutet skjuts upp eftersom mellanliggande planerade dagar ännu inte har ett känt utfall."
)


def analysis_code_signature(paths=ANALYSIS_CODE_FILES):
    """Hash the deterministic analysis pipeline so code changes self-invalidate."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def latest_for_analysis(latest, decision_plan, latest_date, code_signature=None):
    enriched = dict(latest)
    workout_context = dict(latest.get("workout_analysis_context") or {})
    plan_comparison = build_plan_comparison(decision_plan, latest, latest_date)
    workout_context["plan_comparison"] = plan_comparison
    workout_context["coach_pipeline_contract_version"] = COACH_PIPELINE_CONTRACT_VERSION
    workout_context["analysis_code_sha256"] = code_signature or analysis_code_signature()
    enriched["workout_analysis_context"] = workout_context
    return enriched, plan_comparison


def link_fulfilled_activity_ids(plan, activities):
    """Persist only deterministic workout→activity linkage.

    Independent same-day workouts are linked separately. A multisport workout may
    link to several component activities through activity_ids. Ambiguous
    same-family matching remains unresolved rather than being guessed.
    """
    changed = False
    fulfilled = legacy.fulfilled_plan_workouts(plan, activities)
    meta = plan.get("meta") or {}

    for workout in legacy.planned_workouts(plan):
        key = legacy.workout_key(workout, meta)
        activity_ids = tuple(fulfilled.get(key) or ())
        if not activity_ids:
            continue

        if len(activity_ids) == 1:
            if str(workout.get("activity_id") or "") != str(activity_ids[0]):
                workout["activity_id"] = activity_ids[0]
                workout.pop("activity_ids", None)
                changed = True
        else:
            normalized = list(activity_ids)
            if workout.get("activity_ids") != normalized:
                workout["activity_ids"] = normalized
                workout.pop("activity_id", None)
                changed = True

    # Legacy calendar rows are a projection only. Preserve a single activity_id
    # there when the date contains exactly one fulfilled physical workout.
    if plan.get("planned_workouts") is not None:
        by_date = {}
        for workout in legacy.planned_workouts(plan):
            key = legacy.workout_key(workout, meta)
            ids = tuple(fulfilled.get(key) or ())
            if ids:
                by_date.setdefault(workout.get("date"), []).append(ids)
        for day in plan.get("days") or []:
            groups = by_date.get(day.get("date")) or []
            if len(groups) == 1 and len(groups[0]) == 1:
                if str(day.get("activity_id") or "") != str(groups[0][0]):
                    day["activity_id"] = groups[0][0]
                    changed = True
            elif len(groups) != 1:
                if "activity_id" in day:
                    day.pop("activity_id", None)
                    changed = True
    return changed


def select_activity_for_analysis(decision_plan, activities, coach_state, local_date):
    """Prefer unanalysed activities that deterministically fulfill planned workouts."""
    if not activities:
        return None

    analysed_ids = {
        str(entry.get("activity_id"))
        for entry in coach_state.get("analyses") or []
        if entry.get("activity_id") is not None
    }
    by_id = {
        str(activity.get("id")): activity
        for activity in activities
        if activity.get("id") is not None
    }
    fulfilled = legacy.fulfilled_plan_workouts(decision_plan, activities)

    planned_candidates = []
    for workout in legacy.planned_workouts(decision_plan):
        if str(workout.get("date") or "") != local_date:
            continue
        key = legacy.workout_key(workout, decision_plan.get("meta") or {})
        for activity_id in fulfilled.get(key) or ():
            activity = by_id.get(str(activity_id))
            if activity and str(activity_id) not in analysed_ids:
                planned_candidates.append(activity)

    if planned_candidates:
        return min(
            planned_candidates,
            key=lambda activity: activity.get("start_date") or "",
        )

    unanalysed = [
        activity
        for activity in activities
        if activity.get("id") is None
        or str(activity.get("id")) not in analysed_ids
    ]
    source = unanalysed or activities
    return max(source, key=lambda activity: activity.get("start_date") or "")


def concretize_deferred_review(action, decision_plan, latest_date):
    """Replace generic deferred copy with known adjacent sessions when possible."""
    normalized = dict(action)
    if normalized.get("action") != "review" or normalized.get("reason") != DEFERRED_REVIEW_REASON:
        return normalized

    future_days = sorted(
        [
            day
            for day in (decision_plan.get("days") or [])
            if str(day.get("date") or "") > latest_date and day.get("session")
        ],
        key=lambda day: day.get("date"),
    )
    fixed_day = next(
        (
            day
            for day in future_days
            if day.get("manual_lock") is True or day.get("planning_status") == "fixed"
        ),
        None,
    )
    if not fixed_day:
        return normalized

    following_day = next(
        (
            day
            for day in future_days
            if str(day.get("date") or "") > str(fixed_day.get("date") or "")
            and day.get("session")
        ),
        None,
    )
    if not following_day:
        return normalized

    fixed_label = fixed_day.get("label") or fixed_day.get("date")
    following_label = following_day.get("label") or following_day.get("date")
    normalized["recommendation"] = (
        f"{fixed_label}: {fixed_day.get('session')} ligger kvar som plan. "
        f"{following_label}: {following_day.get('session')} bedöms efter den faktiska belastningen "
        f"från {str(fixed_label).lower()} och återhämtningen därefter."
    )
    return normalized


def normalize_invalid_dose_option_action(action, decision_plan):
    """Fail closed when the model mixes a dose option from another planned day.

    A model-generated option id is advisory until it has been matched against the
    target day's deterministic dose_options. A cross-day or invented id must never
    abort activity ingestion/publication and must never be replaced by a guessed
    alternative. Convert only that invalid automatic action to review.
    """
    normalized = dict(action)
    option_id = str(normalized.get("dose_option_id") or "").strip()
    target = str(normalized.get("target_date") or "").strip()
    kind = normalized.get("action")
    if not option_id or not target or kind not in {"keep", "reduce"}:
        return normalized

    try:
        day = legacy.target_workout(decision_plan, normalized)
    except RuntimeError:
        day = None
    if not day:
        return normalized

    valid_ids = {
        str(option.get("id") or "").strip()
        for option in (day.get("dose_options") or [])
        if str(option.get("id") or "").strip()
    }
    if option_id in valid_ids:
        return normalized

    normalized["action"] = "review"
    normalized["target_date"] = ""
    normalized["target_workout_key"] = ""
    normalized["dose_option_id"] = ""
    normalized["reason"] = "Det valda dosalternativet matchar inte det planerade passet."
    normalized["recommendation"] = "Behåll nuvarande plan; ingen automatisk ändring görs."
    normalized["requires_approval"] = False
    return normalized


def normalize_unapplicable_plan_action(
    action,
    decision_plan,
    ready_dates,
    ready_workouts,
    local_date,
):
    """Fail closed when model output cannot be applied safely.

    Structured model output is untrusted until the deterministic plan validators
    accept it. A semantically invalid automatic change must never abort activity
    ingestion or publication; degrade only that action to a no-change review.
    """
    normalized = dict(action)
    try:
        legacy.validate_plan_action(normalized, ready_dates, ready_workouts)
        legacy.validate_dose_option_action(decision_plan, normalized, local_date)
        return normalized
    except RuntimeError as exc:
        print(
            f"AI coach: ogiltig automatisk planåtgärd neutraliserad: {exc}",
            flush=True,
        )

    normalized["action"] = "review"
    normalized["target_date"] = ""
    normalized["target_workout_key"] = ""
    normalized["dose_option_id"] = ""
    normalized["reason"] = (
        "Den föreslagna automatiska planändringen kunde inte kopplas entydigt "
        "till ett tillåtet målpass."
    )
    normalized["recommendation"] = (
        "Behåll nuvarande plan; ingen automatisk ändring görs. "
        "Bedöm nästa beslutsmogna pass när underlaget räcker."
    )
    normalized["requires_approval"] = False

    # The fallback itself is deterministic and must satisfy the same contracts.
    legacy.validate_plan_action(normalized, ready_dates, ready_workouts)
    legacy.validate_dose_option_action(decision_plan, normalized, local_date)
    return normalized


def main():
    plan = legacy.load_json(legacy.PLAN_FILE, {})
    upcoming = legacy.load_json(legacy.UPCOMING_FILE, {})
    activities_state = legacy.load_json(legacy.ACTIVITIES_FILE, {"activities": []})
    performance_history = legacy.load_json(
        legacy.PERFORMANCE_FILE,
        {"schema_version": 1, "entries": []},
    )
    coach_state = legacy.load_json(
        legacy.COACH_FILE,
        {"analyses": [], "last_trigger_hash": None, "last_run_utc": None},
    )
    strategy = legacy.load_json(legacy.STRATEGY_FILE, {})
    legacy.validate_training_strategy(strategy)
    wellness_context = legacy.load_private_wellness_context()
    activities = activities_state.get("activities", [])

    if not activities:
        print("AI coach pipeline: inga aktiviteter att analysera.")
        return 0

    tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
    local_date = datetime.now(tz).date().isoformat()

    if link_fulfilled_activity_ids(plan, activities):
        legacy.PLAN_FILE.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    decision_plan = legacy.planning_window(plan, upcoming)
    latest = select_activity_for_analysis(
        decision_plan,
        activities,
        coach_state,
        local_date,
    )
    if latest is None:
        print("AI coach pipeline: inga aktiviteter att analysera.")
        return 0

    latest_date = (latest.get("start_date_local") or latest.get("start_date") or "")[:10]
    latest_input, plan_comparison = latest_for_analysis(
        latest,
        decision_plan,
        latest_date,
        code_signature=analysis_code_signature(),
    )
    rolling_context = legacy.rolling_load_context(
        activities,
        decision_plan,
        local_date,
        strategy,
    )
    performance_context = legacy.performance_context_for_activity(
        performance_history,
        latest.get("id"),
    )
    trigger_hash = legacy.stable_hash(
        decision_plan,
        latest_input,
        local_date,
        strategy,
        wellness_context,
        rolling_context,
        performance_context,
    )

    if coach_state.get("last_trigger_hash") == trigger_hash:
        print("AI coach pipeline: inget nytt underlag; hoppar över API-anrop.")
        return 0

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("AI coach pipeline: OPENAI_API_KEY saknas; hoppar över AI-analys.")
        return 0

    recent = sorted(
        activities,
        key=lambda activity: activity.get("start_date") or "",
        reverse=True,
    )[:10]
    coach_plan, fulfilled_dates = legacy.plan_for_coach(decision_plan, activities)
    candidate_workouts = legacy.allowed_target_workouts(
        decision_plan, activities, local_date
    )
    ready_workouts = legacy.decision_ready_target_workouts(
        decision_plan, activities, local_date
    )
    candidate_dates = list(
        dict.fromkeys(item["date"] for item in candidate_workouts)
    )
    ready_dates = list(
        dict.fromkeys(item["date"] for item in ready_workouts)
    )
    deferred_dates = [date for date in candidate_dates if date not in ready_dates]
    remaining_dates = legacy.remaining_training_dates(decision_plan, activities, local_date)

    input_data = {
        "today_local": local_date,
        "latest_activity": latest_input,
        "latest_activity_date": latest_date,
        "recent_activities": recent,
        "rolling_load_context": rolling_context,
        "performance_context": performance_context,
        "current_plan": coach_plan,
        "current_strategy": strategy,
        "private_wellness_context": wellness_context,
        "fulfilled_plan_dates": sorted(fulfilled_dates),
        "allowed_target_dates": ready_dates,
        "allowed_target_workouts": ready_workouts,
        "deferred_target_dates": deferred_dates,
        "instruction": (
            "Analysera senaste passet utifrån latest_activity.workout_analysis_context som primärt faktalager. "
            "Dess plan_comparison är en deterministisk jämförelse mellan vald planerad dos, godkända dosalternativ "
            "och faktiskt genomförd dos; kalla aldrig passet 'enligt plan' om den jämförelsen visar en avvikelse. "
            "Använd rolling_load_context som enda faktakälla för vilka pass som ligger i föregående och kommande 2–3 dagar. "
            "Om performance_context finns är dess arbetsintervall och jämförelsedelta deterministiska fakta: tolka dem, "
            "men rekonstruera eller ändra aldrig siffrorna. Skilj inom-pass-trend från jämförelse mot tidigare samma protokoll. "
            "private_wellness_context är privat och tillfälligt: använd det endast konservativt och återge aldrig råvärden eller källnamn. "
            "Dagar i fulfilled_plan_dates är helt genomförda och får aldrig ordineras igen. target_date får endast väljas ur allowed_target_dates. "
            "target_workout_key ska peka på ett pass i allowed_target_workouts. Om flera separata pass ligger samma datum "
            "måste exakt målpass anges; de får aldrig slås ihop till ett datumobjekt. "
            "Datum i deferred_target_dates är inte beslutsmogna och ska inte ändras nu. Om allowed_target_dates är tom ska target_date vara tomt. "
            "Föreslå endast konservativ automatisk ändring; allt som kan innebära ökad belastning ska vara review. "
            "Om dose_option_id används måste id:t finnas i dose_options för exakt samma target_workout_key; blanda aldrig dosalternativ mellan pass. "
            "Hitta aldrig på klockslag eller rapporteringsfönster för användarfeedback."
        ),
    }

    system_prompt = legacy.PROMPT_FILE.read_text(encoding="utf-8")
    result = legacy.call_openai(system_prompt, input_data)
    if wellness_context.get("daily"):
        result = legacy.scrub_private_wellness_output(result)
    result = legacy.neutralize_unbased_load_labels(result)
    result = legacy.neutralize_same_day_absorption_claims(
        result,
        latest_activity=latest_input,
        latest_date=latest_date,
        local_date=local_date,
    )
    result = guard_result(
        result,
        latest_date=latest_date,
        local_date=local_date,
        plan_comparison=plan_comparison,
    )
    result["assessment"] = legacy.normalize_assessment_confidence(result["assessment"])

    facts = legacy.canonical_facts(latest, latest_date, fulfilled_dates)
    plan_fact = plan_comparison_fact(plan_comparison)
    if plan_fact:
        facts.append(plan_fact)
    facts.extend(legacy.performance_facts(performance_context))
    result["assessment"]["facts"] = facts[:7]

    result["plan_action"] = legacy.normalize_deferred_future_action(
        result["plan_action"],
        candidate_dates=candidate_dates,
        ready_dates=ready_dates,
    )
    result["plan_action"] = concretize_deferred_review(
        result["plan_action"],
        decision_plan,
        latest_date,
    )
    result["plan_action"] = legacy.normalize_no_remaining_plan(
        result["plan_action"],
        allowed_dates=ready_dates,
        latest_date=latest_date,
        fulfilled_dates=fulfilled_dates,
        remaining_dates=remaining_dates,
    )
    result["plan_action"] = legacy.normalize_target_workout(
        result["plan_action"],
        ready_workouts,
    )
    result["plan_action"] = legacy.normalize_dose_option_field(result["plan_action"])
    result["plan_action"] = legacy.normalize_resolved_dose_reselection(
        decision_plan,
        result["plan_action"],
    )
    result["plan_action"] = legacy.normalize_same_day_open_dose_action(
        decision_plan,
        result["plan_action"],
        local_date,
    )
    result = guard_result(
        result,
        latest_date=latest_date,
        local_date=local_date,
        plan_comparison=plan_comparison,
    )
    result["plan_action"] = normalize_invalid_dose_option_action(
        result["plan_action"],
        decision_plan,
    )
    result["plan_action"] = normalize_unapplicable_plan_action(
        result["plan_action"],
        decision_plan,
        ready_dates,
        ready_workouts,
        local_date,
    )
    # Keep the strict validators after normalization as an invariant check.
    legacy.validate_plan_action(
        result["plan_action"], ready_dates, ready_workouts
    )
    legacy.validate_dose_option_action(decision_plan, result["plan_action"], local_date)

    target_date = str(result["plan_action"].get("target_date") or "")
    target_key = str(result["plan_action"].get("target_workout_key") or "")
    target_plan = plan
    target_file = legacy.PLAN_FILE

    def owns_target(document):
        if target_key:
            return any(
                legacy.workout_key(item, document.get("meta") or {}) == target_key
                for item in legacy.planned_workouts(document)
            )
        return any(
            day.get("date") == target_date
            for day in document.get("days", [])
        )

    if target_date and not owns_target(plan) and owns_target(upcoming):
        target_plan = upcoming
        target_file = legacy.UPCOMING_FILE

    changed, apply_note = legacy.apply_conservative_action(target_plan, result["plan_action"])
    if changed:
        target_file.write_text(
            json.dumps(target_plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    now_utc = datetime.now(timezone.utc).isoformat()
    workout_context = latest_input.get("workout_analysis_context") or {}
    entry = {
        "activity_id": latest.get("id"),
        "activity_date": latest_date,
        "activity_name": latest.get("name"),
        "generated_at_utc": now_utc,
        "model": legacy.MODEL,
        "analysis_contract": {
            "pipeline_version": COACH_PIPELINE_CONTRACT_VERSION,
            "workout_context_version": workout_context.get("contract_version"),
            "plan_comparison_version": PLAN_COMPARISON_CONTRACT_VERSION,
            "coach_prompt_sha256": workout_context.get("coach_prompt_sha256"),
            "analysis_code_sha256": workout_context.get("analysis_code_sha256"),
        },
        "performance_marker_id": performance_context.get("marker_id") if performance_context else None,
        "performance_protocol_key": performance_context.get("protocol_key") if performance_context else None,
        "assessment": result["assessment"],
        "plan_action": result["plan_action"],
        "auto_apply": {
            "applied": changed,
            "note": apply_note,
        },
    }

    analyses = [
        analysis
        for analysis in coach_state.get("analyses", [])
        if analysis.get("activity_id") != latest.get("id")
    ]
    analyses.insert(0, entry)
    coach_state["analyses"] = analyses[:30]
    coach_state["last_run_utc"] = now_utc
    updated_decision_plan = legacy.planning_window(plan, upcoming)
    coach_state["last_trigger_hash"] = legacy.stable_hash(
        updated_decision_plan,
        latest_input,
        local_date,
        strategy,
        wellness_context,
        rolling_context,
        performance_context,
    )
    coach_state["contract_version"] = legacy.COACH_CONTRACT_VERSION
    coach_state["pipeline_contract_version"] = COACH_PIPELINE_CONTRACT_VERSION
    legacy.COACH_FILE.write_text(
        json.dumps(coach_state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    wellness_note = (
        "med privat återhämtningskontext"
        if wellness_context.get("daily")
        else "utan återhämtningskontext"
    )
    print(
        f"AI coach pipeline: analyserade aktivitet {latest.get('id')} med {legacy.MODEL} "
        f"{wellness_note}. Fulfilled={sorted(fulfilled_dates)} ready_targets={ready_dates} "
        f"deferred={deferred_dates}. {apply_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
