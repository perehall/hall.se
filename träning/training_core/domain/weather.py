"""Immutable external weather observations used by presentation/planning adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DailyWeatherForecast:
    local_date: date
    location_name: str
    temperature_min_c: float | None
    temperature_max_c: float | None
    wind_max_ms: float | None
    precip_probability_max_pct: float | None
    symbol_code: int | None


@dataclass(frozen=True)
class WeatherSnapshot:
    status: str
    source: str
    fetched_at_utc: str
    daily: tuple[DailyWeatherForecast, ...]
