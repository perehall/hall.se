#!/usr/bin/env python3
import hashlib
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
GOAL_FILE = ROOT / "data" / "goal.json"


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
    goal = load(GOAL_FILE)

    validate_plan_document(plan)
    validate_plan_document(upcoming, upcoming=True)
    validate_activities_document(activities_state)
    try:
        validate_training_strategy(strategy)
    except StrategyContractError as exc:
        raise ContractError(str(exc)) from exc

    require(goal.get("schema_version") == 2, "målbild: schema_version måste vara 2")
    canonical_goal = str(goal.get("goal") or "").strip()
    require(bool(canonical_goal), "målbild: goal saknas")
    require(
        strategy.get("north_star") == canonical_goal,
        "strategi: north_star avviker från kanonisk målbild; mesocykeln måste omprövas",
    )
    goal_hash = hashlib.sha256(canonical_goal.encode("utf-8")).hexdigest()
    require(
        (strategy.get("goal_contract") or {}).get("goal_hash") == goal_hash,
        "strategi: målbilden har ändrats; goal_contract och mesocykel måste omprövas",
    )
    require(
        (strategy.get("current_mesocycle") or {}).get("goal_basis_hash") == goal_hash,
        "strategi: aktuell mesocykel bygger inte på nuvarande målbild",
    )

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
        "Datakontrakt OK: plan v3, kommande vecka v3, aktiviteter v2, strategi v5 och coach-state är konsistenta."
    )


if __name__ == "__main__":
    main()
