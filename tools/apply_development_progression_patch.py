#!/usr/bin/env python3
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING = ROOT / "träning"
DATA = TRAINING / "data"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def option(option_id, value, session, intent):
    return {
        "id": option_id,
        "kind": "structured",
        "value": value,
        "session": session,
        "intent": intent,
    }


def slot_by_name(strategy, name):
    return next(
        item
        for item in strategy["current_mesocycle"]["microcycle_template"]
        if item["slot"] == name
    )


def option_by_id(slot, option_id):
    return next(item for item in slot["dose_options"] if item["id"] == option_id)


def selected_step(slot, microcycle_index):
    progression = slot.get("development_progression") or {}
    return next(
        (
            step
            for step in progression.get("microcycle_plan") or []
            if step.get("microcycle") == microcycle_index
        ),
        None,
    )


def patch_strategy():
    path = DATA / "training_strategy.json"
    strategy = load_json(path)

    strategy["decision_policy"].update(
        {
            "development_goal_requires_progression": True,
            "development_hold_or_regression_requires_reason": True,
            "maintenance_repeat_is_separate_mode": True,
        }
    )

    progression_policy = strategy["current_mesocycle"]["progression_policy"]
    progression_policy.update(
        {
            "development_key_sessions_must_progress_or_justify_hold": True,
            "regression_below_demonstrated_floor_requires_reason": True,
            "maintenance_sessions_may_repeat_without_progression": True,
            "max_consecutive_development_repeats_without_reason": 1,
        }
    )

    threshold = slot_by_name(strategy, "run_threshold")
    threshold["development_progression"] = {
        "mode": "develop",
        "demonstrated_floor_option_id": "run-threshold-3x8",
        "same_dose_repeat_requires_reason": True,
        "source": "absorbed_training_history",
        "microcycle_plan": [
            {
                "microcycle": 2,
                "option_id": "run-threshold-3x8",
                "relation": "hold",
                "reason": "Kriterierna kräver mer än en jämförbar 3 × 8-exponering innan arbetstiden ökas.",
            },
            {
                "microcycle": 3,
                "option_id": "run-threshold-3x10",
                "relation": "progress",
                "reason": "Planerad utveckling från etablerade 24 till 30 min kontrollerat tröskelarbete; intensiteten hålls oförändrat kontrollerad.",
            },
            {
                "microcycle": 4,
                "option_id": "run-threshold-3x10",
                "relation": "hold",
                "reason": "Konsolidera den högre arbetstiden och skapa jämförbar data inför mesocykelutvärderingen.",
            },
        ],
    }

    hill = slot_by_name(strategy, "run_hill_quality")
    hill["dose_options"] = [
        option(
            "run-hill-6x150",
            6,
            "Löpning · backkvalitet · 15 min lugnt + 6 × 150 m / full lugn nedjogg + 10 min lugnt",
            "Tydligt reducerad reservdos. Får bara användas som tillfällig regression när faktisk närbelastning eller återhämtning motiverar det; aldrig som normal utvecklingsbaseline.",
        ),
        option(
            "run-hill-2x6x150",
            12,
            "Löpning · backkvalitet · 15 min lugnt + 2 × 6 × 150 m / lugn joggvila + 10 min lugnt",
            "Demonstrerat kapacitetsgolv: 2 × 6 × 150 m har genomförts utan problem. I utvecklingsläge är detta golv, inte nästa utvecklingsmål.",
        ),
        option(
            "run-hill-2x7x150",
            14,
            "Löpning · backkvalitet · 15 min lugnt + 2 × 7 × 150 m / lugn joggvila + 10 min lugnt",
            "Nästa konservativa utvecklingssteg från demonstrerade 2 × 6: endast repetitionsvolymen ökas, inte avsedd intensitet.",
        ),
        option(
            "run-hill-2x8x150",
            16,
            "Löpning · backkvalitet · 15 min lugnt + 2 × 8 × 150 m / lugn joggvila + 10 min lugnt",
            "Följande progressionssteg när 2 × 7 är absorberat med bibehållen mekanik och utan oproportionerlig återhämtningskostnad.",
        ),
    ]
    hill["session"] = option_by_id(hill, "run-hill-2x7x150")["session"]
    hill["baseline_option_id"] = "run-hill-2x7x150"
    hill["reason"] = (
        "Mesocykelns andra prioriterade löpkvalitet: kraft, löpekonomi och mekanisk kvalitet. "
        "Tidigare 2 × 6 × 150 m är demonstrerat utan problem, därför är 2 × 7 nästa utvecklingsbaseline. "
        "Regression kräver ett explicit närbelastningsskäl."
    )
    hill["development_focus"] = (
        "Kraftfull men kontrollerad löpning med bibehållen mekanik. Utveckla arbetsmängden stegvis; "
        "ingen maximal sprint eller syrajakt."
    )
    hill["progression_target_option_id"] = "run-hill-2x8x150"
    hill["progression_criteria"] = [
        "Demonstrerade 2 × 6 × 150 m är kapacitetsgolv och får inte åter bli normal utvecklingsbaseline.",
        "2 × 7 ska kunna genomföras med bibehållen kraft och mekanik utan tydlig syrajakt eller teknikförlust i slutet.",
        "Fredagens mekaniska belastning ska kunna absorberas utan att söndagens lugna distans återkommande måste offras.",
        "Progression från 2 × 7 till 2 × 8 ändrar endast repetitionsvolymen; avsedd intensitet ska inte samtidigt höjas.",
    ]
    hill["development_progression"] = {
        "mode": "develop",
        "demonstrated_floor_option_id": "run-hill-2x6x150",
        "same_dose_repeat_requires_reason": True,
        "source": "user_report_2026-09-04",
        "microcycle_plan": [
            {
                "microcycle": 2,
                "option_id": "run-hill-2x7x150",
                "relation": "progress",
                "reason": "2 × 6 × 150 m är redan genomfört utan problem; nästa normala utvecklingsdos ökar endast repetitionsvolymen.",
            },
            {
                "microcycle": 3,
                "option_id": "run-hill-2x8x150",
                "relation": "progress",
                "reason": "Fortsatt planerad volymprogression när mikrocykel 2 absorberats; kortsiktig regression är fortfarande tillåten med explicit skäl.",
            },
            {
                "microcycle": 4,
                "option_id": "run-hill-2x8x150",
                "relation": "hold",
                "reason": "Konsolidera den högre dosen inför mesocykelutvärdering i stället för att öka två belastningsvariabler samtidigt.",
            },
        ],
    }

    guards = strategy["current_mesocycle"]["guardrails"]
    old = "Backpassets konkreta grundplan får ändras först när faktisk belastning eller återhämtning ger skäl; ingen automatisk progression."
    new = (
        "Utvecklingspass får inte fastna på en historisk baseline. Planerad progression hör till mesocykeln; "
        "samma dos får hållas eller en lägre dos användas endast med explicit skäl. Reaktiv wellness får aldrig ensam öka belastningen."
    )
    if old in guards:
        guards[guards.index(old)] = new
    elif new not in guards:
        guards.append(new)

    write_json(path, strategy)
    return strategy


