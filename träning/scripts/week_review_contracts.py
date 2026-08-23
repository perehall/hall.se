#!/usr/bin/env python3
import re
from datetime import date, timedelta

from training_contracts import VALID_CLASSIFICATIONS, ContractError, require

REVIEW_SCHEMA_VERSION = 1
REVIEW_CONTRACT_VERSION = 1
VALID_PLAN_OUTCOMES = {
    "fulfilled",
    "different_activity",
    "not_completed",
    "completed_without_synced_activity",
    "no_activity_planned",
    "unplanned_activity",
}


def _nonempty(value, context):
    require(isinstance(value, str) and value.strip(), f"{context}: text saknas")


def _nonnegative_int(value, context):
    require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"{context}: måste vara icke-negativt heltal")


def _iso_date(value, context):
    _nonempty(value, context)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{context}: ogiltigt ISO-datum {value!r}") from exc


def validate_week_assessment(assessment):
    require(isinstance(assessment, dict), "week_review.assessment: måste vara objekt")
    required_strings = ["summary", "load_continuity", "key_lesson", "next_week_implication"]
    for field in required_strings:
        _nonempty(assessment.get(field), f"week_review.assessment.{field}")
    limits = {"worked": 4, "not_as_planned": 4, "uncertainties": 3}
    for field, limit in limits.items():
        value = assessment.get(field)
        require(isinstance(value, list), f"week_review.assessment.{field}: måste vara lista")
        require(len(value) <= limit, f"week_review.assessment.{field}: max {limit} punkter")
        require(
            all(isinstance(item, str) and item.strip() for item in value),
            f"week_review.assessment.{field}: innehåller tom/ogiltig text",
        )
    require("score" not in assessment and "rating" not in assessment, "week_review: poäng/betyg är inte tillåtet")
    return True


