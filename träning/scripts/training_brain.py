#!/usr/bin/env python3
from datetime import date, timedelta
import math

from coach_rules import activity_local_date, matching_activity


STATUS_LABELS = {
    "completed": "GENOMFÖRT",
    "planned": "PLANERAT",
    "preliminary": "PRELIMINÄRT",
    "conditional": "VILLKORAT",
    "open": "ÖPPET",
}
ROLE_LABELS = {
    "anchor": "ANKARE",
    "flex": "FLEX",
    "optional": "OPTIONAL",
}

WET_WEATHER_SYMBOLS = {8, 9, 10, 11, 12, 13, 14, 18, 19, 20, 21, 22, 23, 24}
HIGH_IMPACT_WEATHER_SYMBOLS = {10, 11, 14, 20, 21, 24}
RUN_QUALITY_STIMULI = {"run_threshold", "run_hill_quality", "run_moderate_hard"}
RUN_STIMULI = {
    "run_threshold",
    "run_hill_quality",
    "run_moderate_hard",
    "run_easy_distance",
    "run_aerobic",
    "run_long",
}
INDOOR_SESSION_TOKENS = {
    "inomhus",
    "löpband",
    "treadmill",
    "zwift",
    "trainer",
    "spinning",
}


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_setting(settings, key):
    alternatives = (settings or {}).get("indoor_alternatives") or {}
    value = alternatives.get(key)
    if isinstance(value, dict):
        return value.get("available") is True
    return value is True


def _day_by_date(plan, day_text):
    return next((item for item in plan.get("days") or [] if item.get("date") == day_text), None)


def _nearby_plan_days(plan, today_date, *, before=0, after=0):
    rows = []
    for offset in range(-before, after + 1):
        if offset == 0:
            continue
        day_date = today_date + timedelta(days=offset)
        day = _day_by_date(plan, day_date.isoformat())
        if day:
            rows.append((offset, day))
    return rows


def _weather_is_actionable(forecast):
    symbol = _number((forecast or {}).get("symbol_code"))
    if symbol is None:
        return False
    symbol = int(round(symbol))
    precip_probability = _number((forecast or {}).get("precip_probability_max_pct"))
    if symbol in HIGH_IMPACT_WEATHER_SYMBOLS:
        return True
    return (
        symbol in WET_WEATHER_SYMBOLS
        and precip_probability is not None
        and precip_probability >= 70
    )