def apply_slot_to_day(day, slot):
    if day.get("microcycle_slot") != slot["slot"]:
        return False
    if day.get("status") == "completed":
        return False

    day["dose_options"] = deepcopy(slot["dose_options"])
    step = selected_step(slot, day.get("microcycle_index"))
    option_id = step["option_id"] if step else slot["baseline_option_id"]
    chosen = option_by_id(slot, option_id)
    day["baseline_option_id"] = option_id
    day["session"] = chosen["session"]
    day["dose_open"] = False
    day["dose_resolution"] = {
        "state": "baseline",
        "kind": chosen["kind"],
        "value": chosen["value"],
        "option_id": option_id,
    }
    day["reason"] = slot["reason"]
    day["development_focus"] = slot["development_focus"]
    day["development_progression"] = deepcopy(slot["development_progression"])
    if step:
        day["development_step"] = deepcopy(step)
    else:
        day.pop("development_step", None)
    return True


def patch_plan_documents(strategy):
    for filename in ("plan.json", "upcoming_week.json"):
        path = DATA / filename
        document = load_json(path)
        for slot_name in ("run_threshold", "run_hill_quality"):
            slot = slot_by_name(strategy, slot_name)
            for day in document.get("days") or []:
                apply_slot_to_day(day, slot)

        # Current Friday already has a legitimate accumulated-load reason to regress.
        # Keep that reason, but reduce from the new development baseline to the demonstrated floor,
        # never below it via an invented 4–5 rep structure.
        if filename == "plan.json":
            for day in document.get("days") or []:
                if day.get("date") == "2026-09-04" and day.get("microcycle_slot") == "run_hill_quality":
                    if (day.get("auto_coach") or {}).get("action") == "reduce":
                        day["coach_adjustment"] = (
                            "Tillfällig regression från utvecklingsplanens 2 × 7 × 150 m till 2 × 6 × 150 m. "
                            "Skälet är den redan dokumenterade ackumulerade närbelastningen; detta är belastningsstyrning, inte ny utvecklingsbaseline."
                        )
        write_json(path, document)


