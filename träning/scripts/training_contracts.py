#!/usr/bin/env python3
from datetime import date, timedelta


PLAN_SCHEMA_VERSION = 3
ACTIVITIES_SCHEMA_VERSION = 2
MIN_COACH_CONTRACT_VERSION = 3

VALID_DAY_STATUSES = {"completed", "planned", "preliminary", "conditional", "open"}
VALID_PLANNING_STATUSES = {"fixed", "planned", "preliminary", "open"}
VALID_CLASSIFICATIONS = {"training", "recreation"}
VALID_PLAN_RELATIONS = {"separate"}
VALID_PLAN_SPORTS = {"run", "swim", "bike", "strength", "enduro", "swimrun", "rest", "open"}
VALID_WORKOUT_STEP_KINDS = {"swim", "rest", "lap_rest"}
VALID_COACH_ACTIONS = {"keep", "reduce", "rest", "review"}
VALID_CONFIDENCE = {"low", "medium", "high"}

ACTIVITY_FAMILY = {
    "Run": "run",
    "TrailRun": "run",
    "VirtualRun": "run",
    "Swim": "swim",
    "Swimrun": "swimrun",
    "MountainBikeRide": "bike",
    "Ride": "bike",
    "VirtualRide": "bike",
    "WeightTraining": "strength",
    "Enduro": "enduro",
}

# Explicit plan type -> activity families that may fulfill the day.
# Swimrun is commonly exposed by the upstream activity source as a run-like
# activity, so either the raw run-family source activity or a normalized
# Swimrun activity may fulfill an explicitly planned swimrun.
# rest/open are intentional non-activity states and are never auto-fulfilled.
PLAN_SPORT_ACTIVITY_FAMILIES = {
    "run": {"run"},
    "swim": {"swim"},
    "bike": {"bike"},
    "strength": {"strength"},
    "enduro": {"enduro"},
    "swimrun": {"run", "swimrun"},
    "rest": set(),
    "open": set(),
}


class ContractError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def _iso_date(value, context):
    require(isinstance(value, str) and value, f"{context}: datum saknas")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{context}: ogiltigt ISO-datum {value!r}") from exc


def _nonempty_string(value, context):
    require(isinstance(value, str) and value.strip(), f"{context}: text saknas")


def _positive_int(value, context):
    require(isinstance(value, int) and not isinstance(value, bool) and value > 0, f"{context}: måste vara positivt heltal")


def _nonnegative_number(value, context):
    if value is None:
        return
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{context}: måste vara numeriskt")
    require(value >= 0, f"{context}: får inte vara negativt")


def _validate_baseline_dose_contract(day, context):
    baseline_id = str(day.get("baseline_option_id") or "").strip()
    if not baseline_id:
        return

    options = day.get("dose_options")
    require(
        isinstance(options, list) and options,
        f"{context}: baseline_option_id kräver en icke-tom dose_options-lista",
    )
    option_ids = set()
    option_by_id = {}
    for option_index, option in enumerate(options):
        option_context = f"{context}.dose_options[{option_index}]"
        require(isinstance(option, dict), f"{option_context}: måste vara objekt")
        option_id = str(option.get("id") or "").strip()
        _nonempty_string(option_id, f"{option_context}.id")
        require(option_id not in option_ids, f"{context}: dubbelt dose_options-id {option_id!r}")
        option_ids.add(option_id)
        option_by_id[option_id] = option
        _nonempty_string(option.get("kind"), f"{option_context}.kind")
        value = option.get("value")
        require(
            isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0,
            f"{option_context}.value måste vara positivt tal",
        )
        _nonempty_string(option.get("session"), f"{option_context}.session")

    require(
        baseline_id in option_ids,
        f"{context}: baseline_option_id {baseline_id!r} saknas i dose_options",
    )

    resolution = day.get("dose_resolution")
    if resolution is not None:
        require(isinstance(resolution, dict), f"{context}.dose_resolution måste vara objekt")
        resolution_id = str(resolution.get("option_id") or "").strip()
        if resolution_id:
            require(
                resolution_id in option_ids,
                f"{context}: dose_resolution.option_id {resolution_id!r} saknas i dose_options",
            )
        if resolution.get("state") == "baseline":
            require(
                resolution_id == baseline_id,
                f"{context}: baseline-resolution måste använda baseline_option_id",
            )
            require(
                day.get("session") == option_by_id[baseline_id].get("session"),
                f"{context}: baseline-session måste matcha baseline_option_id",
            )


