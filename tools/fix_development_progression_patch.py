#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING = ROOT / "träning"
DATA = TRAINING / "data"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fix_strategy_contracts():
    path = TRAINING / "scripts" / "strategy_contracts.py"
    text = path.read_text(encoding="utf-8")

    # The one-off migration's generic replacement can match current_priorities
    # before capability_portfolio. Remove that misplaced assignment once.
    misplaced = '        capability_modes[key] = item.get("mode")\n'
    first = text.find(misplaced)
    capabilities = text.find('    capabilities = document.get("capability_portfolio")')
    if first >= 0 and capabilities >= 0 and first < capabilities:
        text = text[:first] + text[first + len(misplaced):]

    capability_marker = '''        nonempty_string(item.get("label"), f"{context}.label")
        require(item.get("mode") in VALID_PRIORITY_MODES, f"{context}: ogiltigt mode")
        priority = item.get("priority")
'''
    capability_replacement = '''        nonempty_string(item.get("label"), f"{context}.label")
        require(item.get("mode") in VALID_PRIORITY_MODES, f"{context}: ogiltigt mode")
        capability_modes[key] = item.get("mode")
        priority = item.get("priority")
'''
    capability_section = text[capabilities:] if capabilities >= 0 else ""
    if 'capability_modes[key] = item.get("mode")' not in capability_section:
        marker_pos = text.find(capability_marker, capabilities)
        if marker_pos < 0:
            raise RuntimeError("fixer: capability_portfolio marker saknas")
        text = (
            text[:marker_pos]
            + capability_replacement
            + text[marker_pos + len(capability_marker):]
        )

    monotonic_marker = '''            baseline_value = next(option["value"] for option in dose_options if option["id"] == baseline_option_id)
            floor_value = next(option["value"] for option in dose_options if option["id"] == floor_id)
            require(baseline_value >= floor_value, f"{context}: normal utvecklingsbaseline får inte ligga under demonstrerat kapacitetsgolv")
'''
    monotonic_replacement = '''            baseline_value = next(option["value"] for option in dose_options if option["id"] == baseline_option_id)
            floor_value = next(option["value"] for option in dose_options if option["id"] == floor_id)
            option_values = {option["id"]: option["value"] for option in dose_options}
            previous_value = floor_value
            for sequence_index, step in enumerate(sorted(plan_steps, key=lambda value: value["microcycle"])):
                step_context = f"{context}.development_progression.microcycle_plan[{sequence_index}]"
                step_value = option_values[step["option_id"]]
                relation = step["relation"]
                require(step_value >= floor_value, f"{step_context}: planerad utvecklingsdos får inte ligga under demonstrerat golv")
                if relation == "establish":
                    require(sequence_index == 0, f"{step_context}: establish får bara vara första utvecklingssteget")
                elif step_value > previous_value:
                    require(relation == "progress", f"{step_context}: högre dos måste markeras som progress")
                elif step_value == previous_value:
                    require(relation == "hold", f"{step_context}: samma utvecklingsdos måste markeras som hold och ha explicit skäl")
                else:
                    require(False, f"{step_context}: planerad regression hör inte hemma i normal utvecklingslinje")
                previous_value = step_value
            require(baseline_value >= floor_value, f"{context}: normal utvecklingsbaseline får inte ligga under demonstrerat kapacitetsgolv")
'''
    if monotonic_replacement not in text:
        if monotonic_marker not in text:
            raise RuntimeError("fixer: utvecklingskontraktets golvmarkör saknas")
        text = text.replace(monotonic_marker, monotonic_replacement, 1)

    path.write_text(text, encoding="utf-8")


