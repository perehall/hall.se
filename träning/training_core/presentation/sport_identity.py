"""Structured sport identity for v2 presentation."""

from __future__ import annotations


SPORT_ICON_KEYS = {
    "run": "run",
    "swim": "swim",
    "bike": "bike",
    "enduro": "enduro",
    "strength": "strength",
    "swimrun": "run",
    "running": "run",
    "trailrun": "run",
    "virtualrun": "run",
    "swimming": "swim",
    "ride": "bike",
    "virtualride": "bike",
    "mountainbikeride": "bike",
    "emountainbikeride": "bike",
    "weighttraining": "strength",
    "strengthtraining": "strength",
}

STIMULUS_ICON_KEYS = {
    "run_": "run",
    "swim_": "swim",
    "mtb_": "bike",
    "bike_": "bike",
    "enduro_": "enduro",
    "strength_": "strength",
    "plyometric": "strength",
}


def sport_icon_key(sport: str) -> str | None:
    return SPORT_ICON_KEYS.get(str(sport or "").strip().lower())


def activity_icon_key(sport_family: str) -> str:
    return sport_icon_key(sport_family) or "activity"


def planned_icon_keys(*, sport: str, payload: dict | None = None) -> tuple[str, ...]:
    raw_sport = str(sport or "").strip().lower()
    if raw_sport in {"rest", "open", ""}:
        return ()

    result: list[str] = []

    def add(key: str | None) -> None:
        if key and key not in result:
            result.append(key)

    if raw_sport == "swimrun":
        add("swim")
        add("run")
    else:
        add(sport_icon_key(raw_sport))

    raw = payload or {}
    stimuli = raw.get("stimuli") or []
    if not isinstance(stimuli, list):
        stimuli = []
    for stimulus in stimuli:
        value = str(stimulus or "").strip().lower()
        for prefix, key in STIMULUS_ICON_KEYS.items():
            if value == prefix or value.startswith(prefix):
                add(key)
                break

    return tuple(result or ("activity",))