def workout_distance_m(workout):
    total = 0
    for block in workout.get("blocks") or []:
        repeat = block.get("repeat", 1)
        _positive_int(repeat, f"workout block {block.get('name', '<utan namn>')} repeat")
        block_distance = 0
        steps = block.get("steps") or []
        require(isinstance(steps, list) and steps, f"workout block {block.get('name', '<utan namn>')}: steps saknas")
        for step in steps:
            kind = step.get("kind")
            require(kind in VALID_WORKOUT_STEP_KINDS, f"workout: ogiltig step kind {kind!r}")
            if kind == "swim":
                distance = step.get("distance_m")
                _positive_int(distance, "workout swim distance_m")
                block_distance += distance
            else:
                _positive_int(step.get("duration_s"), f"workout {kind} duration_s")
        total += repeat * block_distance
    return total


def validate_watch_workout(workout, context):
    require(isinstance(workout, dict), f"{context}: watch_workout måste vara objekt")
    require(isinstance(workout.get("sync_enabled"), bool), f"{context}: sync_enabled måste vara bool")
    _nonempty_string(workout.get("id"), f"{context}.id")
    require(workout.get("type") == "Swim", f"{context}: endast type='Swim' stöds")
    blocks = workout.get("blocks")
    require(isinstance(blocks, list) and blocks, f"{context}: blocks saknas")
    for block in blocks:
        _nonempty_string(block.get("name"), f"{context}.block.name")
    calculated = workout_distance_m(workout)
    planned = workout.get("planned_distance_m")
    if planned is not None:
        _positive_int(planned, f"{context}.planned_distance_m")
        require(calculated == planned, f"{context}: strukturerad distans {calculated} m != planned_distance_m {planned} m")
    if workout.get("sync_enabled") is True:
        _nonempty_string(workout.get("external_id"), f"{context}.external_id")
    return calculated


def validate_plan_document(document, *, upcoming=False):
    require(isinstance(document, dict), "plan: rot måste vara objekt")
    require(document.get("schema_version") == PLAN_SCHEMA_VERSION, f"plan: schema_version måste vara {PLAN_SCHEMA_VERSION}")

    meta = document.get("meta")
    require(isinstance(meta, dict), "plan.meta saknas")
    _nonempty_string(meta.get("timezone"), "plan.meta.timezone")
    require(isinstance(meta.get("week"), int), "plan.meta.week måste vara heltal")
    start = _iso_date(meta.get("week_start"), "plan.meta.week_start")
    end = _iso_date(meta.get("week_end"), "plan.meta.week_end")
    require(end == start + timedelta(days=6), "plan: week_end måste vara exakt sex dagar efter week_start")
    _nonempty_string(meta.get("title"), "plan.meta.title")
    _nonempty_string(meta.get("principle"), "plan.meta.principle")

    days = document.get("days")
    require(isinstance(days, list) and len(days) == 7, f"plan: exakt 7 dagar krävs, fick {len(days) if isinstance(days, list) else 'icke-lista'}")
    seen = set()
    for index, day in enumerate(days):
        context = f"plan.days[{index}]"
        require(isinstance(day, dict), f"{context}: måste vara objekt")
        day_date = _iso_date(day.get("date"), f"{context}.date")
        expected = start + timedelta(days=index)
        require(day_date == expected, f"{context}: förväntat datum {expected.isoformat()}, fick {day_date.isoformat()}")
        require(day_date.isoformat() not in seen, f"plan: dubbelt datum {day_date.isoformat()}")
        seen.add(day_date.isoformat())
        _nonempty_string(day.get("label"), f"{context}.label")
        require(day.get("status") in VALID_DAY_STATUSES, f"{context}: ogiltig status {day.get('status')!r}")
        sport = day.get("sport")
        require(sport in VALID_PLAN_SPORTS, f"{context}: explicit sport saknas/är ogiltig: {sport!r}")
        _nonempty_string(day.get("session"), f"{context}.session")
        _nonempty_string(day.get("reason"), f"{context}.reason")
        if "classification" in day:
            require(day.get("classification") in VALID_CLASSIFICATIONS, f"{context}: ogiltig classification")
        if upcoming:
            require(day.get("planning_status") in VALID_PLANNING_STATUSES, f"{context}: ogiltig planning_status")
        if "watch_workout" in day:
            validate_watch_workout(day["watch_workout"], f"{context}.watch_workout")
        _validate_baseline_dose_contract(day, context)

    if upcoming:
        require(document.get("state") == "preliminary", "upcoming plan: state måste vara 'preliminary'")
        _nonempty_string(document.get("week_key"), "upcoming plan.week_key")
    return True