def fix_strategy_and_plan_semantics():
    strategy_path = DATA / "training_strategy.json"
    strategy = load_json(strategy_path)
    slots = {
        slot["slot"]: slot
        for slot in strategy["current_mesocycle"]["microcycle_template"]
    }

    threshold_reason = (
        "Mesocykelns första prioriterade löpstimulus. Aktuell mikrocykel väljer etablering, hold eller progression "
        "från den definierade utvecklingslinjen; kortsiktig ändring kräver sakligt stöd i faktisk närbelastning eller återhämtning."
    )
    hill_reason = (
        "Mesocykelns andra prioriterade löpkvalitet: kraft, löpekonomi och mekanisk kvalitet. "
        "2 × 6 × 150 m är demonstrerat kapacitetsgolv; aktuell mikrocykel väljer nästa utvecklingssteg. "
        "Regression kräver ett explicit närbelastningsskäl."
    )
    slots["run_threshold"]["reason"] = threshold_reason
    slots["run_hill_quality"]["reason"] = hill_reason
    write_json(strategy_path, strategy)

    for filename in ("plan.json", "upcoming_week.json"):
        path = DATA / filename
        document = load_json(path)
        for day in document.get("days") or []:
            slot_name = day.get("microcycle_slot")
            if slot_name == "run_threshold" and day.get("status") != "completed":
                day["reason"] = threshold_reason
            if slot_name != "run_hill_quality" or day.get("status") == "completed":
                continue

            day["reason"] = hill_reason
            step = day.get("development_step") or {}
            step_option_id = step.get("option_id") or day.get("baseline_option_id")
            option = next(
                (item for item in (day.get("dose_options") or []) if item.get("id") == step_option_id),
                None,
            )
            if option:
                day["decision_note"] = (
                    f"Utvecklingsplan för mikrocykeln: {option['session']}. "
                    "En lägre dos är ett tillfälligt belastningsbeslut och får inte bli ny normalbaseline."
                )

            # Preserve the already-made near-term reduction for today, but make it
            # structurally consistent with the new development baseline.
            if (
                filename == "plan.json"
                and day.get("date") == "2026-09-04"
                and (day.get("auto_coach") or {}).get("action") == "reduce"
            ):
                reduced = next(
                    item
                    for item in day["dose_options"]
                    if item.get("id") == "run-hill-2x6x150"
                )
                baseline = next(
                    item
                    for item in day["dose_options"]
                    if item.get("id") == "run-hill-2x7x150"
                )
                auto = day["auto_coach"]
                day["original_session"] = baseline["session"]
                day["session"] = reduced["session"]
                day["dose_resolution"] = {
                    "state": "resolved",
                    "kind": reduced["kind"],
                    "value": reduced["value"],
                    "source": "migrated_existing_near_term_revision",
                    "option_id": reduced["id"],
                    "basis": auto.get("reason") or "Explicit närbelastningsstyrd regression.",
                    "applied_at_utc": auto.get("applied_at_utc"),
                }
                day["coach_adjustment"] = (
                    "Tillfällig regression från utvecklingsplanens 2 × 7 × 150 m till 2 × 6 × 150 m. "
                    "Skälet är den redan dokumenterade ackumulerade närbelastningen; detta är belastningsstyrning, inte ny utvecklingsbaseline."
                )
        write_json(path, document)


def fix_rollover_test():
    path = TRAINING / "tests" / "test_rollover_week.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '    def test_future_week_has_concrete_baselines_without_automatic_progression(self):\n',
        '    def test_future_week_has_concrete_baselines_with_mesocycle_progression(self):\n',
        1,
    )
    old = '            4: ("run-hill-6x150", "6 × 150 m"),\n'
    new = '            4: ("run-hill-2x7x150", "2 × 7 × 150 m"),\n'
    if old not in text and new not in text:
        raise RuntimeError("fixer: gammal hill-baseline saknas i rollover-test")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def strengthen_progression_tests():
    path = TRAINING / "tests" / "test_development_progression_contract.py"
    text = path.read_text(encoding="utf-8")
    marker = '''    def test_next_microcycle_advances_development_anchors(self):
'''
    extra = '''    def test_same_dose_cannot_be_disguised_as_progress(self):
        broken = deepcopy(self.strategy)
        hill = next(item for item in broken["current_mesocycle"]["microcycle_template"] if item["slot"] == "run_hill_quality")
        hill["development_progression"]["microcycle_plan"][1]["option_id"] = "run-hill-2x7x150"
        hill["development_progression"]["microcycle_plan"][1]["relation"] = "progress"
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(broken)

    def test_existing_today_reduction_preserves_development_baseline(self):
        today = next(day for day in self.plan["days"] if day.get("date") == "2026-09-04")
        self.assertEqual(today["baseline_option_id"], "run-hill-2x7x150")
        self.assertEqual(today["dose_resolution"]["option_id"], "run-hill-2x6x150")
        self.assertIn("2 × 6 × 150 m", today["session"])
        self.assertIn("2 × 7 × 150 m", today["original_session"])

'''
    if "def test_same_dose_cannot_be_disguised_as_progress" not in text:
        if marker not in text:
            raise RuntimeError("fixer: testinfogningspunkt saknas")
        text = text.replace(marker, extra + marker, 1)
    path.write_text(text, encoding="utf-8")


def main():
    fix_strategy_contracts()
    fix_strategy_and_plan_semantics()
    fix_rollover_test()
    strengthen_progression_tests()
    print("Development progression migration fixer applied.")


if __name__ == "__main__":
    main()
