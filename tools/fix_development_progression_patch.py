#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING = ROOT / "träning"


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

    path.write_text(text, encoding="utf-8")


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


def main():
    fix_strategy_contracts()
    fix_rollover_test()
    print("Development progression migration fixer applied.")


if __name__ == "__main__":
    main()
