"""Typed current-week planning context for v2 presentation."""

from __future__ import annotations

from dataclasses import dataclass

from training_core.domain.planning import WeekPlanningContext
from training_core.presentation.public_copy import assert_public_copy


CAPABILITY_LABELS = {
    "swim_aerobic": "sim aerob",
    "swim_technique": "simteknik",
    "swim_threshold": "kontrollerad simtröskel",
    "run_threshold": "kontrollerad löptröskel",
    "run_easy_distance": "lugn löpdistans",
    "run_hill_quality": "backstyrka/löpekonomi",
    "mtb_aerobic": "MTB aerob",
    "mtb_technical": "MTB teknik",
    "strength_unilateral": "unilateral styrka",
    "strength_core": "core",
    "plyometric": "plyometri",
    "enduro_technical": "enduroteknik",
}


@dataclass(frozen=True)
class WeekContextReadModel:
    focus: str
    block_label: str
    microcycle_index: int | None
    microcycle_total: int | None
    principle: str
    hypothesis: str
    primary: tuple[str, ...]
    secondary: tuple[str, ...]
    maintenance: tuple[str, ...]
    protected: tuple[str, ...]

    @property
    def meta_line(self) -> str:
        parts = [self.block_label]
        if self.microcycle_index and self.microcycle_total:
            parts.append(
                f"mikrocykel {self.microcycle_index} av {self.microcycle_total}"
            )
        return " · ".join(parts)


def _labels(values) -> tuple[str, ...]:
    seen = set()
    result = []
    for value in values or ():
        raw = str(value or "").strip()
        if not raw:
            continue
        label = CAPABILITY_LABELS.get(raw, raw.replace("_", " "))
        if label not in seen:
            seen.add(label)
            result.append(label)
    return tuple(result)


def _focus(primary: tuple[str, ...]) -> str:
    remaining = list(primary)
    parts: list[str] = []
    if "sim aerob" in remaining and "simteknik" in remaining:
        parts.append("Sim aerob/teknik")
        remaining.remove("sim aerob")
        remaining.remove("simteknik")
    if "MTB aerob" in remaining and "MTB teknik" in remaining:
        parts.append("MTB aerob/teknik")
        remaining.remove("MTB aerob")
        remaining.remove("MTB teknik")
    if "unilateral styrka" in remaining and "core" in remaining:
        parts.append("styrka/core")
        remaining.remove("unilateral styrka")
        remaining.remove("core")
    parts.extend(remaining)
    return " + ".join(parts)


def build_week_context_read_model(
    context: WeekPlanningContext | None,
) -> WeekContextReadModel | None:
    if context is None:
        return None

    meso = context.mesocycle
    micro = context.microcycle
    meso_payload = meso.payload or {}
    plan_meta = (micro.payload or {}).get("plan_meta") or {}
    contract = plan_meta.get("mesocycle_contract") or {}

    primary = _labels(
        meso_payload.get("primary_capabilities")
        or contract.get("primary")
        or ()
    )
    secondary = _labels(
        meso_payload.get("secondary_capabilities")
        or contract.get("secondary")
        or ()
    )
    maintenance = _labels(contract.get("maintenance") or ())
    protected = _labels(contract.get("protected_capacity") or ())

    focus = _focus(primary)
    if not focus:
        title = str(meso.title or "").strip()
        focus = title or "Veckans utvecklingsfokus"

    principle = str(
        plan_meta.get("principle")
        or meso.goal_contribution
        or ""
    ).strip()
    hypothesis = str(meso.hypothesis or "").strip()
    if principle:
        assert_public_copy(principle)
    if hypothesis:
        assert_public_copy(hypothesis)

    block_label = (
        "Byggblock"
        if "byggblock" in str(meso.title or "").lower()
        else "Mesocykel"
    )
    return WeekContextReadModel(
        focus=focus,
        block_label=block_label,
        microcycle_index=micro.microcycle_index,
        microcycle_total=meso.duration_weeks,
        principle=principle,
        hypothesis=hypothesis,
        primary=primary,
        secondary=secondary,
        maintenance=maintenance,
        protected=protected,
    )
