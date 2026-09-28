"""Shared workout-prescription copy for current and historical presentation."""

from __future__ import annotations


def _selected_candidate(payload: dict) -> dict:
    design = payload.get("workout_design") or {}
    selected_id = design.get("selected_candidate_id")
    candidates = design.get("candidates") or []
    selected = next(
        (item for item in candidates if item.get("id") == selected_id),
        None,
    )
    if selected is None and len(candidates) == 1:
        selected = candidates[0]
    return selected or {}


def _display_line(block: dict) -> str:
    name = str(block.get("name") or "").strip()
    intensity = str(block.get("intensity") or "").strip()
    instruction = str(block.get("instruction") or "").strip()

    # "Styrkemall" and "enligt styrkemall" describe the source of the
    # prescription, not useful athlete-facing content. The pass header already
    # says that the strength template applies.
    if name.casefold() == "styrkemall":
        name = ""
    if intensity.casefold() == "enligt styrkemall":
        intensity = ""

    parts = []
    for part in (name, intensity, instruction):
        if part and part not in parts:
            parts.append(part)
    return " · ".join(parts)


def prescription_lines(payload: dict) -> tuple[str, ...]:
    selected = _selected_candidate(payload)
    blocks = (selected.get("prescription") or {}).get("blocks") or []
    lines = []
    for block in blocks:
        line = _display_line(block)
        if line:
            lines.append(line)
    return tuple(lines)
