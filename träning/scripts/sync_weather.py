#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
CONFIG_FILE = ROOT / "data" / "weather_config.json"
WEATHER_FILE = ROOT / "data" / "weather.json"

API_BASE = "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1/geotype/point"
PARAMETERS = [
    "air_temperature",
    "wind_speed",
    "probability_of_precipitation",
    "symbol_code",
]


def load_json(path, fallback=None):
    if not path.exists():
        return {} if fallback is None else fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(data):
    WEATHER_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_location(value):
    if not isinstance(value, dict):
        raise ValueError("weather location must be an object")
    name = str(value.get("name") or "").strip()
    lat = float(value["latitude"])
    lon = float(value["longitude"])
    if not name:
        raise ValueError("weather location name is missing")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("weather coordinates are invalid")
    return {
        "name": name,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
    }


def location_key(location):
    return (location["latitude"], location["longitude"])


def smhi_value(data, name):
    value = data.get(name)
    if value is None or value == 9999:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_location(location):
    lon = location["longitude"]
    lat = location["latitude"]
    query = urlencode({"parameters": ",".join(PARAMETERS)})
    url = f"{API_BASE}/lon/{lon:.6f}/lat/{lat:.6f}/data.json?{query}"
    request = Request(url, headers={"User-Agent": "hall.se-training-weather/1.0"})
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"SMHI returned HTTP {response.status}")
        payload = json.load(response)
    if not isinstance(payload.get("timeSeries"), list):
        raise RuntimeError("SMHI response is missing timeSeries")
    return payload


def summarize_by_local_date(payload, tz):
    buckets = {}
    for entry in payload.get("timeSeries", []):
        timestamp = entry.get("time")
        data = entry.get("data") or {}
        if not timestamp or not isinstance(data, dict):
            continue
        try:
            instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(tz)
        except ValueError:
            continue
        date = instant.date().isoformat()
        bucket = buckets.setdefault(
            date,
            {
                "temperatures": [],
                "winds": [],
                "precip_probabilities": [],
                "symbols": [],
            },
        )
        temperature = smhi_value(data, "air_temperature")
        wind = smhi_value(data, "wind_speed")
        precip_probability = smhi_value(data, "probability_of_precipitation")
        symbol = smhi_value(data, "symbol_code")
        if temperature is not None:
            bucket["temperatures"].append(temperature)
        if wind is not None:
            bucket["winds"].append(wind)
        if precip_probability is not None:
            bucket["precip_probabilities"].append(precip_probability)
        if symbol is not None:
            minutes_from_noon = abs((instant.hour * 60 + instant.minute) - 12 * 60)
            bucket["symbols"].append((minutes_from_noon, int(round(symbol))))

    summaries = {}
    for date, bucket in buckets.items():
        summary = {}
        if bucket["temperatures"]:
            summary["temperature_min_c"] = round(min(bucket["temperatures"]), 1)
            summary["temperature_max_c"] = round(max(bucket["temperatures"]), 1)
        if bucket["winds"]:
            summary["wind_max_ms"] = round(max(bucket["winds"]), 1)
        if bucket["precip_probabilities"]:
            summary["precip_probability_max_pct"] = int(round(max(bucket["precip_probabilities"])))
        if bucket["symbols"]:
            summary["symbol_code"] = min(bucket["symbols"], key=lambda item: item[0])[1]
        if summary:
            summaries[date] = summary
    return summaries


def stale_result(error):
    now = datetime.now(timezone.utc).isoformat()
    previous = load_json(WEATHER_FILE, {})
    previous["status"] = "stale" if previous.get("daily") else "unavailable"
    previous["last_attempt_utc"] = now
    previous["last_error"] = str(error)[:240]
    previous.setdefault("source", "SMHI Open Data · SNOW1gv1")
    write_json(previous)
    print(f"Weather sync warning: {error}. Existing forecast kept when available.")


def main():
    plan = load_json(PLAN_FILE)
    config = load_json(CONFIG_FILE)
    tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
    default_location = normalize_location(config["default_location"])
    today = datetime.now(tz).date().isoformat()

    day_locations = {}
    unique_locations = {}
    for day in plan.get("days", []):
        date = day.get("date")
        if not date or date < today:
            continue
        location = normalize_location(day.get("weather_location") or default_location)
        day_locations[date] = location
        unique_locations[location_key(location)] = location

    fetched_at = datetime.now(timezone.utc).isoformat()
    forecasts_by_location = {}
    metadata_by_location = {}
    for key, location in unique_locations.items():
        payload = fetch_location(location)
        forecasts_by_location[key] = summarize_by_local_date(payload, tz)
        metadata_by_location[key] = {
            "created_time": payload.get("createdTime"),
            "reference_time": payload.get("referenceTime"),
            "grid_coordinates": payload.get("geometry", {}).get("coordinates"),
        }

    daily = {}
    for date, location in day_locations.items():
        key = location_key(location)
        summary = forecasts_by_location.get(key, {}).get(date)
        if not summary:
            continue
        daily[date] = {
            "location": location,
            **summary,
        }

    result = {
        "status": "ok",
        "source": "SMHI Open Data · SNOW1gv1",
        "fetched_at_utc": fetched_at,
        "last_attempt_utc": fetched_at,
        "default_location": default_location,
        "daily": daily,
        "locations": [
            {
                "location": location,
                **metadata_by_location.get(key, {}),
            }
            for key, location in unique_locations.items()
        ],
    }
    write_json(result)
    print(f"Weather OK: {len(daily)} planned day(s), {len(unique_locations)} location(s).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        stale_result(exc)
