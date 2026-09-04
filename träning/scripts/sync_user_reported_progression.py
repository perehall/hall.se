#!/usr/bin/env python3
import json
import re
from pathlib import Path

from rollover_week import build_mesocycle_next_week
from strategy_contracts import validate_training_strategy

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
OVERRIDES_FILE = ROOT / "data" / "activity_overrides.json"

HILL_REPORT_RE = re.compile(
    r"(?P<sets>\d+)\s*[×xX]\s*(?P<reps>\d+)\s*(?:backintervaller|backar|intervaller)\b",
    re.IGNORECASE,
)
DISTANCE_RE = re.compile(r"(?:×|x)\s*(?P<distance>\d+)\s*m\b", re.IGNORECASE)


def load(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_hill_structure(report):
    match = HILL_REPORT_RE.search(str(report or ""))
    if not match:
        return None
    sets = int(match.group("sets"))
    reps = int(match.group("reps"))
    if sets <= 0 or reps <= 0:
        return None
    return {"sets": sets, "reps": reps, "total": sets * reps}


def latest_explicit_hill_report(activities, overrides):
    activity_by_id = {
        str(item.get("id")): item
        for item in activities.get("activities") or []
        if item.get("id") is not None
    }
    candidates = []

    for activity_id, override in (overrides.get("overrides") or {}).items():
        structure = parse_hill_structure(override.get("user_report"))
        if not structure:
            continue
        activity = activity_by_id.get(str(activity_id), {})
        when = activity.get("start_date_local") or activity.get("start_date") or ""
        candidates.append((when, int(activity_id) if str(activity_id).isdigit() else 0, structure))

    for activity in activities.get("activities") or []:
        structure = parse_hill_structure(activity.get("user_report"))
        if not structure:
            continue
        when = activity.get("start_date_local") or activity.get("start_date") or ""
        activity_id = activity.get("id")
        candidates.append((when, int(activity_id) if str(activity_id).isdigit() else 0, structure))

    if not candidates:
        return None
    _, _, structure = max(candidates, key=lambda item: (item[0], item[1]))
    return structure


def hill_template(strategy):
    mesocycle = strategy.get("current_mesocycle") or {}
    return next(
        (item for item in mesocycle.get("microcycle_template") or [] if item.get("slot") == "run_hill_quality"),
        None,
    )


def option_by_id(hill, option_id):
    return next((item for item in hill.get("dose_options") or [] if item.get("id") == option_id), None)


def option_value(hill, option_id):
    option = option_by_id(hill, option_id)
    return option.get("value") if option else None


def planned_rep_distance_m(hill):
    for option in reversed(hill.get("dose_options") or []):
        match = DISTANCE_RE.search(str(option.get("session") or ""))
        if match:
            return int(match.group("distance"))
    return None


def make_hill_option(sets, reps, distance_m, *, role):
    option_id = f"run-hill-{sets}x{reps}x{distance_m}"
    total = sets * reps
    if role == "floor":
        intent = (
            f"Volymgolv från uttrycklig användarrapport: {sets} × {reps} = {total} genomförda "
            f"backintervaller. {distance_m} m är repetitionslängden i den framtida ordinationen; "
            "användarrapporten används inte för att påstå exakt längd på varje tidigare intervall."
        )
    else:
        intent = (
            f"Planerat utvecklingssteg från {sets} × {reps - 1}: endast repetitionsvolymen ökas. "
            f"Avsedd intensitet och planerad repetitionslängd {distance_m} m hålls oförändrade."
        )
    return {
        "id": option_id,
        "kind": "structured",
        "value": total,
        "session": (
            f"Löpning · backkvalitet · 15 min lugnt + {sets} × {reps} × {distance_m} m "
            "/ lugn joggvila + 10 min lugnt"
        ),
        "intent": intent,
    }


def upsert_option(hill, option):
    options = hill.setdefault("dose_options", [])
    for index, existing in enumerate(options):
        if existing.get("id") == option["id"]:
            options[index] = option
            return
    options.append(option)
    options.sort(key=lambda item: (item.get("value", 0), item.get("id", "")))


def promote_hill_progression(strategy, plan, structure):
    hill = hill_template(strategy)
    if not hill:
        return False

    development = hill.get("development_progression") or {}
    current_floor_id = development.get("demonstrated_floor_option_id")
    current_floor_value = option_value(hill, current_floor_id) or 0
    if structure["total"] <= current_floor_value:
        return False

    distance_m = planned_rep_distance_m(hill)
    if not distance_m:
        raise RuntimeError("Backprogression: kunde inte fastställa planerad repetitionslängd från befintlig strategi.")

    sets = structure["sets"]
    floor_reps = structure["reps"]
    floor = make_hill_option(sets, floor_reps, distance_m, role="floor")
    baseline = make_hill_option(sets, floor_reps + 1, distance_m, role="progress")
    target = make_hill_option(sets, floor_reps + 2, distance_m, role="progress")
    for option in (floor, baseline, target):
        upsert_option(hill, option)

    hill["session"] = baseline["session"]
    hill["baseline_option_id"] = baseline["id"]
    hill["progression_target_option_id"] = target["id"]
    hill["reason"] = (
        f"Mesocykelns andra prioriterade löpkvalitet. Användaren har uttryckligen rapporterat "
        f"{sets} × {floor_reps} = {structure['total']} genomförda backintervaller; det är nu "
        "demonstrerat repetitionsvolymgolv. Nästa normaldos ska därför ligga över 18 arbetsrepetitioner "
        "eller ha ett explicit hold-/regressionsskäl."
    ).replace("över 18", f"över {structure['total']}")
    hill["progression_criteria"] = [
        f"{sets} × {floor_reps} = {structure['total']} genomförda backintervaller är demonstrerat repetitionsvolymgolv och får inte åter bli en lägre normal utvecklingsbaseline.",
        f"{sets} × {floor_reps + 1} ska kunna genomföras med bibehållen kraft och mekanik utan tydlig syrajakt eller teknikförlust i slutet.",
        "Fredagens mekaniska belastning ska kunna absorberas utan att söndagens lugna distans återkommande måste offras.",
        f"Progression från {sets} × {floor_reps + 1} till {sets} × {floor_reps + 2} ändrar endast repetitionsvolymen; avsedd intensitet ska inte samtidigt höjas.",
    ]

    current_microcycle = int((plan.get("meta") or {}).get("microcycle_index") or 1)
    total_microcycles = int((plan.get("meta") or {}).get("microcycle_total") or current_microcycle)
    steps = [
        {
            "microcycle": current_microcycle,
            "option_id": floor["id"],
            "relation": "hold",
            "reason": (
                f"Uttrycklig användarrapport etablerar {structure['total']} genomförda backintervaller i "
                f"{sets} × {floor_reps}. Steget förankrar det nya volymgolvet; exakt tidigare repetitionslängd antas inte."
            ),
        }
    ]
    if current_microcycle + 1 <= total_microcycles:
        steps.append(
            {
                "microcycle": current_microcycle + 1,
                "option_id": baseline["id"],
                "relation": "progress",
                "reason": (
                    f"Nästa normala utvecklingssteg ökar endast arbetsrepetitionerna från "
                    f"{structure['total']} till {baseline['value']}."
                ),
            }
        )
    if current_microcycle + 2 <= total_microcycles:
        steps.append(
            {
                "microcycle": current_microcycle + 2,
                "option_id": target["id"],
                "relation": "progress",
                "reason": (
                    f"Fortsatt volymprogression från {baseline['value']} till {target['value']} arbetsrepetitioner "
                    "om föregående steg absorberats; annars krävs explicit hold-skäl."
                ),
            }
        )

    development["demonstrated_floor_option_id"] = floor["id"]
    development["same_dose_repeat_requires_reason"] = True
    development["source"] = "explicit_user_report"
    development["microcycle_plan"] = steps
    hill["development_progression"] = development
    return True


def sync_state(strategy, plan, activities, overrides):
    structure = latest_explicit_hill_report(activities, overrides)
    if not structure:
        return False, None
    changed = promote_hill_progression(strategy, plan, structure)
    return changed, structure


def main():
    strategy = load(STRATEGY_FILE, {})
    plan = load(PLAN_FILE, {})
    activities = load(ACTIVITIES_FILE, {"activities": []})
    overrides = load(OVERRIDES_FILE, {"overrides": {}})

    changed, structure = sync_state(strategy, plan, activities, overrides)
    if not changed:
        if structure:
            print(f"Progressionssynk OK: rapporterat golv {structure['total']} kräver ingen uppdatering.")
        else:
            print("Progressionssynk OK: ingen explicit backstruktur att applicera.")
        return 0

    validate_training_strategy(strategy)
    upcoming = build_mesocycle_next_week(plan, strategy)
    dump(STRATEGY_FILE, strategy)
    dump(UPCOMING_FILE, upcoming)
    print(
        f"Progressionssynk OK: demonstrerat backgolv uppdaterat till {structure['sets']} × "
        f"{structure['reps']} ({structure['total']} intervaller); kommande mikrocykel byggd om."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
