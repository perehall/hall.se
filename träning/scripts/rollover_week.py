#!/usr/bin/env python3
import json
import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from strategy_contracts import validate_training_strategy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PLAN_FILE = DATA_DIR / "plan.json"
UPCOMING_FILE = DATA_DIR / "upcoming_week.json"
ACTIVITIES_FILE = DATA_DIR / "activities.json"
COACH_FILE = DATA_DIR / "coach.json"
STRATEGY_FILE = DATA_DIR / "training_strategy.json"
WEEKS_DIR = DATA_DIR / "weeks"

WEEKDAY_LABELS = (
    "Måndag",
    "Tisdag",
    "Onsdag",
    "Torsdag",
    "Fredag",
    "Lördag",
    "Söndag",
)

# Fast användaråtagande: åtta måndagar med enduroskola från 2026-08-24.
# Detta är träningsbelastning, inte en fri/öppen dag och inte automatiskt rekreation.
ENDURO_SCHOOL_START = date(2026, 8, 24)
ENDURO_SCHOOL_OCCURRENCES = 8

SWIM_FOCUS_CYCLE = (
    "Sätt handen rent framför axeln och etablera greppet tidigt utan att pressa handen nedåt; håll huvudet stilla.",
    "Rotera runt en stabil kroppslinje: låt höft och axel följa med utan att huvudet vandrar eller benen börjar slingra.",
    "Låt återföringen vara avslappnad och isättningen ren; behåll ett tidigt grepp när handen går i vattnet.",
    "Öka frekvensen utan att korta draget eller tappa greppet bakåt; rytm får inte ersätta vattenkänsla.",
)

DOSE_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?(?:\s*[–-]\s*\d+(?:[.,]\d+)?)?\s*(?:min|h|km|m)\b",
    re.IGNORECASE,
)
CLOCK_DURATION_PATTERN = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")


def load_json(path, fallback=None):
    if not path.exists():
        return {} if fallback is None else fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def activity_local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date") or ""
    return value[:10] if isinstance(value, str) and len(value) >= 10 else ""


def week_key(start):
    iso = start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def has_explicit_dose(session):
    session = str(session or "")
    return bool(DOSE_PATTERN.search(session) or CLOCK_DURATION_PATTERN.search(session))


def _option_by_id(options, option_id):
    return next((item for item in (options or []) if item.get("id") == option_id), None)


def apply_baseline_option(day, baseline_option_id=None):
    """Make a pre-approved concrete option the visible baseline plan.

    Alternative options remain available for conservative adjustment, but the
    athlete is never asked to wait for the previous session before seeing a
    usable plan.
    """
    options = day.get("dose_options") or []
    option_id = baseline_option_id or day.get("baseline_option_id")
    option = _option_by_id(options, option_id)
    if option is None:
        return False
    day["baseline_option_id"] = option_id
    day["session"] = option["session"]
    day["dose_open"] = False
    day["dose_resolution"] = {
        "state": "baseline",
        "kind": option.get("kind"),
        "value": option.get("value"),
        "option_id": option_id,
    }
    return True


def is_enduro_school_date(day_date):
    if isinstance(day_date, str):
        day_date = date.fromisoformat(day_date)
    delta = (day_date - ENDURO_SCHOOL_START).days
    if delta < 0 or delta % 7 != 0:
        return False
    occurrence = delta // 7
    return occurrence < ENDURO_SCHOOL_OCCURRENCES


def fixed_enduro_school_day(day_date, label="Måndag"):
    if isinstance(day_date, str):
        day_date = date.fromisoformat(day_date)
    return {
        "date": day_date.isoformat(),
        "label": label,
        "status": "planned",
        "planning_status": "fixed",
        "session": "Enduroskola · fast tillfälle",
        "reason": (
            "Fast återkommande enduroskola, totalt åtta måndagar från 24/8. "
            "Enduron räknas som faktisk träningsbelastning; övrig träning runt dagen anpassas efter utfallet."
        ),
        "development_focus": "Teknisk kvalitet och avslappnad körning; faktisk belastning styr efterföljande pass.",
        "sport": "enduro",
        "classification": "training",
        "manual_lock": True,
        "priority_role": "flex",
        "stimuli": ["enduro_technical"],
    }


