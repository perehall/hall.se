#!/usr/bin/env python3
from datetime import date, timedelta


PLAN_SCHEMA_VERSION = 3
ACTIVITIES_SCHEMA_VERSION = 2
MIN_COACH_CONTRACT_VERSION = 3

VALID_DAY_STATUSES = {"completed", "planned", "preliminary", "conditional", "open"}
VALID_PLANNING_STATUSES = {"fixed", "planned", "preliminary", "open"}
VALID_CLASSIFICATIONS = {"training", "recreation"}
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