def patch_coach_state():
    path = DATA / "coach.json"
    coach = load_json(path)
    for analysis in coach.get("analyses") or []:
        action = analysis.get("plan_action") or {}
        if action.get("target_date") == "2026-09-04" and action.get("action") == "reduce":
            action["reason"] = (
                "Ackumulerad närbelastning motiverar en tillfällig regression från utvecklingsplanen, inte en lägre normalbaseline."
            )
            action["recommendation"] = (
                "Kör 2 × 6 × 150 m med lugn joggvila i stället för planerade 2 × 7. "
                "Detta är dagens belastningsstyrda undantag; nästa utvecklingsbaseline sänks inte."
            )
            action["dose_option_id"] = "run-hill-2x6x150"
    write_json(path, coach)


def patch_prompt():
    path = TRAINING / "coach_prompt.md"
    text = path.read_text(encoding="utf-8")
    marker = "\n## Fler-dagars belastningsmodell\n"
    section = """
## Utvecklingsläge: progression är ett kontrakt

Ett pass med utvecklingsroll får inte behandlas som ett återkommande underhållspass.

- `development_progression` anger demonstrerat kapacitetsgolv och den planerade utvecklingslinjen för ett nyckelpass. En planerad högre baseline i en senare mikrocykel är avsiktlig mesocykelprogression och ska inte feltolkas som förbjuden reaktiv "automatisk belastningsökning".
- När `mode` är `develop` ska nyckelpass normalt flytta minst en relevant belastningsvariabel över blocket. Samma dos får upprepas endast när `development_step.relation` är `hold` och en konkret orsak finns, till exempel bekräftelse/konsolidering, återhämtningsvecka, taper eller återgång.
- `demonstrated_floor_option_id` är senast demonstrerade absorberade kapacitetsgolv. En normal utvecklingsbaseline får inte ligga under golvet. Tillfällig regression under eller till golvet kräver ett explicit skäl i faktisk närbelastning/återhämtning och får inte skrivas tillbaka som ny normalbaseline.
- Underhåll och aktivering är legitima roller, men de får inte etiketteras som mesocykelns utvecklande kvalitet bara för att de innehåller fart eller struktur.
- `same_dose_repeat_requires_reason` betyder att upprepning utan utveckling är ett aktivt beslut som ska kunna motiveras. Om ingen sådan motivering finns ska passet fortsätta sin definierade progressionslinje.
- Kortsiktig belastningsstyrning får fortfarande reducera, flytta eller ta bort ett planerat utvecklingspass. Skillnaden är att den långsiktiga utvecklingslinjen bevaras och återtas när den åter är absorberbar.
"""
    if "## Utvecklingsläge: progression är ett kontrakt" not in text:
        if marker not in text:
            raise RuntimeError("coach_prompt.md: infogningspunkt saknas")
        text = text.replace(marker, "\n" + section.rstrip() + "\n" + marker, 1)
    path.write_text(text, encoding="utf-8")


