#!/usr/bin/env python3
import argparse
import base64
import json
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_URL = "https://intervals.icu/api/v1/athlete/0/wellness"
TIMEZONE = ZoneInfo("Europe/Stockholm")
DEFAULT_OUTPUT = Path("/tmp/training_wellness_context.json")
WELLNESS_FIELDS = (
    "restingHR",
    "hrv",
    "sleepSecs",
    "sleepScore",
    "sleepQuality",
    "steps",
)


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fetch_wellness(oldest, newest, *, opener=urlopen):
    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("INTERVALS_API_KEY saknas")

    auth = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")
    query = urlencode({"oldest": oldest, "newest": newest})
    request = Request(
        f"{API_URL}?{query}",
        method="GET",
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "User-Agent": "hall-training-wellness-context/1.0",
        },
    )
    try:
        with opener(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except HTTPError as exc:
        raise RuntimeError(f"Intervals.icu wellness HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Intervals.icu wellness kunde inte nås: {exc.reason}") from exc

    if status < 200 or status >= 300:
        raise RuntimeError(f"Intervals.icu wellness oväntad HTTP-status: {status}")
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Intervals.icu wellness returnerade inte giltig JSON") from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("Intervals.icu wellness-svar har oväntad struktur")
    return rows


def build_context(rows, *, oldest, newest):
    daily = []
    coverage = {field: 0 for field in WELLNESS_FIELDS}
    for source in rows:
        date_text = source.get("id")
        if not isinstance(date_text, str):
            continue
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError:
            continue

        row = {"date": date_text}
        for field in WELLNESS_FIELDS:
            value = source.get(field)
            if _numeric(value):
                row[field] = value
                coverage[field] += 1
        if len(row) > 1:
            daily.append(row)

    daily.sort(key=lambda item: item["date"])
    return {
        "schema_version": 1,
        "source": "Garmin via Intervals.icu",
        "privacy": "ephemeral_private",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "window": {"oldest": oldest, "newest": newest},
        "latest_date": daily[-1]["date"] if daily else None,
        "coverage": coverage,
        "daily": daily,
    }


def validate_context(context):
    if not isinstance(context, dict) or context.get("schema_version") != 1:
        raise RuntimeError("Wellness-kontext: ogiltigt schema")
    if context.get("privacy") != "ephemeral_private":
        raise RuntimeError("Wellness-kontext: privacy-kontrakt saknas")
    daily = context.get("daily")
    if not isinstance(daily, list):
        raise RuntimeError("Wellness-kontext: daily måste vara lista")
    allowed = {"date", *WELLNESS_FIELDS}
    for row in daily:
        if not isinstance(row, dict) or not set(row).issubset(allowed):
            raise RuntimeError("Wellness-kontext: otillåtet fält i daily")
        if not isinstance(row.get("date"), str):
            raise RuntimeError("Wellness-kontext: datum saknas")
        for field, value in row.items():
            if field != "date" and not _numeric(value):
                raise RuntimeError("Wellness-kontext: wellnessvärde måste vara numeriskt")
    return context


def signature_payload(context):
    """Stable private payload for coach invalidation; excludes generation timestamp."""
    if not context:
        return {}
    validate_context(context)
    return {
        "schema_version": context["schema_version"],
        "source": context.get("source"),
        "window": context.get("window") or {},
        "daily": context.get("daily") or [],
    }


def write_private_context(path, context):
    validate_context(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def main():
    parser = argparse.ArgumentParser(description="Hämta privat Garmin/Intervals-wellness till tillfällig coachkontext")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--output", default=os.environ.get("WELLNESS_CONTEXT_FILE", str(DEFAULT_OUTPUT)))
    args = parser.parse_args()
    if args.days < 7 or args.days > 90:
        raise RuntimeError("--days måste vara 7..90")

    today = datetime.now(TIMEZONE).date()
    oldest = (today - timedelta(days=args.days - 1)).isoformat()
    newest = today.isoformat()
    rows = fetch_wellness(oldest, newest)
    context = build_context(rows, oldest=oldest, newest=newest)
    write_private_context(Path(args.output), context)

    coverage = context["coverage"]
    available = ",".join(field for field, count in coverage.items() if count) or "none"
    print(
        f"Wellness context OK: records={len(context['daily'])} fields={available}. "
        "Värden skrevs endast till privat temporärfil och loggas inte."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Wellness context ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