def resolve_weather_advice(plan, activities, weather, settings, today):
    """Return a short, conservative execution advisory or None.

    Weather may alter how today's planned stimulus is executed, but must not
    invent extra training or silently change the microcycle.
    """
    today_date = today if isinstance(today, date) else date.fromisoformat(str(today))
    today_text = today_date.isoformat()
    day = _day_by_date(plan, today_text)
    if not day or day_fulfilled(day, activities):
        return None
    if (weather or {}).get("status") != "ok":
        return None

    forecast = ((weather or {}).get("daily") or {}).get(today_text) or {}
    if not _weather_is_actionable(forecast):
        return None

    sport = str(day.get("sport") or "").strip().lower()
    session = str(day.get("session") or "").strip().lower()
    if any(token in session for token in INDOOR_SESSION_TOKENS):
        return None
    stimuli = set(day.get("stimuli") or [])
    nearby = _nearby_plan_days(plan, today_date, before=2, after=2)

    recent_run_quality = any(
        offset < 0
        and RUN_QUALITY_STIMULI.intersection(set(item.get("stimuli") or []))
        and day_fulfilled(item, activities)
        for offset, item in nearby
    )
    future_run = any(
        offset > 0
        and RUN_STIMULI.intersection(set(item.get("stimuli") or []))
        for offset, item in nearby
    )

    trainer_available = _bool_setting(settings, "trainer")
    treadmill_available = _bool_setting(settings, "treadmill")
    swim_available = _bool_setting(settings, "swim")

    if sport == "bike":
        has_aerobic = "mtb_aerobic" in stimuli or any("bike" in item and "aerobic" in item for item in stimuli)
        has_technical = "mtb_technical" in stimuli

        if has_aerobic and trainer_available:
            note = ["Behåller dagens aeroba cykelstimulus."]
            if has_technical:
                note.append("MTB-teknikdelen ersätts inte inomhus.")
            if recent_run_quality:
                note.append("Det undviker extra löpmekanisk belastning efter nylig löpkvalitet.")
            if future_run and treadmill_available:
                note.append("Löpband är därför inte förstahandsval med löpning nära i planen.")
            if swim_available:
                note.append("Simning är ett lättare alternativ.")
            return {
                "title": "Regn påverkar dagens MTB",
                "recommendation": "Trainer på gravel är förstahandsval idag.",
                "note": " ".join(note),
                "kind": "weather_execution",
            }

        if has_technical:
            return {
                "title": "Regn påverkar dagens MTB",
                "recommendation": "Trainer kan bara ersätta den fysiologiska delen; teknikstimulus uteblir.",
                "note": "Behåll utepasset endast om våta förhållanden är ett avsiktligt och rimligt teknikstimulus.",
                "kind": "weather_execution",
            }

        if swim_available:
            return {
                "title": "Regn påverkar dagens cykelpass",
                "recommendation": "Simning är ett möjligt lättare alternativ.",
                "note": "Det ändrar grenspecificiteten, så byt bara om dagens cykelspecifika stimulus inte behöver skyddas.",
                "kind": "weather_execution",
            }

    if sport == "run" and treadmill_available:
        note = "Behåller löpningens mekaniska och fysiologiska stimulus bättre än ett grenbyte."
        if any("trail" in str(item).lower() or "technical" in str(item).lower() for item in stimuli):
            note += " Eventuell stig-/teknikdel ersätts inte."
        return {
            "title": "Regn påverkar dagens löppass",
            "recommendation": "Löpband är förstahandsval om du vill behålla passets syfte.",
            "note": note,
            "kind": "weather_execution",
        }

    return None


def activities_on_date(activities, day_date):
    return [activity for activity in activities or [] if activity_local_date(activity) == day_date]


def day_fulfilled(day, activities):
    return matching_activity(day, activities) is not None


def capability_labels(strategy):
    return {
        item.get("key"): item.get("label")
        for item in strategy.get("capability_portfolio") or []
        if item.get("key") and item.get("label")
    }


def stimulus_labels(day, strategy):
    labels = capability_labels(strategy)
    return [labels.get(key, key) for key in day.get("stimuli") or []]


def resolve_today(plan, activities, strategy, today):
    today_text = today.isoformat() if isinstance(today, date) else str(today)
    day = next((item for item in plan.get("days") or [] if item.get("date") == today_text), None)
    if not day:
        return {
            "date": today_text,
            "status": "UTANFÖR AKTUELL VECKA",
            "headline": "Ingen aktiv dagsplan",
            "why": "Den aktiva veckoplanen innehåller inte dagens datum.",
            "role": "",
            "stimuli": [],
            "fulfilled": False,
        }

    fulfilled = day_fulfilled(day, activities)
    status = "GENOMFÖRT" if fulfilled else STATUS_LABELS.get(day.get("status"), str(day.get("status") or "").upper())
    headline = "Dagens plan är genomförd" if fulfilled else day.get("session") or "Ingen session"
    if fulfilled:
        activity = matching_activity(day, activities)
        label = (
            (activity or {}).get("display_label")
            or (activity or {}).get("sport_type")
            or "Aktivitet"
        )
        why = "Registrerat som dagens plan: " + str(label) + "."
    else:
        why = day.get("reason") or "Ingen motivering registrerad."
        same_day_rule = (strategy.get("decision_policy") or {}).get("same_day_open_dose_must_resolve_or_review") is True
        if same_day_rule and day.get("dose_open") is True:
            status = "DOSBESLUT KRÄVS"
            why = (
                why
                + " Dagens stimulus är känt men dosen är fortfarande öppen; systemet måste lösa dosen "
                  "eller uttryckligen markera att underlaget inte räcker."
            )

    return {
        "date": today_text,
        "status": status,
        "headline": headline,
        "why": why,
        "role": ROLE_LABELS.get(day.get("priority_role"), ""),
        "stimuli": stimulus_labels(day, strategy),
        "fulfilled": fulfilled,
    }


