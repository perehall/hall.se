#!/usr/bin/env python3
import json
import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PLAN_FILE = DATA_DIR / "plan.json"
UPCOMING_FILE = DATA_DIR / "upcoming_week.json"
ACTIVITIES_FILE = DATA_DIR / "activities.json"
COACH_FILE = DATA_DIR / "coach.json"
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

        # Enduro is a recreation classification in this training model. It may
        # be fixed in the calendar without inventing a training dose.
        if day.get("sport") == "enduro" and "classification" not in day:
            day["classification"] = "recreation"

        status = day.get("status")
        sport = day.get("sport")
        classification = day.get("classification")
        session = day.get("session") or ""
        if (
            status in {"planned", "preliminary", "conditional"}
            and sport not in {"rest", "open"}
            and classification != "recreation"
            and not has_explicit_dose(session)
        ):
            day["status"] = "open"
            day["rollover_status_from"] = status
            note = (
                "Ingen träningsdos var fastställd när veckan blev aktiv; passet är därför öppet "
                "tills faktisk belastning och återhämtning ger underlag."
            )
            reason = str(day.get("reason") or "").strip()
            day["reason"] = f"{reason} {note}".strip()

    return promoted


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
    current_start, _ = validate_week_bounds(promoted.get("meta") or {}, "promoverad plan")
    next_start, _ = validate_week_bounds(future.get("meta") or {}, "framtidsplan")
    next_key = future["week_key"]
    swim_days = [day for day in promoted.get("days") or [] if day.get("sport") == "swim"]

    for ordinal, source in enumerate(swim_days):
        source_date = date.fromisoformat(source["date"])
        offset = (source_date - current_start).days
        if not 0 <= offset <= 6:
            raise RuntimeError("Veckoskifte: simpass ligger utanför promoverad vecka")
        target_date = next_start + timedelta(days=offset)
        future["days"][offset] = _clean_preview_swim(
            source,
            target_date,
            WEEKDAY_LABELS[offset],
            next_key,
            focus_index=next_start.isocalendar().week + ordinal,
        )
    return future


def build_open_next_week(promoted):
    meta = promoted.get("meta") or {}
    _, current_end = validate_week_bounds(meta, "promoverad plan")
    next_start = current_end + timedelta(days=1)
    next_end = next_start + timedelta(days=6)
    next_iso = next_start.isocalendar()
    timezone_name = meta.get("timezone") or "Europe/Stockholm"

    days = []
    for offset, label in enumerate(WEEKDAY_LABELS):
        day_date = next_start + timedelta(days=offset)
        days.append(
            {
                "date": day_date.isoformat(),
                "label": label,
                "status": "open",
                "planning_status": "open",
                "session": "Öppet · planeras när underlag finns",
                "reason": (
                    "Ingen träningsdos sätts ännu. Passet planeras utifrån faktisk belastning, "
                    "återhämtning och de närmast föregående 2–3 dagarna."
                ),
                "sport": "open",
            }
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
            "title": "Preliminär framtidsvecka",
            "principle": (
                "Veckan hålls öppen tills faktisk belastning och återhämtning ger tillräckligt underlag. "
                "Etablerade simpass förs preliminärt vidare utan automatisk volymökning; övriga dagar fylls inte ut."
            ),
            "preview_summary": (
                "Översiktsvecka utan påhittad belastningsökning. Etablerade simpass skrivs ut preliminärt "
                "med tekniskt utvecklingsfokus; övriga pass sätts när aktuell veckas utfall är känt."
            ),
        },
        "days": days,
        "strength_template": deepcopy(promoted.get("strength_template") or []),
    }
    return seed_preliminary_swims(promoted, future)


def rollover_documents(plan, upcoming, today):
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
    next_preview = build_open_next_week(promoted)
    return promoted, next_preview


def main(*, today_local=None):
    plan = load_json(PLAN_FILE)
    upcoming = load_json(UPCOMING_FILE)
    activities_state = load_json(ACTIVITIES_FILE, {"activities": []})
    coach_state = load_json(COACH_FILE, {"analyses": []})

    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    tz = ZoneInfo(timezone_name)
    today = today_local or datetime.now(tz).date()
    if isinstance(today, str):
        today = date.fromisoformat(today)

    result = rollover_documents(plan, upcoming, today)
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