def validate_activities_document(document):
    require(isinstance(document, dict), "activities: rot måste vara objekt")
    require(document.get("schema_version") == ACTIVITIES_SCHEMA_VERSION, f"activities: schema_version måste vara {ACTIVITIES_SCHEMA_VERSION}")
    activities = document.get("activities")
    require(isinstance(activities, list), "activities.activities måste vara lista")
    seen = set()
    for index, activity in enumerate(activities):
        context = f"activities[{index}]"
        require(isinstance(activity, dict), f"{context}: måste vara objekt")
        activity_id = activity.get("id")
        require(activity_id is not None, f"{context}: id saknas")
        key = str(activity_id)
        require(key not in seen, f"activities: dubbelt id {key}")
        seen.add(key)
        _nonempty_string(activity.get("sport_type"), f"{context}.sport_type")
        local = activity.get("start_date_local") or activity.get("start_date")
        require(isinstance(local, str) and len(local) >= 10, f"{context}: startdatum saknas")
        _iso_date(local[:10], f"{context}.startdatum")
        for field in ("distance_m", "moving_time_s", "elapsed_time_s", "total_elevation_gain_m", "average_heartrate", "max_heartrate", "average_watts", "weighted_average_watts", "calories"):
            _nonnegative_number(activity.get(field), f"{context}.{field}")
        if "classification" in activity:
            require(activity.get("classification") in VALID_CLASSIFICATIONS, f"{context}: ogiltig classification")
        if "display_label" in activity:
            _nonempty_string(activity.get("display_label"), f"{context}.display_label")
        if "plan_relation" in activity:
            require(activity.get("plan_relation") in VALID_PLAN_RELATIONS, f"{context}: ogiltig plan_relation")
        if "laps" in activity:
            laps = activity.get("laps")
            require(isinstance(laps, list), f"{context}.laps måste vara lista")
            for lap_index, lap in enumerate(laps):
                lap_context = f"{context}.laps[{lap_index}]"
                require(isinstance(lap, dict), f"{lap_context}: måste vara objekt")
                for field in (
                    "elapsed_time_s",
                    "moving_time_s",
                    "distance_m",
                    "average_speed",
                    "average_heartrate",
                    "max_heartrate",
                    "average_watts",
                    "average_cadence",
                ):
                    _nonnegative_number(lap.get(field), f"{lap_context}.{field}")
    return True



