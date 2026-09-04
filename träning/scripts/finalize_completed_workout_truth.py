#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from coach_rules import matching_activity, planning_window
from finalize_human_training_language import (
    explicit_interval_structure,
    humanize_post_workout_details,
    visible_training_language,
)
from finalize_post_workout_ui import (
    CARD_MARKER,
    find_coach_analysis,
    find_performance,
    next_planned_day,
    render_post_workout,
)

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
COACH_FILE = ROOT / "data" / "coach.json"
PERFORMANCE_FILE = ROOT / "data" / "performance_history.json"


def load(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def local_date(activity):
    value = str(activity.get("start_date_local") or activity.get("start_date") or "")
    return value[:10] if len(value) >= 10 else ""


def activities_on_date(activities, day_text):
    return [item for item in activities if local_date(item) == day_text]


def fulfilled_activity(day, activities):
    same_day = activities_on_date(activities, str(day.get("date") or ""))
    if not same_day:
        return None
    return matching_activity(day, same_day)


def day_card_ranges(page):
    pattern = re.compile(r'<div class="day[^"]*" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">')
    matches = list(pattern.finditer(page))
    return [
        (
            match.start(),
            matches[index + 1].start() if index + 1 < len(matches) else len(page),
            match.group("date"),
        )
        for index, match in enumerate(matches)
    ]


def force_completed_badges(page, plan, activities):
    fulfilled_dates = {
        str(day.get("date"))
        for day in (plan.get("days") or [])
        if fulfilled_activity(day, activities)
    }
    for start, end, day_text in reversed(day_card_ranges(page)):
        if day_text not in fulfilled_dates:
            continue
        block = page[start:end]
        block, count = re.subn(
            r'<div class="badge [^"]+">[^<]*</div>',
            '<div class="badge fixed">Genomfört</div>',
            block,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"Genomfört-kontrakt: statusbadge saknas för {day_text}")
        page = page[:start] + block + page[end:]
    return page


def replace_current_post_workout_card(
    page,
    decision_plan,
    activities_state,
    coach_state,
    performance_history,
    today,
):
    day = next((item for item in decision_plan.get("days") or [] if item.get("date") == today), None)
    if not day:
        return page, None

    activities = activities_state.get("activities") or []
    activity = fulfilled_activity(day, activities)
    if not activity:
        return page, None

    analysis = find_coach_analysis(day, coach_state, today)
    performance = find_performance(activity, performance_history)
    next_day = next_planned_day(decision_plan, today)

    # "Plan före passet" means the last effective prescription the athlete had
    # before starting, not the older baseline stored in original_session.
    render_day = dict(day)
    render_day["planned_session"] = str(day.get("session") or "").strip()

    card = render_post_workout(
        render_day,
        activity,
        analysis,
        next_day,
        performance=performance,
    )
    reported_structure = explicit_interval_structure(activity.get("user_report"))
    card = humanize_post_workout_details(card, reported_structure=reported_structure)
    card = visible_training_language(card)

    card_pattern = re.compile(
        r'<section class="today-outcome"[^>]*data-post-workout-state="completed"[^>]*>.*?</section>',
        re.S,
    )
    page, count = card_pattern.subn(card, page, count=1)
    if count != 1:
        if CARD_MARKER in page:
            raise RuntimeError("Genomfört-kontrakt: kunde inte avgränsa befintligt efterpasskort")
        raise RuntimeError("Genomfört-kontrakt: efterpasskort saknas trots genomfört dagens pass")
    return page, {
        "day": day,
        "activity": activity,
        "analysis": analysis,
        "reported_structure": reported_structure,
    }


def current_card(page):
    match = re.search(
        r'<section class="today-outcome"[^>]*data-post-workout-state="completed"[^>]*>.*?</section>',
        page,
        re.S,
    )
    return match.group(0) if match else ""


def assert_completed_truth(page, plan, activities, today_context):
    for day in plan.get("days") or []:
        if not fulfilled_activity(day, activities):
            continue
        day_text = str(day.get("date") or "")
        match = re.search(
            rf'<div class="day[^"]*" id="dag-{re.escape(day_text)}">(.*?)(?=<div class="day[^"]*" id="dag-|<footer>|$)',
            page,
            re.S,
        )
        if not match:
            raise RuntimeError(f"Genomfört-kontrakt: dagkort saknas för {day_text}")
        badge = re.search(r'<div class="badge [^"]+">([^<]*)</div>', match.group(1))
        if not badge or badge.group(1).strip() != "Genomfört":
            raise RuntimeError(f"Genomfört-kontrakt: {day_text} visas inte som Genomfört")

    if not today_context:
        return

    card = current_card(page)
    day = today_context["day"]
    analysis = today_context["analysis"]
    reported_structure = today_context["reported_structure"]
    expected_plan = str(day.get("session") or "").strip()

    plan_match = re.search(
        r'<span class="today-outcome-label">Plan före passet</span><strong>(.*?)</strong>',
        card,
        re.S,
    )
    if not plan_match or html.unescape(re.sub(r"<[^>]+>", "", plan_match.group(1))).strip() != expected_plan:
        raise RuntimeError("Genomfört-kontrakt: Plan före passet är inte sista gällande ordination")

    if reported_structure:
        outcome_match = re.search(
            r'<span class="today-outcome-label">Genomfört</span><strong>(.*?)</strong>',
            card,
            re.S,
        )
        outcome = html.unescape(re.sub(r"<[^>]+>", "", outcome_match.group(1))).strip() if outcome_match else ""
        if outcome != reported_structure:
            raise RuntimeError(
                f"Genomfört-kontrakt: utfall {outcome!r} avviker från användarrapport {reported_structure!r}"
            )

    if analysis:
        interpretations = (analysis.get("assessment") or {}).get("interpretations") or []
        for item in interpretations:
            if str(item).strip() and html.escape(str(item).strip()) not in card:
                raise RuntimeError("Genomfört-kontrakt: efterpasskortet visar inte aktuell coachanalys")


def finalize_page(page, plan, upcoming, activities_state, coach_state, performance_history, today):
    activities = activities_state.get("activities") or []
    page = force_completed_badges(page, plan, activities)
    decision_plan = planning_window(plan, upcoming)
    page, today_context = replace_current_post_workout_card(
        page,
        decision_plan,
        activities_state,
        coach_state,
        performance_history,
        today,
    )
    assert_completed_truth(page, plan, activities, today_context)
    return page


def main():
    plan = load(PLAN_FILE, {})
    upcoming = load(UPCOMING_FILE, {})
    activities = load(ACTIVITIES_FILE, {"activities": []})
    coach = load(COACH_FILE, {"analyses": []})
    performance = load(PERFORMANCE_FILE, {"schema_version": 1, "entries": []})
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today = datetime.now(ZoneInfo(timezone_name)).date().isoformat()

    page = INDEX_FILE.read_text(encoding="utf-8")
    rendered = finalize_page(page, plan, upcoming, activities, coach, performance, today)
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    print("Genomfört-kontrakt OK: status, sista ordination, utfall och coachunderlag är synkade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