def replace_once(path, old, new, label):
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"{label}: förväntad kodsekvens saknas")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_strategy_contracts():
    path = TRAINING / "scripts" / "strategy_contracts.py"
    replace_once(
        path,
        '    capability_keys = set()\n    for index, item in enumerate(capabilities):',
        '    capability_keys = set()\n    capability_modes = {}\n    for index, item in enumerate(capabilities):',
        "strategy_contracts capability map",
    )
    replace_once(
        path,
        '        require(item.get("mode") in VALID_PRIORITY_MODES, f"{context}: ogiltigt mode")\n        priority = item.get("priority")',
        '        require(item.get("mode") in VALID_PRIORITY_MODES, f"{context}: ogiltigt mode")\n        capability_modes[key] = item.get("mode")\n        priority = item.get("priority")',
        "strategy_contracts capability mode",
    )

    anchor_marker = '''            if progression_target is not None:\n                nonempty_string(progression_target, f"{context}.progression_target_option_id")\n                require(progression_target in option_ids, f"{context}.progression_target_option_id måste referera till ett dose_options-id")\n                require(progression_target != baseline_option_id, f"{context}.progression_target_option_id får inte vara baseline")\n'''
    anchor_new = anchor_marker + '''\n        is_development_anchor = (\n            item.get("priority_role") == "anchor"\n            and any(capability_modes.get(key) == "develop" for key in stimuli)\n        )\n        if is_development_anchor:\n            require(dose_options is not None, f"{context}: utvecklande nyckelpass måste ha dose_options")\n            development = item.get("development_progression")\n            require(isinstance(development, dict), f"{context}.development_progression saknas")\n            require(development.get("mode") == "develop", f"{context}.development_progression.mode måste vara develop")\n            floor_id = development.get("demonstrated_floor_option_id")\n            nonempty_string(floor_id, f"{context}.development_progression.demonstrated_floor_option_id")\n            require(floor_id in option_ids, f"{context}: demonstrerat golv måste referera till ett dose_options-id")\n            require(development.get("same_dose_repeat_requires_reason") is True, f"{context}: upprepad utvecklingsdos måste kräva skäl")\n            plan_steps = development.get("microcycle_plan")\n            require(isinstance(plan_steps, list) and plan_steps, f"{context}.development_progression.microcycle_plan saknas")\n            seen_microcycles = set()\n            for step_index, step in enumerate(plan_steps):\n                step_context = f"{context}.development_progression.microcycle_plan[{step_index}]"\n                require(isinstance(step, dict), f"{step_context}: måste vara objekt")\n                microcycle = step.get("microcycle")\n                require(isinstance(microcycle, int) and microcycle > 0, f"{step_context}.microcycle måste vara positivt heltal")\n                require(microcycle not in seen_microcycles, f"{step_context}: dubblerad microcycle {microcycle}")\n                seen_microcycles.add(microcycle)\n                option_id = step.get("option_id")\n                nonempty_string(option_id, f"{step_context}.option_id")\n                require(option_id in option_ids, f"{step_context}.option_id måste referera till dose_options")\n                require(step.get("relation") in {"progress", "hold", "establish"}, f"{step_context}.relation ogiltig")\n                nonempty_string(step.get("reason"), f"{step_context}.reason")\n            baseline_value = next(option["value"] for option in dose_options if option["id"] == baseline_option_id)\n            floor_value = next(option["value"] for option in dose_options if option["id"] == floor_id)\n            require(baseline_value >= floor_value, f"{context}: normal utvecklingsbaseline får inte ligga under demonstrerat kapacitetsgolv")\n            require(progression_target is not None, f"{context}: utvecklande nyckelpass måste ha progression_target_option_id")\n            target_value = next(option["value"] for option in dose_options if option["id"] == progression_target)\n            require(target_value > baseline_value, f"{context}: progression_target måste vara större än baseline i vald belastningsvariabel")\n'''
    replace_once(path, anchor_marker, anchor_new, "strategy_contracts development anchor")

    progression_fields_old = '''        "normal_variation_does_not_trigger_change",\n    ):'''
    progression_fields_new = '''        "normal_variation_does_not_trigger_change",\n        "development_key_sessions_must_progress_or_justify_hold",\n        "regression_below_demonstrated_floor_requires_reason",\n        "maintenance_sessions_may_repeat_without_progression",\n    ):'''
    replace_once(path, progression_fields_old, progression_fields_new, "strategy_contracts progression fields")

    policy_assert_old = '''    require(progression.get("normal_variation_does_not_trigger_change") is True, "strategi: normal variation får inte utlösa planändring")\n'''
    policy_assert_new = policy_assert_old + '''    require(progression.get("development_key_sessions_must_progress_or_justify_hold") is True, "strategi: utvecklande nyckelpass måste progrediera eller ha explicit hold-skäl")\n    require(progression.get("regression_below_demonstrated_floor_requires_reason") is True, "strategi: regression under demonstrerat golv måste kräva explicit skäl")\n    require(progression.get("maintenance_sessions_may_repeat_without_progression") is True, "strategi: underhåll får upprepas utan utvecklingskrav")\n    repeat_limit = progression.get("max_consecutive_development_repeats_without_reason")\n    require(isinstance(repeat_limit, int) and repeat_limit == 1, "strategi: max omotiverade upprepningar av utvecklingsdos måste vara 1")\n'''
    replace_once(path, policy_assert_old, policy_assert_new, "strategy_contracts progression assertions")

    decision_fields_old = '''        "multi_day_context_required",\n    ):'''
    decision_fields_new = '''        "multi_day_context_required",\n        "development_goal_requires_progression",\n        "development_hold_or_regression_requires_reason",\n        "maintenance_repeat_is_separate_mode",\n    ):'''
    replace_once(path, decision_fields_old, decision_fields_new, "strategy_contracts decision fields")

    decision_assert_old = '''    require(policy.get("multi_day_context_required") is True, "strategi: planändring måste använda fler-dagars kontext")\n'''
    decision_assert_new = decision_assert_old + '''    require(policy.get("development_goal_requires_progression") is True, "strategi: utvecklingsmål måste kräva progression")\n    require(policy.get("development_hold_or_regression_requires_reason") is True, "strategi: hold/regression i utvecklingsläge måste kräva skäl")\n    require(policy.get("maintenance_repeat_is_separate_mode") is True, "strategi: underhåll ska vara en separat roll från utveckling")\n'''
    replace_once(path, decision_assert_old, decision_assert_new, "strategy_contracts decision assertions")


