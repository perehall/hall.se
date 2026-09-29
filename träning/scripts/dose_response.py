#!/usr/bin/env python3
"""Deterministic dose-response facts derived from recorded training.

This module does not prescribe training. It separates four concepts that were
previously conflated by the planner:

- demonstrated: a dose was completed;
- tolerated: it was completed without an explicit same-session warning signal;
- absorbed: a comparable dose has been repeated with supportive user feedback,
  without a next-day recovery warning attached to the later exposure;
- progression_ready: absorbed evidence exists and the latest comparable exposure
  does not contain an explicit warning signal.

The 24-72 h observations are contextual signals, never causal attribution.
Later fatigue may have many causes, especially when another workout intervenes.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

RPE_RE = re.compile(r"\brpe\s*(?P<value>\d+(?:[.,]\d+)?)\s*(?:/\s*10)?", re.IGNORECASE)

SUPPORTIVE_TERMS = (
    "kunde gjort mer",
    "kunde ha gjort mer",
    "superpigg",
    "pigg",
    "fräsch",
    "frisk i benen",
    "riktigt bra",
    "väldigt bra kontroll",
    "bra kontroll",
    "god kontroll",
    "kände mig stark",
    "stark",
)

CAUTION_TERMS = (
    "väldigt sliten",
    "sliten",
    "tunga ben",
    "tung i benen",
    "trött",
    "helt slut",
    "smärta",
    "ont i",
    "seg i benen",
)

RECOVERY_SUPPORTIVE_TERMS = (
    "superpigg",
    "pigg",
    "fräsch",
    "återhämtad",
    "kunde gjort mer",
    "kunde ha gjort mer",
)

RECOVERY_CAUTION_TERMS = (
    "väldigt sliten",
    "sliten",
    "tunga ben",
    "tung i benen",
    "trött",
    "seg i benen",
    "smärta",
    "ont i",
)

CAPABILITY_METRIC = {
    "run_threshold": "work_minutes",
    "run_hill_quality": "repetitions",
    "run_easy_distance": "duration_minutes",
    "swim_aerobic": "distance_m",
    "swim_threshold": "distance_m",
    "mtb_technical": "duration_minutes",
    "strength_unilateral": "duration_minutes",
}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _rpe_values(report):
    values = []
    for match in RPE_RE.finditer(str(report or "")):
        try:
            value = float(match.group("value").replace(",", "."))
        except (TypeError, ValueError):
            continue
        if 0 <= value <= 10:
            values.append(value)
    return values


def direct_response(report):
    """Classify explicit same-session feedback without inventing recovery."""
    text = str(report or "").strip()
    if not text:
        return {
            "signal": "unknown",
            "rpe_values": [],
            "supportive_terms": [],
            "caution_terms": [],
        }

    lower = text.lower()
    rpes = _rpe_values(text)
    supportive = [term for term in SUPPORTIVE_TERMS if term in lower]
    caution = [term for term in CAUTION_TERMS if term in lower]

    # RPE is interpreted conservatively and only as user-reported effort.
    # A high RPE is a warning signal; a low RPE alone is not evidence of absorption.
    if caution or (rpes and max(rpes) >= 8.0):
        signal = "caution"
    elif supportive and (not rpes or max(rpes) <= 7.0):
        signal = "supportive"
    else:
        signal = "neutral"

    return {
        "signal": signal,
        "rpe_values": rpes,
        "supportive_terms": supportive,
        "caution_terms": caution,
    }


def recovery_context(session_date, sessions, *, today):
    """Collect explicit 24-72 h context without claiming causality."""
    if isinstance(session_date, str):
        session_date = date.fromisoformat(session_date)
    if isinstance(today, str):
        today = date.fromisoformat(today)

    observations = []
    for row in sessions:
        text = str(row.get("user_report") or "").strip()
        if not text:
            continue
        try:
            day = date.fromisoformat(str(row.get("date")))
        except (TypeError, ValueError):
            continue
        delta = (day - session_date).days
        if delta < 1 or delta > 3:
            continue

        lower = text.lower()
        supportive = [term for term in RECOVERY_SUPPORTIVE_TERMS if term in lower]
        caution = [term for term in RECOVERY_CAUTION_TERMS if term in lower]
        if not supportive and not caution:
            continue
        observations.append(
            {
                "date": day.isoformat(),
                "activity_id": row.get("id"),
                "family": row.get("family"),
                "signal": "caution" if caution else "supportive",
                "supportive_terms": supportive,
                "caution_terms": caution,
            }
        )

    signals = [row["signal"] for row in observations]
    if "caution" in signals:
        signal = "caution"
    elif "supportive" in signals:
        signal = "supportive"
    else:
        signal = "unobserved"

    return {
        "window_complete": session_date <= today - timedelta(days=3),
        "signal": signal,
        "observations": observations,
        "causal_interpretation": "not_inferred",
    }


def _evidence_by_activity(evidence, capability, metric):
    result = {}
    for item in evidence:
        if item.get("capability") != capability:
            continue
        activity_id = str(item.get("activity_id") or "")
        value = _number(item.get(metric))
        if not activity_id or value is None:
            continue
        previous = result.get(activity_id)
        if previous is None or value > previous:
            result[activity_id] = value
    return result


def _session_duration_minutes(row):
    value = _number(row.get("elapsed_time_s"))
    return value / 60.0 if value is not None else None


def _session_distance(row):
    return _number(row.get("distance_m"))


def _candidate_exposures(sessions, evidence):
    threshold = _evidence_by_activity(evidence, "run_threshold", "work_minutes")
    hills = _evidence_by_activity(evidence, "run_hill_quality", "repetitions")
    swim_threshold = _evidence_by_activity(evidence, "swim_threshold", "distance_m")
    quality_run_ids = set(threshold) | set(hills)

    exposures = defaultdict(list)
    for row in sessions:
        if row.get("classification") == "recreation":
            continue
        activity_id = str(row.get("id") or "")
        family = str(row.get("family") or "")
        if not activity_id:
            continue

        if activity_id in threshold:
            exposures["run_threshold"].append((row, threshold[activity_id]))
        if activity_id in hills:
            exposures["run_hill_quality"].append((row, hills[activity_id]))
        if activity_id in swim_threshold:
            exposures["swim_threshold"].append((row, swim_threshold[activity_id]))

        if family == "run" and activity_id not in quality_run_ids:
            value = _session_duration_minutes(row)
            if value is not None:
                exposures["run_easy_distance"].append((row, value))
        if family == "swim" and activity_id not in swim_threshold:
            value = _session_distance(row)
            if value is not None:
                exposures["swim_aerobic"].append((row, value))
        if family == "bike":
            value = _session_duration_minutes(row)
            if value is not None:
                exposures["mtb_technical"].append((row, value))
        if family == "strength":
            value = _session_duration_minutes(row)
            if value is not None:
                exposures["strength_unilateral"].append((row, value))

    return exposures


def _comparable_count(rows, value):
    """Count exposures close enough to establish repeatability of the dose."""
    if value <= 0:
        return 0
    lower = value * 0.90
    upper = value * 1.10
    return sum(1 for row in rows if lower <= row["dose_value"] <= upper)


def build_dose_response(sessions, evidence, *, today):
    """Build capability-level dose-response facts from observed sessions."""
    if isinstance(today, str):
        today = date.fromisoformat(today)

    by_capability = {}
    candidates = _candidate_exposures(sessions, evidence)

    for capability, pairs in sorted(candidates.items()):
        rows = []
        for session, value in pairs:
            response = direct_response(session.get("user_report"))
            recovery = recovery_context(session.get("date"), sessions, today=today)
            rows.append(
                {
                    "activity_id": session.get("id"),
                    "date": session.get("date"),
                    "dose_value": round(float(value), 2),
                    "metric": CAPABILITY_METRIC[capability],
                    "direct_response": response,
                    "recovery_context_24_72h": recovery,
                }
            )

        rows.sort(key=lambda item: (str(item["date"]), str(item["activity_id"])))
        for row in rows:
            repeated = _comparable_count(rows, row["dose_value"]) >= 2
            direct = row["direct_response"]["signal"]
            recovery = row["recovery_context_24_72h"]["signal"]

            if direct == "caution":
                status = "caution"
            elif direct == "supportive" and repeated and recovery != "caution":
                status = "absorbed"
            elif direct == "supportive" and repeated and recovery == "caution":
                status = "tolerated_with_recovery_caution"
            else:
                status = "tolerated"

            row["repeat_supported"] = repeated
            row["response_status"] = status

        demonstrated = max((row["dose_value"] for row in rows), default=None)
        tolerated = max(
            (
                row["dose_value"]
                for row in rows
                if row["response_status"] in {"absorbed", "tolerated"}
            ),
            default=None,
        )
        absorbed = max(
            (row["dose_value"] for row in rows if row["response_status"] == "absorbed"),
            default=None,
        )
        latest = rows[-1] if rows else None

        progression_ready = bool(
            absorbed is not None
            and latest is not None
            and latest["direct_response"]["signal"] != "caution"
            and latest["response_status"] != "tolerated_with_recovery_caution"
            and latest["dose_value"] >= absorbed * 0.90
        )

        if not rows:
            reason = "Ingen verifierad exponering finns."
        elif latest["direct_response"]["signal"] == "caution":
            reason = "Senaste jämförbara exponeringen innehåller en explicit varningssignal från användaren."
        elif absorbed is None:
            reason = "Dos har demonstrerats/tolererats men saknar ännu upprepad stödjande respons för att klassas som absorberad."
        elif latest["response_status"] == "tolerated_with_recovery_caution":
            reason = "Senaste exponeringen har stödjande passrespons men 24–72 h-kontexten innehåller en varningssignal; kausalitet antas inte."
        elif latest["dose_value"] < absorbed * 0.90:
            reason = "Senaste jämförbara dos ligger tydligt under tidigare absorberad nivå."
        else:
            reason = "Upprepad jämförbar dos med stödjande respons ger stöd för att dosen är absorberad."

        by_capability[capability] = {
            "metric": CAPABILITY_METRIC[capability],
            "demonstrated_value": demonstrated,
            "tolerated_value": tolerated,
            "absorbed_value": absorbed,
            "progression_ready": progression_ready,
            "progression_reason": reason,
            "latest_exposure": latest,
            "exposures": rows[-8:],
        }

    return {
        "model": "demonstrated_tolerated_absorbed_v1",
        "principle": (
            "Genomförd dos är inte samma sak som absorberad dos. Automatisk progression kräver "
            "upprepad jämförbar exponering med stödjande användarrespons; 24–72 h-signaler används "
            "som kontext och tillskrivs inte kausalt ett tidigare pass."
        ),
        "by_capability": by_capability,
    }


def build_load_windows(sessions, *, today):
    """Fact-only rolling duration/exposure windows; no synthetic training score."""
    if isinstance(today, str):
        today = date.fromisoformat(today)

    specs = {
        "recent_7d": (today - timedelta(days=6), today),
        "previous_7d": (today - timedelta(days=13), today - timedelta(days=7)),
        "recent_28d": (today - timedelta(days=27), today),
    }
    result = {}
    for key, (start, end) in specs.items():
        selected = []
        for row in sessions:
            try:
                day = date.fromisoformat(str(row.get("date")))
            except (TypeError, ValueError):
                continue
            if start <= day <= end and row.get("classification") != "recreation":
                selected.append(row)

        by_family = defaultdict(lambda: {"time_s": 0, "activity_count": 0, "active_days": set()})
        active_days = set()
        total_s = 0
        for row in selected:
            seconds = int(row.get("elapsed_time_s") or 0)
            family = str(row.get("family") or "other")
            day = str(row.get("date"))
            total_s += max(0, seconds)
            active_days.add(day)
            bucket = by_family[family]
            bucket["time_s"] += max(0, seconds)
            bucket["activity_count"] += 1
            bucket["active_days"].add(day)

        result[key] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "time_s": total_s,
            "activity_count": len(selected),
            "active_days": len(active_days),
            "by_family": {
                family: {
                    "time_s": values["time_s"],
                    "activity_count": values["activity_count"],
                    "active_days": len(values["active_days"]),
                }
                for family, values in sorted(by_family.items())
            },
        }

    return {
        "windows": result,
        "interpretation_boundary": (
            "Fönstren är observerad duration och exponeringsfrekvens. De är inte TSS, belastningspoäng, "
            "återhämtningsmått eller bevis för lämplig framtida veckodos."
        ),
    }
