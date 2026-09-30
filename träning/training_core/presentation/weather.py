"""Typed weather read model for training presentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from training_core.domain.weather import WeatherSnapshot
from training_core.presentation.today import PlannedDay


OUTDOOR_PLAN_SPORTS = {"run", "bike", "enduro", "swimrun"}
OUTDOOR_SESSION_TOKENS = (
    "enduro",
    "swimrun",
    "öppet vatten",
    "open water",
    "havssim",
    "sjösim",
)
INDOOR_SESSION_TOKENS = (
    "inomhus",
    "löpband",
    "treadmill",
    "zwift",
    "trainer",
    "spinning",
)

WEATHER_SYMBOLS = {
    1: "Klart",
    2: "Mest klart",
    3: "Växlande molnighet",
    4: "Halvklart",
    5: "Molnigt",
    6: "Mulet",
    7: "Dimma",
    8: "Lätta regnskurar",
    9: "Regnskurar",
    10: "Kraftiga regnskurar",
    11: "Åska",
    12: "Lätta snöblandade skurar",
    13: "Snöblandade skurar",
    14: "Kraftiga snöblandade skurar",
    15: "Lätta snöbyar",
    16: "Snöbyar",
    17: "Kraftiga snöbyar",
    18: "Lätt regn",
    19: "Regn",
    20: "Kraftigt regn",
    21: "Åska",
    22: "Lätt snöblandat regn",
    23: "Snöblandat regn",
    24: "Kraftigt snöblandat regn",
    25: "Lätt snöfall",
    26: "Snöfall",
    27: "Kraftigt snöfall",
}


@dataclass(frozen=True)
class DayWeatherReadModel:
    local_date: date
    location: str
    symbol_code: int | None
    condition: str
    temperature: str
    precipitation: str
    wind: str
    stale: bool
    summary: str


@dataclass(frozen=True)
class WeatherReadModel:
    status: str
    source: str
    source_url: str
    days: tuple[DayWeatherReadModel, ...]

    def for_date(self, local_date: date) -> DayWeatherReadModel | None:
        return next(
            (item for item in self.days if item.local_date == local_date),
            None,
        )


def day_is_outdoor(day: PlannedDay) -> bool:
    sport = str(day.sport or "").strip().lower()
    session = str(day.session or "").strip().lower()
    if any(token in session for token in INDOOR_SESSION_TOKENS):
        return False
    if sport in OUTDOOR_PLAN_SPORTS:
        return True
    if any(
        str(component.sport or "").strip().lower() in OUTDOOR_PLAN_SPORTS
        for component in day.components
    ):
        return True
    return any(token in session for token in OUTDOOR_SESSION_TOKENS)


def _decimal(value: float) -> str:
    return f"{float(value):.1f}".replace(".", ",")


def _day_model(forecast, *, stale: bool) -> DayWeatherReadModel:
    condition = (
        WEATHER_SYMBOLS.get(
            forecast.symbol_code,
            f"Vädersymbol {forecast.symbol_code}",
        )
        if forecast.symbol_code is not None
        else ""
    )
    temperature = ""
    if (
        forecast.temperature_min_c is not None
        and forecast.temperature_max_c is not None
    ):
        if round(forecast.temperature_min_c, 1) == round(
            forecast.temperature_max_c, 1
        ):
            temperature = f"{_decimal(forecast.temperature_min_c)} °C"
        else:
            temperature = (
                f"{_decimal(forecast.temperature_min_c)}–"
                f"{_decimal(forecast.temperature_max_c)} °C"
            )
    precipitation = (
        f"nederbördsrisk max {int(round(forecast.precip_probability_max_pct))} %"
        if forecast.precip_probability_max_pct is not None
        else ""
    )
    wind = (
        f"vind max {_decimal(forecast.wind_max_ms)} m/s"
        if forecast.wind_max_ms is not None
        else ""
    )
    details = [
        item
        for item in (
            condition,
            temperature,
            precipitation,
            wind,
            "äldre väderdata" if stale else "",
        )
        if item
    ]
    summary = (
        f"Väder · {forecast.location_name} · " + " · ".join(details)
        if details else ""
    )
    return DayWeatherReadModel(
        local_date=forecast.local_date,
        location=forecast.location_name,
        symbol_code=forecast.symbol_code,
        condition=condition,
        temperature=temperature,
        precipitation=precipitation,
        wind=wind,
        stale=stale,
        summary=summary,
    )


def build_daily_weather_models(
    snapshot: WeatherSnapshot | None,
) -> tuple[DayWeatherReadModel, ...]:
    """Normalize every available forecast day without applying plan filtering."""
    if snapshot is None:
        return ()
    stale = snapshot.status != "ok"
    return tuple(
        _day_model(forecast, stale=stale)
        for forecast in sorted(snapshot.daily, key=lambda item: item.local_date)
    )


def build_weather_read_model(
    *,
    plan: Iterable[PlannedDay],
    snapshot: WeatherSnapshot | None,
) -> WeatherReadModel:
    if snapshot is None:
        return WeatherReadModel(
            status="unavailable",
            source="",
            source_url="https://www.smhi.se/",
            days=(),
        )

    plan_by_date = {}
    for day in plan:
        plan_by_date.setdefault(day.local_date, []).append(day)
    forecasts = []
    for forecast in build_daily_weather_models(snapshot):
        workouts = plan_by_date.get(forecast.local_date) or []
        if not any(day_is_outdoor(day) for day in workouts):
            continue
        forecasts.append(forecast)
    return WeatherReadModel(
        status=snapshot.status,
        source=snapshot.source,
        source_url="https://www.smhi.se/",
        days=tuple(sorted(forecasts, key=lambda item: item.local_date)),
    )
