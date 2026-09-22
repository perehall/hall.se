#!/usr/bin/env python3
"""Collapse completed-day implementation detail into one calm outcome summary.

This is a presentation-only finalizer. Canonical plan, activity, coach and
feedback data remain untouched; the verbose generated blocks are preserved
behind "Visa detaljer".
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finalize_post_workout_ui import SPORT_LABELS, fmt_duration, local_date
from finalize_training_input_ui import FEELING_LABELS, feedback_from_override

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
OVERRIDES_FILE = ROOT / "data" / "activity_overrides.json"

CSS_MARKER = "/* completed-day-summary-v1 */"
DAY_RE = re.compile(
    r'<div class="day(?P<classes>[^"]*)" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">'
)
DIV_RE = re.compile(r"<div\b[^>]*>|</div>", re.I)

CSS = r"""
/* completed-day-summary-v1 */
.day.completed-day-simplified{padding-top:13px;padding-bottom:13px}
.completed-day-simplified>.session{display:none}
.completed-day-summary{margin-top:2px}
.completed-day-kicker{font-size:.66rem;font-weight:800;letter-spacing:.055em;text-transform:uppercase;color:var(--qp-tertiary,#64748b)}
.completed-day-title{margin:2px 0 1px;font-size:1.05rem;font-weight:800;letter-spacing:-.012em;color:var(--qp-text,#111827)}
.completed-day-meta{color:var(--qp-secondary,#64748b);font-size:.8rem;line-height:1.4;font-variant-numeric:tabular-nums}
.completed-day-section{margin-top:12px;padding-top:11px;border-top:1px solid var(--qp-line-soft,#eef2f4)}
.completed-day-section:first-of-type{margin-top:13px}
.completed-day-label{display:block;margin-bottom:3px;color:var(--qp-tertiary,#64748b);font-size:.65rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase}
.completed-day-section strong{display:block;color:var(--qp-text,#111827);font-size:.92rem;line-height:1.35}
.completed-day-section p{margin:3px 0 0;color:var(--qp-secondary,#5e6661);font-size:.82rem;line-height:1.42}
.completed-day-feedback-list{display:grid;gap:3px;margin-top:2px}
.completed-day-feedback-row{color:var(--qp-text,#111827);font-size:.82rem;line-height:1.4}
.completed-day-feedback-row span{color:var(--qp-secondary,#64748b)}
.completed-day-next{margin-top:11px}
.completed-day-details{margin-top:13px;border-top:1px solid var(--qp-line-soft,#eef2f4)}
.completed-day-details>summary{cursor:pointer;list-style:none;padding:10px 0 1px;color:var(--qp-tertiary,#64748b);font-size:.76rem;font-weight:700}
.completed-day-details>summary::-webkit-details-marker{display:none}
.completed-day-details>summary:after{content:" +"}
.completed-day-details[open]>summary:after{content:" −"}
.completed-day-details-inner{padding:9px 0 2px}
.completed-day-planned{margin:0 0 10px;padding:9px 10px;border-radius:10px;background:var(--qp-surface-soft,#f8fafc);color:var(--qp-secondary,#5e6661);font-size:.78rem;line-height:1.4}
.completed-day-planned strong{color:var(--qp-text,#111827)}
.completed-day-details .coach-title,.completed-day-details .pass-title{font-size:.7rem}
.completed-day-details .week-activity-insight{margin-top:10px}
""".strip()

PROVIDER_LABELS = {
    "WeightTraining": "Styrka",
    "Run": "Löpning",
    "TrailRun": "Traillöpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "Ride": "Cykling",
    "VirtualRide": "Cykling",
    "MountainBikeRide": "MTB",
    "Workout": "Träning",
}


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def balanced_div_end(text: str, start: int) -> int:
    depth = 0
    for match in DIV_RE.finditer(text, start):
        if match.group(0).lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    raise RuntimeError("Completed-day summary: obalanserad div-struktur.")


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def compact_text(value: str, max_chars: int = 170) -> str:
    plain = strip_tags(value)
    if len(plain) <= max_chars:
        return plain
    sentences = re.split(r"(?<=[.!?])\s+", plain)
    if sentences and len(sentences[0]) <= max_chars:
        return sentences[0]
    clipped = plain[: max_chars - 1].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(".,;:") + "…"


def activity_label(activity: dict) -> str:
    candidate = str(activity.get("display_label") or activity.get("sport_type") or "Pass").strip()
    return PROVIDER_LABELS.get(candidate, SPORT_LABELS.get(candidate, candidate))


def performed_title(activities: list[dict]) -> str:
    labels = []
    for activity in activities:
        label = activity_label(activity)
        if label not in labels:
            labels.append(label)
    if not labels:
        return "Genomfört pass"
    return " + ".join(labels)


def performed_meta(activities: list[dict]) -> str:
    parts = []
    for activity in activities:
        label = activity_label(activity)
        duration = fmt_duration(activity.get("elapsed_time_s"))
        parts.append(f"{label} {duration}")
    return " · ".join(parts)


def feedback_rows(activities: list[dict], overrides: dict) -> list[str]:
    rows = []
    mapping = overrides.get("overrides") or {}
    for activity in activities:
        override = mapping.get(str(activity.get("id"))) or {}
        feedback = feedback_from_override(override)
        if not feedback:
            continue
        bits = []
        if isinstance(feedback.get("rpe"), int):
            bits.append(f"RPE {feedback['rpe']}")
        for code in feedback.get("feeling") or []:
            label = FEELING_LABELS.get(code)
            if label and label not in bits:
                bits.append(label)
        if not bits:
            continue
        rows.append(
            f'<div class="completed-day-feedback-row"><strong>{html.escape(activity_label(activity))}</strong>'
            f'<span> · {html.escape(" · ".join(bits))}</span></div>'
        )
    return rows


def normalize_decision(value: str) -> str:
    plain = strip_tags(value).lower()
    if any(token in plain for token in ("behåll", "ingen ändring", "oförändrad")):
        return "Planen ligger kvar"
    if any(token in plain for token in ("skala", "reduc", "ändra", "juster")):
        return "Planen justeras"
    return strip_tags(value) or "Planbeslut saknas"


def extract(pattern: str, block: str) -> str:
    match = re.search(pattern, block, re.S | re.I)
    return match.group(1).strip() if match else ""


def planned_copy(block: str) -> str:
    title = extract(r'class="session-title">(.+?)</strong>', block)
    meta = extract(r'class="session-meta">(.+?)</span>', block)
    if not title:
        raw = extract(r'<div class="session[^"]*">(.*?)</div>', block)
        title = strip_tags(raw)
    result = strip_tags(title)
    meta = strip_tags(meta)
    if meta:
        result += f" · {meta}"
    return result


def detail_copy(value: str) -> str:
    value = value.replace("Automatiskt från Strava", "Passdata")
    value = value.replace("Tränings-Yoda (AI)", "Analys")
    value = value.replace("WeightTraining", "Styrka")
    value = value.replace("MountainBikeRide", "MTB")
    value = value.replace(">Passinsikt<", ">Passanalys<")
    return value


def render_summary(
    block: str,
    activities: list[dict],
    overrides: dict,
    rest: str,
) -> str:
    decision = extract(r'class="coach-decision".*?<strong>(.*?)</strong>', block)
    coach_summary = extract(r'class="coach-summary">(.*?)</div>', block)
    next_step = extract(r'class="coach-next".*?<div>(.*?)</div>\s*</div>', block)

    plan_title = normalize_decision(decision)
    plan_reason = compact_text(coach_summary, 180)
    next_copy = compact_text(next_step, 180)
    feedback = feedback_rows(activities, overrides)
    planned = planned_copy(block)

    feedback_html = ""
    if feedback:
        feedback_html = (
            '<div class="completed-day-section">'
            '<span class="completed-day-label">Din känsla</span>'
            f'<div class="completed-day-feedback-list">{"".join(feedback)}</div>'
            '</div>'
        )

    next_html = ""
    if next_copy:
        next_html = (
            '<div class="completed-day-section completed-day-next">'
            '<span class="completed-day-label">Nästa</span>'
            f'<p>{html.escape(next_copy)}</p>'
            '</div>'
        )

    planned_html = (
        f'<div class="completed-day-planned"><strong>Planerat</strong> · {html.escape(planned)}</div>'
        if planned
        else ""
    )

    return (
        '<div class="completed-day-summary">'
        '<span class="completed-day-kicker">Genomfört</span>'
        f'<div class="completed-day-title">{html.escape(performed_title(activities))}</div>'
        f'<div class="completed-day-meta">{html.escape(performed_meta(activities))}</div>'
        '<div class="completed-day-section">'
        '<span class="completed-day-label">Planpåverkan</span>'
        f'<strong>{html.escape(plan_title)}</strong>'
        + (f'<p>{html.escape(plan_reason)}</p>' if plan_reason else "")
        + '</div>'
        + feedback_html
        + next_html
        + '<details class="completed-day-details"><summary>Visa detaljer</summary>'
        '<div class="completed-day-details-inner">'
        + planned_html
        + detail_copy(rest)
        + '</div></details></div>'
    )


def simplify_completed_days(page: str, activities_state: dict, overrides: dict, today: str) -> tuple[str, int]:
    grouped: dict[str, list[dict]] = {}
    for activity in activities_state.get("activities") or []:
        day = local_date(activity)
        if day and day <= today:
            grouped.setdefault(day, []).append(activity)
    for values in grouped.values():
        values.sort(key=lambda activity: str(activity.get("start_date_local") or ""))

    matches = list(DAY_RE.finditer(page))
    changed = 0
    for match in reversed(matches):
        day = match.group("date")
        activities = grouped.get(day)
        if not activities:
            continue

        start = match.start()
        end = balanced_div_end(page, start)
        block = page[start:end]
        if 'class="completed-day-summary"' in block:
            continue

        session_start = block.find('<div class="session')
        if session_start < 0:
            continue
        session_end = balanced_div_end(block, session_start)
        rest = block[session_end:-6]  # keep the day-card closing </div> outside details
        summary = render_summary(block, activities, overrides, rest)

        opening = block[: block.find(">") + 1]
        if "completed-day-simplified" not in opening:
            opening = opening.replace('class="day', 'class="day completed-day-simplified', 1)
        new_block = opening + block[block.find(">") + 1:session_start] + summary + '</div>'
        page = page[:start] + new_block + page[end:]
        changed += 1

    return page, changed


def main() -> int:
    page = INDEX_FILE.read_text(encoding="utf-8")
    plan = load_json(PLAN_FILE, {"meta": {}})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    overrides = load_json(OVERRIDES_FILE, {"schema_version": 1, "overrides": {}})
    tz = ZoneInfo((plan.get("meta") or {}).get("timezone", "Europe/Stockholm"))
    today = datetime.now(tz).date().isoformat()

    page, changed = simplify_completed_days(page, activities, overrides, today)
    if changed:
        if CSS_MARKER not in page:
            if "</style>" not in page:
                raise RuntimeError("Completed-day summary: </style> saknas.")
            page = page.replace("</style>", CSS + "\n</style>", 1)

    INDEX_FILE.write_text(page, encoding="utf-8")
    print(f"Completed-day summary OK: {changed} genomförd(a) dag(ar) förenklade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
