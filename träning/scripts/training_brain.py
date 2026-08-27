#!/usr/bin/env python3
from datetime import date, timedelta
import math

from coach_rules import activity_family, activity_local_date, planned_families


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


def activities_on_date(activities, day_date):
    return [activity for activity in activities or [] if activity_local_date(activity) == day_date]


def day_fulfilled(day, activities):
    families = planned_families(day)
    if not families:
        return False
    return any(activity_family(activity) in families for activity in activities_on_date(activities, day.get("date")))


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
        labels = [
            activity.get("display_label") or activity.get("sport_type") or "Aktivitet"
            for activity in activities_on_date(activities, today_text)
        ]
        unique_labels = list(dict.fromkeys(labels))
        why = "Registrerat idag: " + " + ".join(unique_labels) + "."
    else:
        why = day.get("reason") or "Ingen motivering registrerad."

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
