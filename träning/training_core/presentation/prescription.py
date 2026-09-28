"""Shared workout-prescription copy for current and historical presentation."""

from __future__ import annotations

from dataclasses import dataclass


EQUIPMENT_LABELS = {
    "paddles": "paddlar",
    "pull_buoy": "dolme",
    "fins": "fenor",
    "snorkel": "snorkel",
    "kickboard": "platta",
}


@dataclass(frozen=True)
class PrescriptionRow:
    dose: str
    instruction: str


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



def _duration(seconds) -> str:
    seconds = int(seconds or 0)
    if seconds <= 0:
        return ""
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds} s"


def _work_dose(work: dict) -> str:
    work = work or {}
    sets = work.get("sets")
    per_set = work.get("repetitions_per_set")
    reps = work.get("repetitions")
    distance = work.get("distance_m")
    duration = work.get("duration_s")

    if sets and per_set and distance:
        return f"{int(sets)}×{int(per_set)}×{int(distance)} m"
    if reps and distance:
        return f"{int(distance)} m" if int(reps) == 1 else f"{int(reps)}×{int(distance)} m"
    if reps and duration:
        return f"{int(reps)}×{_duration(duration)}"
    if distance:
        return f"{int(distance)} m"
    if duration:
        return _duration(duration)
    return ""


def _equipment_lingo(value) -> str:
    values = value or []
    labels = [
        EQUIPMENT_LABELS.get(str(item).strip().lower(), str(item).strip())
        for item in values
        if str(item).strip()
    ]
    return " + ".join(labels) if labels else "utan redskap"


def _recovery_text(recovery: dict, *, swim: bool) -> str:
    recovery = recovery or {}
    parts = []
    duration = _duration(recovery.get("duration_s"))
    instruction = str(recovery.get("instruction") or "").strip()
    if duration:
        parts.append(f"v {duration}" if swim else f"vila {duration}")
    if instruction:
        parts.append(instruction)
    return " · ".join(parts)


def prescription_rows(payload: dict) -> tuple[PrescriptionRow, ...]:
    """Structured athlete-facing prescription rows shared by all week surfaces."""
    selected = _selected_candidate(payload)
    prescription = selected.get("prescription") or {}
    if prescription.get("completeness") == "external":
        return ()

    rows = []
    for block in prescription.get("blocks") or []:
        dose = _work_dose(block.get("work") or {})
        is_swim = "equipment" in block or block.get("component") == "swim"
        instruction = str(block.get("instruction") or block.get("name") or "").strip()
        if not dose and not is_swim:
            instruction = _display_line(block)

        if "equipment" in block:
            equipment = _equipment_lingo(block.get("equipment"))
            instruction = f"{instruction} · {equipment}" if instruction else equipment

        recovery = _recovery_text(block.get("recovery") or {}, swim=is_swim)
        if recovery:
            instruction = f"{instruction} · {recovery}" if instruction else recovery

        if dose or instruction:
            rows.append(PrescriptionRow(dose=dose or "—", instruction=instruction))
    return tuple(rows)
