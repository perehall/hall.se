#!/usr/bin/env python3
"""Robust orchestration for the AI workout coach.

Raw provider data is preserved, but the model receives deterministic workout
facts and a deterministic planned-versus-actual comparison before interpretation.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import coach as legacy
from coach_output_guard import guard_result
from workout_plan_context import (
    PLAN_COMPARISON_CONTRACT_VERSION,
    build_plan_comparison,
    plan_comparison_fact,
)


COACH_PIPELINE_CONTRACT_VERSION = 1


def latest_for_analysis(latest, decision_plan, latest_date):
    enriched = dict(latest)
    workout_context = dict(latest.get("workout_analysis_context") or {})
    plan_comparison = build_plan_comparison(decision_plan, latest, latest_date)
    workout_context["plan_comparison"] = plan_comparison
    workout_context["coach_pipeline_contract_version"] = COACH_PIPELINE_CONTRACT_VERSION
    enriched["workout_analysis_context"] = workout_context
    return enriched, plan_comparison


def main():
    plan = legacy.load_json(legacy.PLAN_FILE, {})
    upcoming = legacy.load_json(legacy.UPCOMING_FILE, {})
    decision_plan = legacy.planning_window(plan, upcoming)
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

    latest = max(activities, key=lambda activity: activity.get("start_date") or "")
    latest_date = (latest.get("start_date_local") or latest.get("start_date") or "")[:10]
    tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
    local_date = datetime.now(tz).date().isoformat()

    latest_input, plan_comparison = latest_for_analysis(latest, decision_plan, latest_date)
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
    candidate_dates = legacy.allowed_target_dates(decision_plan, activities, local_date)
    ready_dates = legacy.decision_ready_target_dates(decision_plan, activities, local_date)
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
        "deferred_target_dates": deferred_dates,
        "instruction": (
            "Analysera senaste passet utifrån latest_activity.workout_analysis_context som primärt faktalager. "
            "Dess plan_comparison är en deterministisk jämförelse mellan vald planerad dos, godkända dosalternativ "
            "och faktiskt genomförd dos; kalla aldrig passet 'enligt plan' om den jämförelsen visar en avvikelse. "
            "Använd rolling_load_context som enda faktakälla för vilka pass som ligger i föregående och kommande 2–3 dagar. "
            "Om performance_context finns är dess arbetsintervall och jämförelsedelta deterministiska fakta: tolka dem, "
            "men rekonstruera eller ändra aldrig siffrorna. Skilj inom-pass-trend från jämförelse mot tidigare samma protokoll. "
            "private_wellness_context är privat och tillfälligt: använd det endast konservativt och återge aldrig råvärden eller källnamn. "
            "Dagar i fulfilled_plan_dates är redan genomförda och får aldrig ordineras igen. target_date får endast väljas ur allowed_target_dates. "
            "Datum i deferred_target_dates är inte beslutsmogna och ska inte ändras nu. Om allowed_target_dates är tom ska target_date vara tomt. "
            "Föreslå endast konservativ automatisk ändring; allt som kan innebära ökad belastning ska vara review. "
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
    result["plan_action"] = legacy.normalize_no_remaining_plan(
        result["plan_action"],
        allowed_dates=ready_dates,
        latest_date=latest_date,
        fulfilled_dates=fulfilled_dates,
        remaining_dates=remaining_dates,
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
    legacy.validate_plan_action(result["plan_action"], ready_dates)
    legacy.validate_dose_option_action(decision_plan, result["plan_action"], local_date)

    target_date = str(result["plan_action"].get("target_date") or "")
    target_plan = plan
    target_file = legacy.PLAN_FILE
    if target_date and not any(day.get("date") == target_date for day in plan.get("days", [])):
        if any(day.get("date") == target_date for day in upcoming.get("days", [])):
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