def resolve_next_decision(plan, activities, strategy, today):
    today_date = today if isinstance(today, date) else date.fromisoformat(str(today))
    horizon_days = int((strategy.get("decision_policy") or {}).get("horizon_days") or 3)
    horizon_end = today_date + timedelta(days=horizon_days)
    future = []
    for day in plan.get("days") or []:
        try:
            day_date = date.fromisoformat(day.get("date") or "")
        except ValueError:
            continue
        if not (today_date < day_date <= horizon_end):
            continue
        if day_fulfilled(day, activities):
            continue
        future.append((day_date, day))

    explicit = [(day_date, day) for day_date, day in future if day.get("decision_note")]
    if explicit:
        day_date, day = explicit[0]
        return {
            "date": day_date.isoformat(),
            "label": day.get("label") or day_date.isoformat(),
            "headline": day.get("session") or "Kommande pass",
            "note": day.get("decision_note"),
        }

    unresolved = [
        (day_date, day)
        for day_date, day in future
        if day.get("status") == "conditional" or day.get("dose_open")
    ]
    if unresolved:
        day_date, day = unresolved[0]
        note = day.get("coach_adjustment")
        if not note:
            note = "Dosen låses först när de närmast föregående dagarnas faktiska belastning är känd."
        return {
            "date": day_date.isoformat(),
            "label": day.get("label") or day_date.isoformat(),
            "headline": day.get("session") or "Kommande pass",
            "note": note,
        }

    anchors = [(day_date, day) for day_date, day in future if day.get("priority_role") == "anchor"]
    if anchors:
        day_date, day = anchors[0]
        return {
            "date": day_date.isoformat(),
            "label": day.get("label") or day_date.isoformat(),
            "headline": day.get("session") or "Kommande nyckelpass",
            "note": "Nästa prioriterade stimulus i den aktuella mesocykeln.",
        }

    if future:
        day_date, day = future[0]
        return {
            "date": day_date.isoformat(),
            "label": day.get("label") or day_date.isoformat(),
            "headline": day.get("session") or "Kommande pass",
            "note": "Ingen särskild omplanering krävs med nuvarande underlag.",
        }
    return {
        "date": "",
        "label": "",
        "headline": "Inget beslut inom 72 timmar",
        "note": "Planen behöver inte låsas längre fram innan mer faktisk träning är känd.",
    }


def resolve_mesocycle(strategy, today):
    today_date = today if isinstance(today, date) else date.fromisoformat(str(today))
    mesocycle = strategy.get("current_mesocycle") or {}
    start = date.fromisoformat(mesocycle["start_date"])
    end = date.fromisoformat(mesocycle["end_date"])
    length_days = int((mesocycle.get("microcycle_structure") or {}).get("length_days") or 7)
    total_microcycles = max(1, math.ceil(((end - start).days + 1) / length_days))
    if today_date < start:
        microcycle_index = 0
        state = "startar snart"
    elif today_date > end:
        microcycle_index = total_microcycles
        state = "avslutad · väntar utvärdering"
    else:
        microcycle_index = min(total_microcycles, ((today_date - start).days // length_days) + 1)
        state = f"mikrocykel {microcycle_index} av {total_microcycles}"
    return {
        "id": mesocycle.get("id") or "",
        "title": mesocycle.get("title") or "Aktuell mesocykel",
        "state": state,
        "microcycle_index": microcycle_index,
        "microcycle_total": total_microcycles,
        "goal_contribution": mesocycle.get("goal_contribution") or "",
        "hypothesis": mesocycle.get("hypothesis") or "",
        "evaluation_date": mesocycle.get("evaluation_date") or "",
        "protected_stimuli": [capability_labels(strategy).get(key, key) for key in mesocycle.get("protected_stimuli") or []],
    }


def resolve_priority_line(strategy):
    ordered = sorted(strategy.get("current_priorities") or [], key=lambda item: item.get("priority", 999))
    return [item.get("label") for item in ordered if item.get("label")]


# Compatibility alias for archived callers; new code should use resolve_mesocycle.
resolve_block = resolve_mesocycle
