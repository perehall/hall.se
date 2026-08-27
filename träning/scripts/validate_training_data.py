#!/usr/bin/env python3
import json
from pathlib import Path

from coach_rules import activity_local_date, canonical_activity_fact
from strategy_contracts import StrategyContractError, validate_training_strategy
from training_contracts import (
    ContractError,
    require,
    validate_activities_document,
    validate_coach_document,
    validate_plan_document,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
COACH_FILE = ROOT / "data" / "coach.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"


def load(path):
    if not path.exists():
        raise ContractError(f"Datakontrakt: fil saknas: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    plan = load(PLAN_FILE)
    upcoming = load(UPCOMING_FILE)
    activities_state = load(ACTIVITIES_FILE)
    coach = load(COACH_FILE)
    strategy = load(STRATEGY_FILE)

    validate_plan_document(plan)
    validate_plan_document(upcoming, upcoming=True)
    validate_activities_document(activities_state)
    try:
        validate_training_strategy(strategy)
    except StrategyContractError as exc:
        raise ContractError(str(exc)) from exc

    activities = activities_state.get("activities") or []
    by_id = {str(activity.get("id")): activity for activity in activities if activity.get("id") is not None}
    validate_coach_document(coach, activity_ids=set(by_id))

    analyses = coach.get("analyses") or []
    if analyses:
        latest = analyses[0]
        activity = by_id[str(latest["activity_id"])]
        require(
            latest.get("activity_date") == activity_local_date(activity),
            "coach: senaste activity_date matchar inte källaktiviteten",
        )
        facts = (latest.get("assessment") or {}).get("facts") or []
        require(bool(facts), "coach: senaste analysen saknar deterministiska facts")
        expected_first_fact = canonical_activity_fact(activity)
        require(
            facts[0] == expected_first_fact,
            "coach: första faktaraden avviker från canonical source fact",
        )

    print(
        "Datakontrakt OK: plan v3, kommande vecka v3, aktiviteter v2, strategi v3 och coach-state är konsistenta."
    )


if __name__ == "__main__":
    main()
