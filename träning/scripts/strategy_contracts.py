#!/usr/bin/env python3
from datetime import date


STRATEGY_SCHEMA_VERSION = 5
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

    goal_contract = document.get("goal_contract")
    require(isinstance(goal_contract, dict), "strategi.goal_contract saknas")
    require(goal_contract.get("source_file") == "data/goal.json", "strategi.goal_contract.source_file måste vara data/goal.json")
    require(goal_contract.get("source_schema_version") == 2, "strategi.goal_contract.source_schema_version måste vara 2")
    goal_hash = goal_contract.get("goal_hash")
    nonempty_string(goal_hash, "strategi.goal_contract.goal_hash")
    require(len(goal_hash) == 64, "strategi.goal_contract.goal_hash måste vara sha256")
    require(goal_contract.get("goal_change_requires_mesocycle_review") is True, "strategi: måländring måste kräva mesocykelomprövning")
    nonempty_string(goal_contract.get("principle"), "strategi.goal_contract.principle")

    hierarchy = document.get("planning_hierarchy")
    require(isinstance(hierarchy, dict), "strategi.planning_hierarchy saknas")
    require(
        hierarchy.get("order") == ["north_star", "mesocycle", "microcycle", "near_term", "session"],
        "strategi.planning_hierarchy.order måste vara north_star → mesocycle → microcycle → near_term → session",
    )
    for field in (
        "north_star_role",
        "mesocycle_role",
        "microcycle_role",
        "near_term_role",
        "session_role",
        "calendar_role",
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

    load_model = document.get("load_model")
    require(isinstance(load_model, dict), "strategi.load_model saknas")
    require(load_model.get("lookback_days") == 3, "strategi.load_model.lookback_days måste vara 3")
    require(load_model.get("lookahead_days") == 3, "strategi.load_model.lookahead_days måste vara 3")
    dimensions = load_model.get("dimensions")
    require(isinstance(dimensions, list) and dimensions, "strategi.load_model.dimensions saknas")
    load_dimension_keys = set()
    for index, item in enumerate(dimensions):
        context = f"strategi.load_model.dimensions[{index}]"
        require(isinstance(item, dict), f"{context}: måste vara objekt")
        key = item.get("key")
        nonempty_string(key, f"{context}.key")
        require(key not in load_dimension_keys, f"{context}: dubblerad key {key!r}")
        load_dimension_keys.add(key)
        nonempty_string(item.get("label"), f"{context}.label")
        nonempty_string(item.get("principle"), f"{context}.principle")
    require(
        load_dimension_keys == {"cardiovascular", "mechanical", "neuromuscular", "technical"},
        "strategi.load_model.dimensions måste innehålla cardiovascular/mechanical/neuromuscular/technical",
    )
    load_rules = load_model.get("rules")
    require(isinstance(load_rules, list) and load_rules, "strategi.load_model.rules saknas")
    require(all(isinstance(x, str) and x.strip() for x in load_rules), "strategi.load_model.rules innehåller ogiltig text")

    marker_policy = document.get("performance_marker_policy")
    require(isinstance(marker_policy, dict), "strategi.performance_marker_policy saknas")
    require(marker_policy.get("prefer_embedded_markers") is True, "strategi: prestationsmarkörer ska i första hand vara inbyggda i ordinarie pass")
    require(marker_policy.get("standalone_max_tests_required") is False, "strategi: fristående max-test får inte vara obligatoriska")
    require(marker_policy.get("evaluate_at_mesocycle_review") is True, "strategi: prestationsmarkörer ska utvärderas vid mesocykelreview")
    require(marker_policy.get("comparison_requires_comparable_context") is True, "strategi: prestationsjämförelser kräver jämförbar kontext")
    nonempty_string(marker_policy.get("principle"), "strategi.performance_marker_policy.principle")
    markers = marker_policy.get("markers")
    require(isinstance(markers, list) and markers, "strategi.performance_marker_policy.markers saknas")
    marker_ids = set()
    for index, item in enumerate(markers):
        context = f"strategi.performance_marker_policy.markers[{index}]"
        require(isinstance(item, dict), f"{context}: måste vara objekt")
        marker_id = item.get("id")
        nonempty_string(marker_id, f"{context}.id")
        require(marker_id not in marker_ids, f"{context}: dubblerat id {marker_id!r}")
        marker_ids.add(marker_id)
        for field in ("capability", "source", "compare_when", "interpretation"):
            nonempty_string(item.get(field), f"{context}.{field}")
        metrics = item.get("metrics")
        require(isinstance(metrics, list) and metrics, f"{context}.metrics saknas")
        require(all(isinstance(x, str) and x.strip() for x in metrics), f"{context}.metrics innehåller ogiltig text")

    capabilities = document.get("capability_portfolio")
    require(isinstance(capabilities, list) and capabilities, "strategi.capability_portfolio saknas")
    capability_keys = set()
    capability_modes = {}
    for index, item in enumerate(capabilities):
        context = f"strategi.capability_portfolio[{index}]"
        require(isinstance(item, dict), f"{context}: måste vara objekt")
        key = item.get("key")
        nonempty_string(key, f"{context}.key")
        require(key not in capability_keys, f"{context}: dubblerad key {key!r}")
        capability_keys.add(key)
        nonempty_string(item.get("label"), f"{context}.label")
        require(item.get("mode") in VALID_PRIORITY_MODES, f"{context}: ogiltigt mode")
        capability_modes[key] = item.get("mode")
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
    require(mesocycle.get("goal_basis_hash") == goal_hash, "strategi.current_mesocycle.goal_basis_hash måste matcha aktuell målbild")
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

    contract = mesocycle.get("contract")
    require(isinstance(contract, dict), "strategi.current_mesocycle.contract saknas")
    contract_groups = ("primary", "secondary", "maintenance", "protected_capacity", "external_load")
    seen_contract_capabilities = set()
    for field in contract_groups:
        values = contract.get(field)
        require(isinstance(values, list), f"strategi.current_mesocycle.contract.{field} måste vara lista")
        require(len(values) == len(set(values)), f"strategi.current_mesocycle.contract.{field} innehåller dubbletter")
        for key in values:
            require(key in capability_keys, f"strategi.current_mesocycle.contract.{field}: okänd capability {key!r}")
            require(key not in seen_contract_capabilities, f"strategi.current_mesocycle.contract: capability {key!r} finns i flera roller")
            seen_contract_capabilities.add(key)
    require(contract.get("primary") == protected, "strategi.current_mesocycle.contract.primary måste matcha protected_stimuli")
    nonempty_string(contract.get("principle"), "strategi.current_mesocycle.contract.principle")

    capacity = mesocycle.get("capacity_protection")
    require(isinstance(capacity, dict), "strategi.current_mesocycle.capacity_protection saknas")
    required_each = capacity.get("required_each_microcycle")
    protected_across = capacity.get("protected_across_mesocycle")
    require(isinstance(required_each, list) and required_each, "strategi.current_mesocycle.capacity_protection.required_each_microcycle saknas")
    require(isinstance(protected_across, list) and protected_across, "strategi.current_mesocycle.capacity_protection.protected_across_mesocycle saknas")
    for key in required_each + protected_across:
        require(key in capability_keys, f"strategi.current_mesocycle.capacity_protection: okänd capability {key!r}")
        require(key in contract.get("protected_capacity", []), f"strategi.current_mesocycle.capacity_protection: {key!r} måste vara protected_capacity")
    require(capacity.get("missing_required_action") == "review_and_restore_in_next_absorbable_window", "strategi: saknad skyddad kapacitet måste kräva review och aktiv återplanering")
    capacity_rules = capacity.get("rules")
    require(isinstance(capacity_rules, list) and capacity_rules, "strategi.current_mesocycle.capacity_protection.rules saknas")
    require(all(isinstance(x, str) and x.strip() for x in capacity_rules), "strategi.current_mesocycle.capacity_protection.rules innehåller ogiltig text")

    structure = mesocycle.get("microcycle_structure")
    require(isinstance(structure, dict), "strategi.current_mesocycle.microcycle_structure saknas")
    length_days = structure.get("length_days")
    require(isinstance(length_days, int) and 1 <= length_days <= 14, "strategi.current_mesocycle.microcycle_structure.length_days måste vara 1–14")
    require(length_days == 7, "strategi: nuvarande kalenderpresentation kräver sjudagars mikrocykel")
    require(structure.get("calendar_alignment") == "monday_sunday", "strategi: nuvarande mikrocykel måste vara monday_sunday")
    nonempty_string(structure.get("rationale"), "strategi.current_mesocycle.microcycle_structure.rationale")

    microcycle_template = mesocycle.get("microcycle_template")
    require(isinstance(microcycle_template, list) and microcycle_template, "strategi.current_mesocycle.microcycle_template saknas")
    template_slots = set()
    template_days = set()
    template_stimuli = set()
    for index, item in enumerate(microcycle_template):
        context = f"strategi.current_mesocycle.microcycle_template[{index}]"
        require(isinstance(item, dict), f"{context}: måste vara objekt")
        slot = item.get("slot")
        nonempty_string(slot, f"{context}.slot")
        require(slot not in template_slots, f"{context}: dubblerad slot {slot!r}")
        template_slots.add(slot)
        day_index = item.get("day_index")
        require(isinstance(day_index, int) and 1 <= day_index <= length_days, f"{context}.day_index måste ligga inom mikrocykeln")
        require(day_index not in template_days, f"{context}: flera mesocykelplatser på mikrocykeldag {day_index}")
        template_days.add(day_index)
        nonempty_string(item.get("sport"), f"{context}.sport")
        require(item.get("priority_role") in {"anchor", "flex", "optional", "protected_support"}, f"{context}.priority_role ogiltig")
        stimuli = item.get("stimuli")
        require(isinstance(stimuli, list) and stimuli, f"{context}.stimuli saknas")
        for key in stimuli:
            require(key in capability_keys, f"{context}: okänt stimulus {key!r}")
            template_stimuli.add(key)
        optional_stimuli = item.get("optional_stimuli") or []
        require(isinstance(optional_stimuli, list), f"{context}.optional_stimuli måste vara lista")
        for key in optional_stimuli:
            require(key in capability_keys, f"{context}: okänt optional stimulus {key!r}")
        load_dimensions = item.get("load_dimensions")
        require(isinstance(load_dimensions, list) and load_dimensions, f"{context}.load_dimensions saknas")
        for key in load_dimensions:
            require(key in load_dimension_keys, f"{context}: okänd load_dimension {key!r}")
        marker_id = item.get("performance_marker_id")
        if marker_id is not None:
            nonempty_string(marker_id, f"{context}.performance_marker_id")
            require(marker_id in marker_ids, f"{context}: okänd performance_marker_id {marker_id!r}")
        progression_criteria = item.get("progression_criteria")
        require(isinstance(progression_criteria, list) and progression_criteria, f"{context}.progression_criteria saknas")
        require(all(isinstance(x, str) and x.strip() for x in progression_criteria), f"{context}.progression_criteria innehåller ogiltig text")
        for field in ("session", "reason", "development_focus"):
            nonempty_string(item.get(field), f"{context}.{field}")
        dose_options = item.get("dose_options")
        baseline_option_id = item.get("baseline_option_id")
        if dose_options is not None:
            require(isinstance(dose_options, list) and dose_options, f"{context}.dose_options måste vara icke-tom lista")
            option_ids = set()
            for option_index, option in enumerate(dose_options):
                option_context = f"{context}.dose_options[{option_index}]"
                require(isinstance(option, dict), f"{option_context}: måste vara objekt")
                option_id = option.get("id")
                nonempty_string(option_id, f"{option_context}.id")
                require(option_id not in option_ids, f"{option_context}: dubblerat id {option_id!r}")
                option_ids.add(option_id)
                require(option.get("kind") in {"duration_minutes", "distance_km", "structured"}, f"{option_context}.kind ogiltig")
                value = option.get("value")
                require(isinstance(value, (int, float)) and value > 0, f"{option_context}.value måste vara positivt tal")
                nonempty_string(option.get("session"), f"{option_context}.session")
                nonempty_string(option.get("intent"), f"{option_context}.intent")
            nonempty_string(baseline_option_id, f"{context}.baseline_option_id")
            require(
                baseline_option_id in option_ids,
                f"{context}.baseline_option_id måste referera till ett dose_options-id",
            )
            baseline_option = next(option for option in dose_options if option.get("id") == baseline_option_id)
            require(
                item.get("session") == baseline_option.get("session"),
                f"{context}.session måste vara den konkreta grundplanen från baseline_option_id",
            )
            progression_target = item.get("progression_target_option_id")
            if progression_target is not None:
                nonempty_string(progression_target, f"{context}.progression_target_option_id")
                require(progression_target in option_ids, f"{context}.progression_target_option_id måste referera till ett dose_options-id")
                require(progression_target != baseline_option_id, f"{context}.progression_target_option_id får inte vara baseline")

        is_development_anchor = (
            item.get("priority_role") == "anchor"
            and any(capability_modes.get(key) == "develop" for key in stimuli)
        )
        if is_development_anchor:
            require(dose_options is not None, f"{context}: utvecklande nyckelpass måste ha dose_options")
            development = item.get("development_progression")
            require(isinstance(development, dict), f"{context}.development_progression saknas")
            require(development.get("mode") == "develop", f"{context}.development_progression.mode måste vara develop")
            floor_id = development.get("demonstrated_floor_option_id")
            nonempty_string(floor_id, f"{context}.development_progression.demonstrated_floor_option_id")
            require(floor_id in option_ids, f"{context}: demonstrerat golv måste referera till ett dose_options-id")
            require(development.get("same_dose_repeat_requires_reason") is True, f"{context}: upprepad utvecklingsdos måste kräva skäl")
            plan_steps = development.get("microcycle_plan")
            require(isinstance(plan_steps, list) and plan_steps, f"{context}.development_progression.microcycle_plan saknas")
            seen_microcycles = set()
            for step_index, step in enumerate(plan_steps):
                step_context = f"{context}.development_progression.microcycle_plan[{step_index}]"
                require(isinstance(step, dict), f"{step_context}: måste vara objekt")
                microcycle = step.get("microcycle")
                require(isinstance(microcycle, int) and microcycle > 0, f"{step_context}.microcycle måste vara positivt heltal")
                require(microcycle not in seen_microcycles, f"{step_context}: dubblerad microcycle {microcycle}")
                seen_microcycles.add(microcycle)
                option_id = step.get("option_id")
                nonempty_string(option_id, f"{step_context}.option_id")
                require(option_id in option_ids, f"{step_context}.option_id måste referera till dose_options")
                require(step.get("relation") in {"progress", "hold", "establish"}, f"{step_context}.relation ogiltig")
                nonempty_string(step.get("reason"), f"{step_context}.reason")
            baseline_value = next(option["value"] for option in dose_options if option["id"] == baseline_option_id)
            floor_value = next(option["value"] for option in dose_options if option["id"] == floor_id)
            require(baseline_value >= floor_value, f"{context}: normal utvecklingsbaseline får inte ligga under demonstrerat kapacitetsgolv")
            require(progression_target is not None, f"{context}: utvecklande nyckelpass måste ha progression_target_option_id")
            target_value = next(option["value"] for option in dose_options if option["id"] == progression_target)
            require(target_value > baseline_value, f"{context}: progression_target måste vara större än baseline i vald belastningsvariabel")

    missing_protected = [key for key in protected if key not in template_stimuli]
    require(
        not missing_protected,
        f"strategi.current_mesocycle.microcycle_template saknar protected stimuli {missing_protected!r}",
    )
    missing_capacity = [key for key in required_each if key not in template_stimuli]
    require(
        not missing_capacity,
        f"strategi.current_mesocycle.microcycle_template saknar obligatorisk kapacitet {missing_capacity!r}",
    )

    progression = mesocycle.get("progression_policy")
    require(isinstance(progression, dict), "strategi.current_mesocycle.progression_policy saknas")
    for field in (
        "automatic_load_increase",
        "keep_intensity_controlled",
        "dose_decided_near_term",
        "baseline_session_planned_in_microcycle",
        "preserve_stimulus_before_preserving_exact_session",
        "missed_protected_stimulus_requires_review",
        "microcycle_may_reorganize_sessions",
        "progression_requires_explicit_criteria",
        "change_one_load_variable_at_a_time",
        "wellness_cannot_trigger_progression",
        "normal_variation_does_not_trigger_change",
        "development_key_sessions_must_progress_or_justify_hold",
        "regression_below_demonstrated_floor_requires_reason",
        "maintenance_sessions_may_repeat_without_progression",
    ):
        require(isinstance(progression.get(field), bool), f"strategi.current_mesocycle.progression_policy.{field} måste vara bool")
    require(progression.get("automatic_load_increase") is False, "strategi: automatisk belastningsökning får inte vara aktiverad")
    require(progression.get("dose_decided_near_term") is False, "strategi: konkreta grundpass får inte skjutas upp till samma dag")
    require(
        progression.get("baseline_session_planned_in_microcycle") is True,
        "strategi: mikrocykeln måste innehålla en konkret grundplan för varje planerat pass",
    )
    require(
        progression.get("preserve_stimulus_before_preserving_exact_session") is True,
        "strategi: stimulus ska prioriteras före exakt passform",
    )
    require(
        progression.get("microcycle_may_reorganize_sessions") is True,
        "strategi: mikrocykeln måste kunna omorganisera pass när närbelastningen kräver det",
    )
    require(progression.get("progression_requires_explicit_criteria") is True, "strategi: progression måste kräva explicita kriterier")
    require(progression.get("change_one_load_variable_at_a_time") is True, "strategi: progression ska ändra en belastningsvariabel i taget")
    require(progression.get("wellness_cannot_trigger_progression") is True, "strategi: wellness får inte utlösa progression")
    require(progression.get("normal_variation_does_not_trigger_change") is True, "strategi: normal variation får inte utlösa planändring")
    require(progression.get("development_key_sessions_must_progress_or_justify_hold") is True, "strategi: utvecklande nyckelpass måste progrediera eller ha explicit hold-skäl")
    require(progression.get("regression_below_demonstrated_floor_requires_reason") is True, "strategi: regression under demonstrerat golv måste kräva explicit skäl")
    require(progression.get("maintenance_sessions_may_repeat_without_progression") is True, "strategi: underhåll får upprepas utan utvecklingskrav")
    repeat_limit = progression.get("max_consecutive_development_repeats_without_reason")
    require(isinstance(repeat_limit, int) and repeat_limit == 1, "strategi: max omotiverade upprepningar av utvecklingsdos måste vara 1")

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
        "same_day_open_dose_must_resolve_or_review",
        "concrete_near_term_plan_by_default",
        "adjust_planned_session_only_when_new_evidence_justifies",
        "normal_variation_is_absorbed_by_plan",
        "multi_day_context_required",
        "development_goal_requires_progression",
        "development_hold_or_regression_requires_reason",
        "maintenance_repeat_is_separate_mode",
    ):
        require(isinstance(policy.get(field), bool), f"strategi.decision_policy.{field} måste vara bool")
    require(policy.get("defer_open_dose_until_near_load_known") is False, "strategi: konkret grundplan får inte skjutas upp bara för att föregående pass saknar utfall")
    require(policy.get("concrete_near_term_plan_by_default") is True, "strategi: närtidsplanen måste vara konkret som standard")
    require(
        policy.get("adjust_planned_session_only_when_new_evidence_justifies") is True,
        "strategi: planerade pass får bara ändras när ny information motiverar det",
    )
    require(policy.get("normal_variation_is_absorbed_by_plan") is True, "strategi: normal passvariation ska absorberas av planen")
    require(policy.get("multi_day_context_required") is True, "strategi: planändring måste använda fler-dagars kontext")
    require(policy.get("development_goal_requires_progression") is True, "strategi: utvecklingsmål måste kräva progression")
    require(policy.get("development_hold_or_regression_requires_reason") is True, "strategi: hold/regression i utvecklingsläge måste kräva skäl")
    require(policy.get("maintenance_repeat_is_separate_mode") is True, "strategi: underhåll ska vara en separat roll från utveckling")
    require(policy.get("long_term_goal_is_primary") is True, "strategi: långsiktig målbild måste vara överordnad")
    require(
        policy.get("near_term_changes_must_serve_long_term_direction") is True,
        "strategi: närtidsändringar måste tjäna den långsiktiga riktningen",
    )
    require(
        policy.get("same_day_open_dose_must_resolve_or_review") is True,
        "strategi: legacy-pass med öppen omfattning måste fortfarande hanteras säkert",
    )
    return True