def validate_week_facts(facts):
    require(isinstance(facts, dict), "week_review.facts: måste vara objekt")
    key = facts.get("week_key")
    require(isinstance(key, str) and re.fullmatch(r"\d{4}-W\d{2}", key), "week_review.facts.week_key: ogiltigt format")
    start = _iso_date(facts.get("week_start"), "week_review.facts.week_start")
    end = _iso_date(facts.get("week_end"), "week_review.facts.week_end")
    require(end == start + timedelta(days=6), "week_review.facts: veckan måste omfatta exakt sju dagar")

    for field in (
        "activity_count",
        "training_activity_count",
        "recreation_activity_count",
        "active_days",
        "total_activity_time_s",
        "training_time_s",
        "recreation_time_s",
    ):
        _nonnegative_int(facts.get(field), f"week_review.facts.{field}")
    require(facts["active_days"] <= 7, "week_review.facts.active_days: får inte överstiga 7")
    require(
        facts["training_activity_count"] + facts["recreation_activity_count"] == facts["activity_count"],
        "week_review.facts: tränings- och rekreationsaktiviteter summerar inte till activity_count",
    )
    require(
        facts["training_time_s"] + facts["recreation_time_s"] == facts["total_activity_time_s"],
        "week_review.facts: tränings- och rekreationstid summerar inte till total aktivitetstid",
    )

    activities = facts.get("activities")
    require(isinstance(activities, list) and len(activities) == facts["activity_count"], "week_review.facts.activities: fel antal")
    ids = set()
    activity_dates = set()
    for index, activity in enumerate(activities):
        context = f"week_review.facts.activities[{index}]"
        require(isinstance(activity, dict), f"{context}: måste vara objekt")
        activity_id = activity.get("id")
        require(activity_id is not None, f"{context}.id saknas")
        key_id = str(activity_id)
        require(key_id not in ids, f"{context}: dubbelt aktivitets-id {key_id}")
        ids.add(key_id)
        activity_date = _iso_date(activity.get("date"), f"{context}.date")
        require(start <= activity_date <= end, f"{context}: datum ligger utanför veckan")
        activity_dates.add(activity_date.isoformat())
        _nonempty(activity.get("label"), f"{context}.label")
        require(activity.get("classification") in VALID_CLASSIFICATIONS, f"{context}.classification: ogiltig")
    require(len(activity_dates) == facts["active_days"], "week_review.facts.active_days matchar inte aktivitetsdatumen")

    by_sport = facts.get("by_sport")
    require(isinstance(by_sport, list), "week_review.facts.by_sport: måste vara lista")
    sport_count = 0
    sport_time = 0
    labels = set()
    for index, row in enumerate(by_sport):
        context = f"week_review.facts.by_sport[{index}]"
        _nonempty(row.get("label"), f"{context}.label")
        require(row["label"] not in labels, f"{context}: dubbelt sportnamn")
        labels.add(row["label"])
        _nonnegative_int(row.get("activity_count"), f"{context}.activity_count")
        _nonnegative_int(row.get("time_s"), f"{context}.time_s")
        sport_count += row["activity_count"]
        sport_time += row["time_s"]
    require(sport_count == facts["activity_count"], "week_review.facts.by_sport: activity_count summerar fel")
    require(sport_time == facts["total_activity_time_s"], "week_review.facts.by_sport: time_s summerar fel")

    outcomes = facts.get("plan_outcomes")
    require(isinstance(outcomes, list) and len(outcomes) == 7, "week_review.facts.plan_outcomes: exakt 7 krävs")
    seen_dates = set()
    calculated_counts = {}
    for index, outcome in enumerate(outcomes):
        context = f"week_review.facts.plan_outcomes[{index}]"
        day = _iso_date(outcome.get("date"), f"{context}.date")
        require(start <= day <= end, f"{context}: datum utanför veckan")
        require(day.isoformat() not in seen_dates, f"{context}: dubbelt datum")
        seen_dates.add(day.isoformat())
        value = outcome.get("outcome")
        require(value in VALID_PLAN_OUTCOMES, f"{context}.outcome: ogiltigt {value!r}")
        calculated_counts[value] = calculated_counts.get(value, 0) + 1
        require(isinstance(outcome.get("actual_activity_ids"), list), f"{context}.actual_activity_ids: måste vara lista")
        require(isinstance(outcome.get("actual_labels"), list), f"{context}.actual_labels: måste vara lista")
        require(isinstance(outcome.get("matching_activity_ids"), list), f"{context}.matching_activity_ids: måste vara lista")

    counts = facts.get("outcome_counts")
    require(isinstance(counts, dict), "week_review.facts.outcome_counts: måste vara objekt")
    require(counts == dict(sorted(calculated_counts.items())), "week_review.facts.outcome_counts: matchar inte plan_outcomes")
    return True


def validate_week_review_document(document):
    require(isinstance(document, dict), "week_review: rot måste vara objekt")
    require(document.get("schema_version") == REVIEW_SCHEMA_VERSION, f"week_review.schema_version måste vara {REVIEW_SCHEMA_VERSION}")
    require(document.get("contract_version") == REVIEW_CONTRACT_VERSION, f"week_review.contract_version måste vara {REVIEW_CONTRACT_VERSION}")
    key = document.get("week_key")
    require(isinstance(key, str) and re.fullmatch(r"\d{4}-W\d{2}", key), "week_review.week_key: ogiltigt format")
    start = _iso_date(document.get("week_start"), "week_review.week_start")
    end = _iso_date(document.get("week_end"), "week_review.week_end")
    require(end == start + timedelta(days=6), "week_review: week_end måste vara sex dagar efter week_start")
    digest = document.get("source_hash")
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "week_review.source_hash: ogiltig SHA-256")
    _nonempty(document.get("generated_at_utc"), "week_review.generated_at_utc")
    _nonempty(document.get("model"), "week_review.model")
    validate_week_facts(document.get("facts"))
    require(document["facts"].get("week_key") == key, "week_review: facts.week_key matchar inte dokumentet")
    require(document["facts"].get("week_start") == start.isoformat(), "week_review: facts.week_start matchar inte dokumentet")
    require(document["facts"].get("week_end") == end.isoformat(), "week_review: facts.week_end matchar inte dokumentet")
    validate_week_assessment(document.get("assessment"))
    return True