def seed_fixed_commitments(week_document):
    for index, day in enumerate(week_document.get("days") or []):
        day_date = date.fromisoformat(day["date"])
        if is_enduro_school_date(day_date):
            fixed = fixed_enduro_school_day(day_date, day.get("label") or "Måndag")
            for field in (
                "mesocycle_id",
                "microcycle_id",
                "microcycle_index",
                "microcycle_day",
            ):
                if day.get(field) is not None:
                    fixed[field] = day[field]
            week_document["days"][index] = fixed
    return week_document


def validate_week_bounds(meta, context):
    try:
        start = date.fromisoformat(meta["week_start"])
        end = date.fromisoformat(meta["week_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Veckoskifte: {context} saknar giltiga veckodatum") from exc
    if end != start + timedelta(days=6):
        raise RuntimeError(f"Veckoskifte: {context} omfattar inte exakt sju dagar")
    return start, end


def snapshot_closed_week(plan, activities_state, coach_state, *, now_utc=None):
    meta = plan.get("meta") or {}
    start, end = validate_week_bounds(meta, "aktiv plan")
    key = week_key(start)
    path = WEEKS_DIR / f"{key}.json"
    previous = load_json(path, {})
    stamp = now_utc or datetime.now(timezone.utc).isoformat()
    start_text = start.isoformat()
    end_text = end.isoformat()
    activities = [
        activity
        for activity in (activities_state.get("activities") or [])
        if start_text <= activity_local_date(activity) <= end_text
    ]
    analyses = [
        entry
        for entry in (coach_state.get("analyses") or [])
        if start_text <= str(entry.get("activity_date") or "") <= end_text
    ]
    snapshot = {
        "schema_version": 1,
        "week_key": key,
        "week_start": start_text,
        "week_end": end_text,
        "created_at_utc": previous.get("created_at_utc") or stamp,
        "updated_at_utc": stamp,
        "plan": deepcopy(plan),
        "activities": activities,
        "coach_analyses": analyses,
    }
    return path, snapshot


def promote_upcoming(upcoming):
    promoted = deepcopy(upcoming)
    promoted.pop("state", None)
    promoted.pop("week_key", None)
    meta = promoted.get("meta") or {}
    meta.pop("preview_summary", None)

    for day in promoted.get("days") or []:
        day.pop("planning_status", None)

        if day.get("dose_open") is True and (day.get("dose_options") or []):
            apply_baseline_option(day)
        elif day.get("dose_open") is True:
            # Legacy externally structured/fixed sessions may not have a numeric
            # option. Keep the known session concrete instead of surfacing
            # artificial uncertainty.
            day.pop("dose_open", None)

    return seed_fixed_commitments(promoted)


def _clean_preview_swim(source, target_date, target_label, next_key, focus_index):
    workout = deepcopy(source.get("watch_workout") or {})
    if not workout or workout.get("planned_distance_m") is None or not workout.get("blocks"):
        raise RuntimeError(
            f"Veckoskifte: simpass {source.get('date')} saknar strukturerat watch_workout; "
            "kan inte skapa ett gissningsfritt preliminärt simpass."
        )
    equipment = deepcopy(source.get("swim_equipment") or {})
    if "planned" not in equipment:
        raise RuntimeError(
            f"Veckoskifte: simpass {source.get('date')} saknar swim_equipment.planned"
        )

    copied = deepcopy(source)
    copied["date"] = target_date.isoformat()
    copied["label"] = target_label
    copied["status"] = "preliminary"
    copied["planning_status"] = "preliminary"
    copied["sport"] = "swim"
    copied["swim_equipment"] = equipment
    copied["development_focus"] = SWIM_FOCUS_CYCLE[focus_index % len(SWIM_FOCUS_CYCLE)]
    copied["reason"] = (
        "Preliminär simstruktur förs vidare från föregående veckas etablerade simdos för kontinuitet. "
        "Totaldosen ökas inte automatiskt; slutlig dos och intensitet omprövas mot faktisk belastning "
        "och återhämtning från de närmast föregående 2–3 dagarna."
    )

    for field in (
        "actual_swim_equipment",
        "coach_adjustment",
        "auto_coach",
        "original_session",
        "rollover_status_from",
        "reference",
    ):
        copied.pop(field, None)

    workout["sync_enabled"] = False
    workout.pop("external_id", None)
    workout["id"] = f"swim-{next_key.lower()}-{target_date.isoformat()}-preview"
    copied["watch_workout"] = workout
    return copied


def seed_preliminary_swims(promoted, future):
    next_start, _ = validate_week_bounds(future.get("meta") or {}, "framtidsplan")
    next_key = future["week_key"]
    sources = [day for day in promoted.get("days") or [] if day.get("sport") == "swim"]
    targets = [
        (index, day)
        for index, day in enumerate(future.get("days") or [])
        if day.get("sport") == "swim"
    ]

    for ordinal, ((target_index, target), source) in enumerate(zip(targets, sources)):
        target_date = date.fromisoformat(target["date"])
        copied = _clean_preview_swim(
            source,
            target_date,
            target.get("label") or WEEKDAY_LABELS[target_index],
            next_key,
            focus_index=next_start.isocalendar().week + ordinal,
        )
        copied["priority_role"] = target.get("priority_role") or copied.get("priority_role") or "flex"
        copied["stimuli"] = deepcopy(target.get("stimuli") or copied.get("stimuli") or [])
        copied["mesocycle_id"] = target.get("mesocycle_id")
        copied["microcycle_id"] = target.get("microcycle_id")
        copied["microcycle_index"] = target.get("microcycle_index")
        copied["microcycle_slot"] = target.get("microcycle_slot")
        future["days"][target_index] = copied
    return future


def mesocycle_microcycle_state(mesocycle, cycle_start):
    start = date.fromisoformat(mesocycle["start_date"])
    end = date.fromisoformat(mesocycle["end_date"])
    length_days = int((mesocycle.get("microcycle_structure") or {}).get("length_days") or 7)
    total_microcycles = max(1, ((end - start).days + 1 + length_days - 1) // length_days)
    if not (start <= cycle_start <= end):
        return None, total_microcycles
    index = ((cycle_start - start).days // length_days) + 1
    return index, total_microcycles


def build_mesocycle_next_week(promoted, strategy):
    validate_training_strategy(strategy)
    meta = promoted.get("meta") or {}
    _, current_end = validate_week_bounds(meta, "promoverad plan")
    next_start = current_end + timedelta(days=1)
    next_end = next_start + timedelta(days=6)
    next_iso = next_start.isocalendar()
    timezone_name = meta.get("timezone") or "Europe/Stockholm"
    mesocycle = strategy["current_mesocycle"]
    microcycle_index, total_microcycles = mesocycle_microcycle_state(mesocycle, next_start)
    microcycle_length = int(mesocycle["microcycle_structure"]["length_days"])

    days = []
    for offset, label in enumerate(WEEKDAY_LABELS):
        day_date = next_start + timedelta(days=offset)
        days.append(
            {
                "date": day_date.isoformat(),
                "label": label,
                "status": "open",
                "planning_status": "open",
                "session": "Ingen planerad träning",
                "reason": (
                    "Ingen träning är planerad som standard på denna dag. En ledig dag är inte i sig skäl "
                    "att lägga till ett pass; eventuell ändring ska tjäna mikrocykeln och bygga på faktisk information."
                ),
                "sport": "open",
            }
        )

    inside_mesocycle = (
        microcycle_index is not None
        and date.fromisoformat(mesocycle["start_date"]) <= next_start
        and next_end <= date.fromisoformat(mesocycle["end_date"])
    )

    if inside_mesocycle:
        for slot in mesocycle["microcycle_template"]:
            offset = int(slot["day_index"]) - 1
            day_date = next_start + timedelta(days=offset)
            planned_day = {
                "date": day_date.isoformat(),
                "label": WEEKDAY_LABELS[offset],
                "status": "preliminary",
                "planning_status": "preliminary",
                "session": slot["session"],
                "reason": slot["reason"],
                "development_focus": slot["development_focus"],
                "sport": slot["sport"],
                "priority_role": slot["priority_role"],
                "stimuli": deepcopy(slot["stimuli"]),
                "mesocycle_id": mesocycle["id"],
                "microcycle_id": f'{mesocycle["id"]}:mc{microcycle_index}',
                "microcycle_index": microcycle_index,
                "microcycle_day": int(slot["day_index"]),
                "microcycle_slot": slot["slot"],
            }
            if slot.get("dose_options"):
                planned_day["dose_options"] = deepcopy(slot["dose_options"])
                planned_day["baseline_option_id"] = slot["baseline_option_id"]
                if not apply_baseline_option(planned_day, slot["baseline_option_id"]):
                    raise RuntimeError(
                        f"Veckoplan: baseline_option_id {slot['baseline_option_id']!r} saknas för {slot['slot']!r}"
                    )
            if slot["sport"] == "swim":
                planned_day["swim_equipment"] = {"planned": "tbd"}
            days[offset] = planned_day

        title = f'{mesocycle["title"]} · mikrocykel {microcycle_index} av {total_microcycles}'
        principle = (
            mesocycle["goal_contribution"]
            + " Mikrocykeln är preliminär men konkret: varje planerat pass har en användbar grundplan. "
              "Faktisk belastning och återhämtning används för att behålla eller justera planen, inte för att skapa den i sista stund. "
              "Kalenderveckan är bara visningen."
        )
        preview_summary = (
            f'Mikrocykel {microcycle_index} av {total_microcycles} i aktuell mesocykel. '
            "Skyddade stimuli: "
            + ", ".join(mesocycle["protected_stimuli"])
            + ". Grundpassen är konkreta och får inte ökas automatiskt; justering kräver stöd i faktisk information."
        )
    else:
        title = "Mesocykel avslutad · utvärdering krävs"
        principle = (
            "Ingen ny utvecklingsriktning skapas automatiskt efter avslutad mesocykel. "
            "Fasta åtaganden kan ligga kvar, men nästa mesocykel ska väljas först efter utvärdering mot målbilden och faktisk respons."
        )
        preview_summary = (
            "Övergångsperiod. Systemet väntar på mesocykelutvärdering innan en ny mikrocykel med utvecklingsstimuli planeras."
        )

    future = {
        "schema_version": int(promoted.get("schema_version") or 3),
        "state": "preliminary",
        "week_key": week_key(next_start),
        "meta": {
            "timezone": timezone_name,
            "week": next_iso.week,
            "week_start": next_start.isoformat(),
            "week_end": next_end.isoformat(),
            "title": title,
            "principle": principle,
            "preview_summary": preview_summary,
            "mesocycle_id": mesocycle["id"] if inside_mesocycle else "",
            "microcycle_id": f'{mesocycle["id"]}:mc{microcycle_index}' if inside_mesocycle else "",
            "microcycle_index": microcycle_index if inside_mesocycle else None,
            "microcycle_total": total_microcycles,
            "microcycle_length_days": microcycle_length,
            "calendar_week_is_presentation": True,
            "requires_mesocycle_review": not inside_mesocycle,
        },
        "days": days,
        "strength_template": deepcopy(promoted.get("strength_template") or []),
    }

    if inside_mesocycle:
        future = seed_preliminary_swims(promoted, future)

    future = seed_fixed_commitments(future)

    if inside_mesocycle:
        for offset, day in enumerate(future["days"]):
            if day.get("sport") not in {"open", "rest"}:
                day["mesocycle_id"] = mesocycle["id"]
                day["microcycle_id"] = f'{mesocycle["id"]}:mc{microcycle_index}'
                day["microcycle_index"] = microcycle_index
                day["microcycle_day"] = offset + 1

        actual_stimuli = {
            stimulus
            for day in future["days"]
            for stimulus in (day.get("stimuli") or [])
        }
        missing = [
            stimulus
            for stimulus in mesocycle["protected_stimuli"]
            if stimulus not in actual_stimuli
        ]
        future["meta"]["missing_protected_stimuli"] = missing
        future["meta"]["requires_mesocycle_review"] = bool(missing)
        if missing:
            future["meta"]["preview_summary"] += (
                " Skyddat stimulus saknar plats efter fasta åtaganden och måste lösas i närtidsplaneringen: "
                + ", ".join(missing)
                + "."
            )
    return future


# Kalenderveckan är publiceringsformatet; innehållet byggs som nästa mikrocykel.
def build_open_next_week(promoted, strategy=None):
    if strategy is None:
        raise RuntimeError("Veckoskifte: training_strategy krävs för att bygga nästa mikrocykel")
    return build_mesocycle_next_week(promoted, strategy)


def rollover_documents(plan, upcoming, today, strategy):
    plan_meta = plan.get("meta") or {}
    upcoming_meta = upcoming.get("meta") or {}
    _, current_end = validate_week_bounds(plan_meta, "aktiv plan")
    upcoming_start, upcoming_end = validate_week_bounds(upcoming_meta, "kommande plan")

    if today <= current_end:
        return None
    if upcoming_start != current_end + timedelta(days=1):
        raise RuntimeError(
            "Veckoskifte: upcoming_week börjar inte dagen efter aktiv veckas slut; vägrar promovera."
        )
    if not (upcoming_start <= today <= upcoming_end):
        raise RuntimeError(
            "Veckoskifte: aktiv plan ligger mer än en kalendervecka efter; manuell återställning krävs."
        )

    promoted = promote_upcoming(upcoming)
    promoted_start, _ = validate_week_bounds(promoted.get("meta") or {}, "promoverad plan")
    if promoted_start != upcoming_start:
        raise RuntimeError("Veckoskifte: promoveringen ändrade veckodatumen oväntat")
    next_preview = build_mesocycle_next_week(promoted, strategy)
    return promoted, next_preview


def main(*, today_local=None):
    plan = load_json(PLAN_FILE)
    upcoming = load_json(UPCOMING_FILE)
    activities_state = load_json(ACTIVITIES_FILE, {"activities": []})
    coach_state = load_json(COACH_FILE, {"analyses": []})
    strategy = load_json(STRATEGY_FILE)
    validate_training_strategy(strategy)

    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    tz = ZoneInfo(timezone_name)
    today = today_local or datetime.now(tz).date()
    if isinstance(today, str):
        today = date.fromisoformat(today)

    result = rollover_documents(plan, upcoming, today, strategy)
    if result is None:
        start, _ = validate_week_bounds((plan.get("meta") or {}), "aktiv plan")
        print(f"Veckoskifte: ingen ändring; {week_key(start)} är fortfarande aktuell.")
        return 0

    promoted, next_preview = result
    archive_path, snapshot = snapshot_closed_week(plan, activities_state, coach_state)
    write_json(archive_path, snapshot)
    write_json(PLAN_FILE, promoted)
    write_json(UPCOMING_FILE, next_preview)

    old_key = snapshot["week_key"]
    new_key = week_key(date.fromisoformat(promoted["meta"]["week_start"]))
    future_key = next_preview["week_key"]
    print(
        f"Veckoskifte OK: {old_key} historik, {new_key} aktiv, {future_key} preliminär framtid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