def validate_performance_history_document(document, activity_ids=None):
    require(isinstance(document, dict), "performance_history: rot måste vara objekt")
    require(document.get("schema_version") == 1, "performance_history: schema_version måste vara 1")
    entries = document.get("entries")
    require(isinstance(entries, list), "performance_history.entries måste vara lista")
    seen = set()
    for index, entry in enumerate(entries):
        context = f"performance_history.entries[{index}]"
        require(isinstance(entry, dict), f"{context}: måste vara objekt")
        activity_id = entry.get("activity_id")
        require(activity_id is not None, f"{context}.activity_id saknas")
        key = str(activity_id)
        require(key not in seen, f"performance_history: dubbelt activity_id {key}")
        seen.add(key)
        if activity_ids is not None:
            require(key in activity_ids, f"{context}: activity_id {key} saknas i activities.json")
        _iso_date(entry.get("activity_date"), f"{context}.activity_date")
        _nonempty_string(entry.get("marker_id"), f"{context}.marker_id")
        _nonempty_string(entry.get("protocol_key"), f"{context}.protocol_key")
        require(entry.get("marker_id") == "run-threshold-control", f"{context}: endast run-threshold-control stöds i v1")
        intervals = entry.get("work_intervals")
        require(isinstance(intervals, list) and intervals, f"{context}.work_intervals saknas")
        for interval_index, interval in enumerate(intervals):
            interval_context = f"{context}.work_intervals[{interval_index}]"
            require(isinstance(interval, dict), f"{interval_context}: måste vara objekt")
            _positive_int(interval.get("index"), f"{interval_context}.index")
            for field in (
                "duration_s",
                "distance_m",
                "pace_s_per_km",
                "average_heartrate",
                "max_heartrate",
                "average_watts",
                "average_cadence",
            ):
                _nonnegative_number(interval.get(field), f"{interval_context}.{field}")
        summary = entry.get("summary")
        require(isinstance(summary, dict), f"{context}.summary saknas")
        _positive_int(summary.get("work_interval_count"), f"{context}.summary.work_interval_count")
        for field in (
            "total_work_s",
            "mean_pace_s_per_km",
            "mean_heartrate",
            "mean_watts",
        ):
            _nonnegative_number(summary.get(field), f"{context}.summary.{field}")
        for field in (
            "first_to_last_pace_delta_s_per_km",
            "first_to_last_hr_delta",
            "first_to_last_watts_delta",
        ):
            value = summary.get(field)
            if value is not None:
                require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{context}.summary.{field} måste vara numeriskt")
        comparison = entry.get("comparison")
        if comparison is not None:
            require(isinstance(comparison, dict), f"{context}.comparison måste vara objekt/null")
            require(comparison.get("same_protocol") is True, f"{context}.comparison.same_protocol måste vara true")
            require(comparison.get("previous_activity_id") is not None, f"{context}.comparison.previous_activity_id saknas")
            for field in (
                "mean_pace_delta_s_per_km",
                "mean_hr_delta",
                "mean_watts_delta",
                "total_work_delta_s",
            ):
                value = comparison.get(field)
                if value is not None:
                    require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{context}.comparison.{field} måste vara numeriskt")
    return True

def validate_coach_document(document, activity_ids=None):
    require(isinstance(document, dict), "coach: rot måste vara objekt")
    analyses = document.get("analyses") or []
    require(isinstance(analyses, list), "coach.analyses måste vara lista")
    if not analyses:
        return True
    require(int(document.get("contract_version") or 0) >= MIN_COACH_CONTRACT_VERSION, f"coach: contract_version måste vara >= {MIN_COACH_CONTRACT_VERSION}")

    seen = set()
    for index, entry in enumerate(analyses):
        context = f"coach.analyses[{index}]"
        activity_id = entry.get("activity_id")
        require(activity_id is not None, f"{context}: activity_id saknas")
        key = str(activity_id)
        require(key not in seen, f"coach: dubbelt activity_id {key}")
        seen.add(key)
        if activity_ids is not None:
            require(key in activity_ids, f"{context}: activity_id {key} saknas i activities.json")
        _iso_date(entry.get("activity_date"), f"{context}.activity_date")
        assessment = entry.get("assessment")
        require(isinstance(assessment, dict), f"{context}.assessment saknas")
        require(assessment.get("confidence") in VALID_CONFIDENCE, f"{context}: ogiltig confidence")
        for field in ("facts", "interpretations", "unknowns"):
            value = assessment.get(field)
            require(isinstance(value, list), f"{context}.assessment.{field} måste vara lista")
            require(all(isinstance(item, str) and item.strip() for item in value), f"{context}.assessment.{field} innehåller ogiltigt värde")
        if assessment.get("confidence") == "high":
            require(not assessment.get("unknowns"), f"{context}: high confidence får inte ha unknowns")
        _nonempty_string(assessment.get("summary"), f"{context}.assessment.summary")
        _nonempty_string(assessment.get("load_interpretation"), f"{context}.assessment.load_interpretation")
        action = entry.get("plan_action")
        require(isinstance(action, dict), f"{context}.plan_action saknas")
        require(action.get("action") in VALID_COACH_ACTIONS, f"{context}: ogiltig coach action")
        target = str(action.get("target_date") or "")
        if target:
            _iso_date(target, f"{context}.plan_action.target_date")
        if action.get("action") in {"reduce", "rest"}:
            require(bool(target), f"{context}: reduce/rest kräver target_date")
        require(isinstance(action.get("requires_approval"), bool), f"{context}: requires_approval måste vara bool")
    return True
