#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.domain.weather import (  # noqa: E402
    DailyWeatherForecast,
    WeatherSnapshot,
)
from training_core.presentation.today import PlannedDay  # noqa: E402
from training_core.presentation.weather import (  # noqa: E402
    build_weather_read_model,
    day_is_outdoor,
)
from training_core.repositories.weather import FileWeatherRepository  # noqa: E402


class WeatherPresentationTests(unittest.TestCase):
    def test_outdoor_detection_respects_explicit_indoor_session(self):
        self.assertTrue(
            day_is_outdoor(
                PlannedDay(date(2026, 9, 27), "Löpning · lugn distans", "run", "fixed")
            )
        )
        self.assertFalse(
            day_is_outdoor(
                PlannedDay(
                    date(2026, 9, 27),
                    "Löpband · lugn distans",
                    "run",
                    "fixed",
                )
            )
        )
        self.assertFalse(
            day_is_outdoor(
                PlannedDay(date(2026, 9, 27), "Simning · bassäng", "swim", "fixed")
            )
        )
        self.assertTrue(
            day_is_outdoor(
                PlannedDay(date(2026, 9, 27), "Enduro · Krokek", "enduro", "fixed")
            )
        )

    def test_stale_weather_is_explicit_in_read_model(self):
        day = date(2026, 9, 27)
        snapshot = WeatherSnapshot(
            status="stale",
            source="SMHI Open Data",
            fetched_at_utc="2026-09-26T08:00:00+00:00",
            daily=(
                DailyWeatherForecast(
                    local_date=day,
                    location_name="Oxelösund",
                    temperature_min_c=12.0,
                    temperature_max_c=15.4,
                    wind_max_ms=4.9,
                    precip_probability_max_pct=0,
                    symbol_code=1,
                ),
            ),
        )
        model = build_weather_read_model(
            plan=[PlannedDay(day, "Löpning · lugn distans", "run", "fixed")],
            snapshot=snapshot,
        )
        weather = model.for_date(day)
        self.assertIsNotNone(weather)
        self.assertTrue(weather.stale)
        self.assertEqual(
            weather.summary,
            "Väder · Oxelösund · Klart · 12,0–15,4 °C · "
            "nederbördsrisk max 0 % · vind max 4,9 m/s · äldre väderdata",
        )

    def test_file_adapter_isolatedly_normalizes_synced_cache(self):
        payload = {
            "status": "ok",
            "source": "SMHI Open Data · SNOW1gv1",
            "fetched_at_utc": "2026-09-27T09:17:19+00:00",
            "daily": {
                "2026-09-27": {
                    "location": {"name": "Oxelösund"},
                    "temperature_min_c": 12,
                    "temperature_max_c": 15.4,
                    "wind_max_ms": 4.9,
                    "precip_probability_max_pct": 0,
                    "symbol_code": 1,
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weather.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = FileWeatherRepository(path).current()

        self.assertEqual(snapshot.status, "ok")
        self.assertEqual(snapshot.source, "SMHI Open Data · SNOW1gv1")
        self.assertEqual(len(snapshot.daily), 1)
        self.assertEqual(snapshot.daily[0].location_name, "Oxelösund")
        self.assertEqual(snapshot.daily[0].symbol_code, 1)


if __name__ == "__main__":
    unittest.main()
