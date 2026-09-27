"""Weather repository port and compatibility cache adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from training_core.domain.weather import DailyWeatherForecast, WeatherSnapshot


class WeatherRepository(Protocol):
    def current(self) -> WeatherSnapshot: ...


@dataclass(frozen=True)
class FileWeatherRepository:
    path: Path

    def current(self) -> WeatherSnapshot:
        if not self.path.exists():
            return WeatherSnapshot(
                status="unavailable",
                source="",
                fetched_at_utc="",
                daily=(),
            )
        document = json.loads(self.path.read_text(encoding="utf-8"))
        status = str(document.get("status") or "unavailable").strip()
        if status not in {"ok", "stale", "unavailable"}:
            raise RuntimeError(f"invalid weather cache status: {status!r}")

        rows = []
        for date_text, row in sorted((document.get("daily") or {}).items()):
            if not isinstance(row, dict):
                continue
            location = row.get("location") or {}
            rows.append(
                DailyWeatherForecast(
                    local_date=date.fromisoformat(date_text),
                    location_name=str(location.get("name") or "").strip() or "Oxelösund",
                    temperature_min_c=_number(row.get("temperature_min_c")),
                    temperature_max_c=_number(row.get("temperature_max_c")),
                    wind_max_ms=_number(row.get("wind_max_ms")),
                    precip_probability_max_pct=_number(
                        row.get("precip_probability_max_pct")
                    ),
                    symbol_code=_integer(row.get("symbol_code")),
                )
            )
        return WeatherSnapshot(
            status=status,
            source=str(document.get("source") or "").strip(),
            fetched_at_utc=str(document.get("fetched_at_utc") or "").strip(),
            daily=tuple(rows),
        )


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value) -> int | None:
    number = _number(value)
    return int(round(number)) if number is not None else None
