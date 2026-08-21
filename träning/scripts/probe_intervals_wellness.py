#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_URL = "https://intervals.icu/api/v1/athlete/0/wellness"
TIMEZONE = ZoneInfo("Europe/Stockholm")

# Values for these fields are potentially sensitive. The POC deliberately reports
# only non-null coverage counts, never the values themselves.
CANDIDATE_FIELDS = [
    "restingHR",
    "hrv",
    "hrvSDNN",
    "sleepSecs",
    "sleepScore",
    "sleepQuality",
    "avgSleepingHR",
    "spO2",
    "readiness",
    "baevskySI",
    "stress",
    "fatigue",
    "soreness",
    "mood",
    "motivation",
    "hydration",
    "weight",
    "bodyFat",
    "vo2max",
]

# Intervals-calculated/training metadata is not evidence of Garmin wellness sync.
NON_WELLNESS_FIELDS = {
    "id",
    "updated",
    "ctl",
    "atl",
    "rampRate",
    "ctlLoad",
    "atlLoad",
    "sportInfo",
    "customFields",
    "tempWeight",
    "tempRestingHR",
}


def is_present(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def fetch_wellness(oldest, newest):
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
            "User-Agent": "hall-training-wellness-poc/1.0",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except HTTPError as exc:
        # Do not echo response bodies: an upstream error body could contain data.
        raise RuntimeError(f"Intervals.icu HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Intervals.icu kunde inte nås: {exc.reason}") from exc

    if status < 200 or status >= 300:
        raise RuntimeError(f"Intervals.icu oväntad HTTP-status: {status}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Intervals.icu returnerade inte giltig JSON") from exc

    if not isinstance(data, list):
        raise RuntimeError("Intervals.icu wellness-svar var inte en lista")
    if any(not isinstance(row, dict) for row in data):
        raise RuntimeError("Intervals.icu wellness-svar innehöll oväntad struktur")
    return data


def summarize(rows, days, oldest, newest):
    unique_dates = {row.get("id") for row in rows if isinstance(row.get("id"), str)}
    coverage = Counter()
    discovered = Counter()
    custom_fields_days = 0

    for row in rows:
        for field in CANDIDATE_FIELDS:
            if is_present(row.get(field)):
                coverage[field] += 1

        custom_fields = row.get("customFields")
        if isinstance(custom_fields, dict) and custom_fields:
            custom_fields_days += 1

        for field, value in row.items():
            if field in NON_WELLNESS_FIELDS or field in CANDIDATE_FIELDS:
                continue
            if is_present(value):
                discovered[field] += 1

    print("Intervals.icu wellness POC — SAFE COVERAGE ONLY")
    print("No wellness values are printed or persisted by this workflow.")
    print(f"window={oldest}..{newest}")
    print(f"requested_days={days}")
    print(f"records={len(unique_dates)}")
    print()
    print("candidate_field_coverage:")
    for field in CANDIDATE_FIELDS:
        print(f"{field}={coverage[field]}/{days}")

    if discovered:
        print()
        print("other_non_null_standard_fields (names + coverage only):")
        for field in sorted(discovered):
            print(f"{field}={discovered[field]}/{days}")

    print()
    print(f"customFields_present_days={custom_fields_days}/{days}")

    useful = {field: count for field, count in coverage.items() if count > 0}
    print()
    if not useful:
        print(
            "WARNING: inga wellness-kandidatfält har data ännu; Garmin→Intervals-importen kan fortfarande pågå."
        )
        print("POC_PENDING: wellness saknar ännu data, men efterföljande aktivitetstest får fortsätta.")
        return

    print("POC_OK: minst ett wellness-kandidatfält har data.")


def main():
    parser = argparse.ArgumentParser(
        description="Read-only POC: verifiera Intervals.icu wellness-fälttäckning utan att logga värden"
    )
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    if args.days < 1 or args.days > 31:
        raise RuntimeError("--days måste vara 1..31")

    today = datetime.now(TIMEZONE).date()
    oldest_date = today - timedelta(days=args.days - 1)
    oldest = oldest_date.isoformat()
    newest = today.isoformat()

    rows = fetch_wellness(oldest, newest)
    summarize(rows, args.days, oldest, newest)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
