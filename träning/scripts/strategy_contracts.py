#!/usr/bin/env python3
from datetime import date


STRATEGY_SCHEMA_VERSION = 3
VALID_PRIORITY_MODES = {"develop", "maintain_develop", "develop_cautiously", "supporting"}
VALID_READINESS_STATES = {"keep_option_open", "active_focus", "deprioritized"}
VALID_DEFAULT_ACTIONS = {"keep", "review"}


class StrategyContractError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise StrategyContractError(message)


def nonempty_string(value, context):
    require(isinstance(value, str) and value.strip(), f"{context}: text saknas")


def iso_date(value, context):
    nonempty_string(value, context)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise StrategyContractError(f"{context}: ogiltigt ISO-datum {value!r}") from exc


def validate_training_strategy(document):
    require(isinstance(document, dict), "strategi: rot måste vara objekt")
    require(
        document.get("schema_version") == STRATEGY_SCHEMA_VERSION,
        f"strategi: schema_version måste vara {STRATEGY_SCHEMA_VERSION}",
    )
    nonempty_string(document.get("north_star"), "strategi.north_star")

    hierarchy = document.get("planning_hierarchy")
    require(isinstance(hierarchy, dict), "strategi.planning_hierarchy saknas")
    require(
        hierarchy.get("order") == ["north_star", "mesocycle", "week", "near_term", "session"],
        "strategi.planning_hierarchy.order måste vara north_star → mesocycle → week → near_term → session",
    )
    for field in (
        "north_star_role",
        "mesocycle_role",
        "week_role",
        "near_term_role",
        "session_role",
        "adaptation_rule",
    ):
        nonempty_string(hierarchy.get(field), f"strategi.planning_hierarchy.{field}")

    priorities = document.get("current_priorities")
    require(isinstance(priorities, list) and priorities, "strategi.current_priorities saknas")
    priority_keys = set()
    priority_numbers = set()
    for index, item in enumerate(priorities):
        context = f"strategi.current_priorities[{index}]"
        require(isinstance(item, dict), f"{context}: måste vara objekt")
        key = item.get("key")
        nonempty_string(key, f"{context}.key")
        require(key not in priority_keys, f"{context}: dubblerad key {key!r}")
        priority_keys.add(key)
        nonempty_string(item.get("label"), f"{context}.label")
        require(item.get("mode") in VALID_PRIORITY_MODES, f"{context}: ogiltigt mode")
        priority = item.get("priority")
        require(isinstance(priority, int) and priority > 0, f"{context}.priority måste vara positivt heltal")
        require(priority not in priority_numbers, f"{context}: dubblerad priority {priority}")
        priority_numbers.add(priority)
        nonempty_string(item.get("intent"), f"{context}.intent")

    capabilities = document.get("capability_portfolio")
    require(isinstance(capabilities, list) and capabilities, "strategi.capability_portfolio saknas")
    capability_keys = set()
    for index, item in enumerate(capabilities):
        context = f"strategi.capability_portfolio[{index}]"
        require(isinstance(item, dict), f"{context}: måste vara objekt")
        key = item.get("key")
        nonempty_string(key, f"{context}.key")
        require(key not in capability_keys, f"{context}: dubblerad key {key!r}")
        capability_keys.add(key)
        nonempty_string(item.get("label"), f"{context}.label")
        require(item.get("mode") in VALID_PRIORITY_MODES, f"{context}: ogiltigt mode")
        priority = item.get("priority")
        require(isinstance(priority, int) and priority > 0, f"{context}.priority måste vara positivt heltal")

    mesocycle = document.get("current_mesocycle")
    require(isinstance(mesocycle, dict), "strategi.current_mesocycle saknas")
    nonempty_string(mesocycle.get("id"), "strategi.current_mesocycle.id")
    nonempty_string(mesocycle.get("title"), "strategi.current_mesocycle.title")
    start = iso_date(mesocycle.get("start_date"), "strategi.current_mesocycle.start_date")
    end = iso_date(mesocycle.get("end_date"), "strategi.current_mesocycle.end_date")
    evaluation = iso_date(mesocycle.get("evaluation_date"), "strategi.current_mesocycle.evaluation_date")
    require(start <= end < evaluation, "strategi.current_mesocycle: datumordning måste vara start <= end < evaluation")
    nonempty_string(mesocycle.get("goal_contribution"), "strategi.current_mesocycle.goal_contribution")
    nonempty_string(mesocycle.get("hypothesis"), "strategi.current_mesocycle.hypothesis")

    protected = mesocycle.get("protected_stimuli")
    require(isinstance(protected, list) and protected, "strategi.current_mesocycle.protected_stimuli saknas")
    require(len(set(protected)) == len(protected), "strategi.current_mesocycle.protected_stimuli innehåller dubbletter")
    for key in protected:
        require(key in capability_keys, f"strategi.current_mesocycle: okänt protected stimulus {key!r}")

    supporting = mesocycle.get("supporting_stimuli")
    require(isinstance(supporting, list), "strategi.current_mesocycle.supporting_stimuli måste vara lista")
    require(len(set(supporting)) == len(supporting), "strategi.current_mesocycle.supporting_stimuli innehåller dubbletter")
    for key in supporting:
        require(key in capability_keys, f"strategi.current_mesocycle: okänt supporting stimulus {key!r}")

    weekly_template = mesocycle.get("weekly_template")
    require(isinstance(weekly_template, list) and weekly_template, "strategi.current_mesocycle.weekly_template saknas")
    template_slots = set()
    template_weekdays = set()
    template_stimuli = set()
    for index, item in enumerate(weekly_template):
        context = f"strategi.current_mesocycle.weekly_template[{index}]"
        require(isinstance(item, dict), f"{context}: måste vara objekt")
        slot = item.get("slot")
        nonempty_string(slot, f"{context}.slot")
        require(slot not in template_slots, f"{context}: dubblerad slot {slot!r}")
        template_slots.add(slot)
        weekday = item.get("preferred_weekday")
        require(isinstance(weekday, int) and 1 <= weekday <= 7, f"{context}.preferred_weekday måste vara 1–7")
        require(weekday not in template_weekdays, f"{context}: flera mesocykelplatser på veckodag {weekday}")
        template_weekdays.add(weekday)
        nonempty_string(item.get("sport"), f"{context}.sport")
        require(item.get("priority_role") in {"anchor", "flex", "optional"}, f"{context}.priority_role ogiltig")
        stimuli = item.get("stimuli")
        require(isinstance(stimuli, list) and stimuli, f"{context}.stimuli saknas")
        for key in stimuli:
            require(key in capability_keys, f"{context}: okänt stimulus {key!r}")
            template_stimuli.add(key)
        for field in ("session", "reason", "development_focus"):
            nonempty_string(item.get(field), f"{context}.{field}")

    missing_protected = [key for key in protected if key not in template_stimuli]
    require(
        not missing_protected,
        f"strategi.current_mesocycle.weekly_template saknar protected stimuli {missing_protected!r}",
    )

    progression = mesocycle.get("progression_policy")
    require(isinstance(progression, dict), "strategi.current_mesocycle.progression_policy saknas")
    for field in (
        "automatic_load_increase",
        "keep_intensity_controlled",
        "dose_decided_near_term",
        "preserve_stimulus_before_preserving_exact_session",
        "missed_protected_stimulus_requires_review",
    ):
        require(isinstance(progression.get(field), bool), f"strategi.current_mesocycle.progression_policy.{field} måste vara bool")
    require(progression.get("automatic_load_increase") is False, "strategi: automatisk belastningsökning får inte vara aktiverad")
    require(progression.get("dose_decided_near_term") is True, "strategi: mesocykeldos måste beslutas i närtid")
    require(
        progression.get("preserve_stimulus_before_preserving_exact_session") is True,
        "strategi: stimulus ska prioriteras före exakt passform",
    )

    for field in ("success_signals", "guardrails", "review_questions"):
        values = mesocycle.get(field)
        require(isinstance(values, list) and values, f"strategi.current_mesocycle.{field} saknas")
        require(
            all(isinstance(value, str) and value.strip() for value in values),
            f"strategi.current_mesocycle.{field} innehåller ogiltig text",
        )

    readiness = document.get("strategic_readiness")
    require(isinstance(readiness, list) and readiness, "strategi.strategic_readiness saknas")
    readiness_keys = set()
    for index, item in enumerate(readiness):
        context = f"strategi.strategic_readiness[{index}]"
        require(isinstance(item, dict), f"{context}: måste vara objekt")
        key = item.get("key")
        nonempty_string(key, f"{context}.key")
        require(key not in readiness_keys, f"{context}: dubblerad key {key!r}")
        readiness_keys.add(key)
        nonempty_string(item.get("label"), f"{context}.label")
        require(item.get("state") in VALID_READINESS_STATES, f"{context}: ogiltig state")

    policy = document.get("decision_policy")
    require(isinstance(policy, dict), "strategi.decision_policy saknas")
    horizon = policy.get("horizon_days")
    require(isinstance(horizon, int) and 1 <= horizon <= 7, "strategi.decision_policy.horizon_days måste vara 1–7")
    require(policy.get("default_action") in VALID_DEFAULT_ACTIONS, "strategi.decision_policy.default_action ogiltig")
    for field in (
        "free_day_is_not_training_reason",
        "defer_open_dose_until_near_load_known",
        "prioritize_continuity_over_max_content",
        "protect_mesocycle_stimuli_before_optional_training",
        "long_term_goal_is_primary",
        "near_term_changes_must_serve_long_term_direction",
    ):
        require(isinstance(policy.get(field), bool), f"strategi.decision_policy.{field} måste vara bool")
    require(policy.get("long_term_goal_is_primary") is True, "strategi: långsiktig målbild måste vara överordnad")
    require(
        policy.get("near_term_changes_must_serve_long_term_direction") is True,
        "strategi: närtidsändringar måste tjäna den långsiktiga riktningen",
    )
    return True