def patch_rollover():
    path = TRAINING / "scripts" / "rollover_week.py"
    old = '''            if slot.get("dose_options"):\n                planned_day["dose_options"] = deepcopy(slot["dose_options"])\n                planned_day["baseline_option_id"] = slot["baseline_option_id"]\n                if not apply_baseline_option(planned_day, slot["baseline_option_id"]):\n                    raise RuntimeError(\n                        f"Veckoplan: baseline_option_id {slot['baseline_option_id']!r} saknas för {slot['slot']!r}"\n                    )\n'''
    new = '''            if slot.get("dose_options"):\n                planned_day["dose_options"] = deepcopy(slot["dose_options"])\n                option_id = slot["baseline_option_id"]\n                development = slot.get("development_progression") or {}\n                planned_step = next(\n                    (\n                        step\n                        for step in (development.get("microcycle_plan") or [])\n                        if step.get("microcycle") == microcycle_index\n                    ),\n                    None,\n                )\n                if development:\n                    planned_day["development_progression"] = deepcopy(development)\n                if planned_step:\n                    option_id = planned_step["option_id"]\n                    planned_day["development_step"] = deepcopy(planned_step)\n                planned_day["baseline_option_id"] = option_id\n                if not apply_baseline_option(planned_day, option_id):\n                    raise RuntimeError(\n                        f"Veckoplan: baseline_option_id {option_id!r} saknas för {slot['slot']!r}"\n                    )\n'''
    replace_once(path, old, new, "rollover development schedule")


def write_tests():
    path = TRAINING / "tests" / "test_development_progression_contract.py"
    path.write_text(
        '''#!/usr/bin/env python3\nimport json\nimport sys\nimport unittest\nfrom copy import deepcopy\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\nSCRIPTS = ROOT / "scripts"\nsys.path.insert(0, str(SCRIPTS))\n\nfrom rollover_week import build_mesocycle_next_week  # noqa: E402\nfrom strategy_contracts import StrategyContractError, validate_training_strategy  # noqa: E402\n\n\nclass DevelopmentProgressionContractTests(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        cls.strategy = json.loads((ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8"))\n        cls.plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))\n\n    def test_current_strategy_contract_is_valid(self):\n        self.assertTrue(validate_training_strategy(self.strategy))\n\n    def test_hill_quality_uses_demonstrated_floor_and_progresses(self):\n        hill = next(item for item in self.strategy["current_mesocycle"]["microcycle_template"] if item["slot"] == "run_hill_quality")\n        self.assertEqual(hill["development_progression"]["demonstrated_floor_option_id"], "run-hill-2x6x150")\n        self.assertEqual(hill["baseline_option_id"], "run-hill-2x7x150")\n        self.assertEqual(hill["progression_target_option_id"], "run-hill-2x8x150")\n\n    def test_stale_hill_baseline_below_demonstrated_floor_is_rejected(self):\n        broken = deepcopy(self.strategy)\n        hill = next(item for item in broken["current_mesocycle"]["microcycle_template"] if item["slot"] == "run_hill_quality")\n        hill["baseline_option_id"] = "run-hill-6x150"\n        hill["session"] = next(option["session"] for option in hill["dose_options"] if option["id"] == "run-hill-6x150")\n        with self.assertRaises(StrategyContractError):\n            validate_training_strategy(broken)\n\n    def test_next_microcycle_advances_development_anchors(self):\n        future = build_mesocycle_next_week(self.plan, self.strategy)\n        threshold = next(day for day in future["days"] if day.get("microcycle_slot") == "run_threshold")\n        hill = next(day for day in future["days"] if day.get("microcycle_slot") == "run_hill_quality")\n        self.assertEqual(threshold["microcycle_index"], 3)\n        self.assertEqual(threshold["baseline_option_id"], "run-threshold-3x10")\n        self.assertEqual(hill["baseline_option_id"], "run-hill-2x8x150")\n        self.assertEqual(hill["development_step"]["relation"], "progress")\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
        encoding="utf-8",
    )


def main():
    strategy = patch_strategy()
    patch_plan_documents(strategy)
    patch_coach_state()
    patch_prompt()
    patch_strategy_contracts()
    patch_rollover()
    write_tests()
    print("Development progression patch applied.")


if __name__ == "__main__":
    main()
