#!/usr/bin/env python3
from datetime import date


STRATEGY_SCHEMA_VERSION = 2
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
        hierarchy.get("order") == ["north_star", "development_block", "week", "near_term"],
        "strategi.planning_hierarchy.order måste vara north_star → development_block → week → near_term",
    )
    for field in (
        "north_star_role",
        "development_block_role",
        "week_role",
        "near_term_role",
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

    block = document.get("current_block")
    require(isinstance(block, dict), "strategi.current_block saknas")
    nonempty_string(block.get("id"), "strategi.current_block.id")
    nonempty_string(block.get("title"), "strategi.current_block.title")
    start = iso_date(block.get("start_date"), "strategi.current_block.start_date")
    end = iso_date(block.get("end_date"), "strategi.current_block.end_date")
    evaluation = iso_date(block.get("evaluation_date"), "strategi.current_block.evaluation_date")
    require(start <= end < evaluation, "strategi.current_block: datumordning måste vara start <= end < evaluation")
    nonempty_string(block.get("hypothesis"), "strategi.current_block.hypothesis")
    protected = block.get("protected_stimuli")
    require(isinstance(protected, list) and protected, "strategi.current_block.protected_stimuli saknas")
    require(len(set(protected)) == len(protected), "strategi.current_block.protected_stimuli innehåller dubbletter")
    for key in protected:
        require(key in capability_keys, f"strategi.current_block: okänt protected stimulus {key!r}")
    for field in ("success_signals", "guardrails"):
        values = block.get(field)
        require(isinstance(values, list) and values, f"strategi.current_block.{field} saknas")
        require(all(isinstance(value, str) and value.strip() for value in values), f"strategi.current_block.{field} innehåller ogiltig text")

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
        "protect_block_stimuli_before_optional_training",
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
