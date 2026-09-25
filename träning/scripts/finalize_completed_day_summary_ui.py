#!/usr/bin/env python3
"""Render completed days as one calm, outcome-first surface.

Presentation only. Canonical plan, activity, coach and feedback state remain
untouched. The primary layer shows only what matters after a workout:
what happened, whether the plan changes, the athlete's feeling and what comes
next. Deeper analysis is available in one collapsed section.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finalize_post_workout_ui import (
    SPORT_LABELS,
    fmt_distance,
    fmt_duration,
    fmt_hr,
    local_date,
)
from finalize_training_input_ui import FEELING_LABELS, feedback_from_override, render_block
from finalize_completed_sport_icon import activity_icon_key, render_icon

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
OVERRIDES_FILE = ROOT / "data" / "activity_overrides.json"
ICON_FILE = ROOT / "data" / "sport_icons.json"

CSS_MARKER = "/* completed-day-summary-v2 */"
DAY_RE = re.compile(
    r'<div class="day(?P<classes>[^"]*)" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">'
)
DIV_RE = re.compile(r"<div\b[^>]*>|</div>", re.I)
TRAINING_INPUT_BLOCK_RE = re.compile(
    r'<!-- training-input-ui-v1:start -->\s*'
    r'(?P<section><section class="training-input"(?P<attrs>[^>]*)>.*?</section>)\s*'
    r'<!-- training-input-ui-v1:end -->',
    re.S,
)
ACTIVITY_ID_RE = re.compile(r'data-activity-id="(?P<id>\d+)"')

CSS = r"""
/* completed-day-summary-v2 */
.day.completed-day-simplified{padding-top:14px;padding-bottom:16px}
.completed-day-simplified>.session,.completed-day-simplified>.swim-workout{display:none}
.completed-day-summary{margin-top:1px;color:var(--qp-text,#111827)}
.completed-day-kicker{display:block;margin-bottom:5px;color:var(--qp-tertiary,#64748b);font-size:.64rem;font-weight:850;letter-spacing:.075em;text-transform:uppercase}
.completed-day-title{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:0;font-size:1.08rem;font-weight:850;letter-spacing:-.018em;line-height:1.28}
.completed-day-title-sport{display:inline-flex;align-items:center;gap:7px}
.completed-day-title .sport-icon{width:19px;height:19px;flex:0 0 auto;color:var(--qp-secondary,#59636f)}
.completed-day-title .icon-swim,.completed-day-title .icon-bike,.completed-day-title .icon-enduro,.completed-day-title .icon-strength{width:21px}
.completed-day-title-sep{color:var(--qp-tertiary,#94a3b8);font-weight:550}
.completed-day-meta{margin-top:3px;color:var(--qp-secondary,#64748b);font-size:.81rem;line-height:1.4;font-variant-numeric:tabular-nums}
.completed-day-summary-panel{margin-top:13px;border:1px solid var(--qp-line,#e2e8f0);border-radius:15px;background:rgba(255,255,255,.72);overflow:hidden}
.completed-day-summary-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;padding:12px 13px}
.completed-day-summary-row+.completed-day-summary-row{border-top:1px solid var(--qp-line-soft,#eef2f4)}
.completed-day-summary-copy{min-width:0}
.completed-day-label{display:block;margin-bottom:3px;color:var(--qp-tertiary,#64748b);font-size:.63rem;font-weight:850;letter-spacing:.065em;text-transform:uppercase}
.completed-day-summary-row strong{display:block;color:var(--qp-text,#111827);font-size:.93rem;line-height:1.35}
.completed-day-summary-row p{margin:3px 0 0;color:var(--qp-secondary,#5e6661);font-size:.8rem;line-height:1.42}
.completed-day-feedback-list{display:grid;gap:6px}
.completed-day-feedback-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:start}
.completed-day-feedback-main{min-width:0}
.completed-day-feedback-main strong{display:inline;font-size:.9rem}
.completed-day-feedback-main span{display:inline;margin-left:5px;color:var(--qp-secondary,#64748b);font-size:.8rem}
.completed-day-feedback-row .completed-day-inline-input{display:contents}
.completed-day-feedback-row .completed-day-inline-input>.training-input-compact{display:contents}
.completed-day-feedback-row .completed-day-inline-input>.training-input-compact>div:first-child{display:none}
.completed-day-feedback-row .completed-day-inline-input .training-input-toggle{grid-column:2;grid-row:1;margin:0;padding:1px 0 0;align-self:start;font-size:.76rem}
.completed-day-feedback-row .completed-day-inline-input .training-input-editor{grid-column:1/-1;margin-top:7px;padding-top:10px;border-top:1px solid var(--qp-line-soft,#eef2f4)}
.completed-day-passdata{margin-top:12px;padding:11px 13px 12px;border:1px solid var(--qp-line,#e2e8f0);border-radius:15px;background:rgba(255,255,255,.62)}
.completed-day-passdata-title{display:block;margin-bottom:8px;color:var(--qp-tertiary,#64748b);font-size:.63rem;font-weight:850;letter-spacing:.065em;text-transform:uppercase}
.completed-day-passdata-group+.completed-day-passdata-group{margin-top:10px;padding-top:10px;border-top:1px solid var(--qp-line-soft,#eef2f4)}
.completed-day-passdata-sport{display:block;margin:0 0 7px;color:var(--qp-secondary,#475569);font-size:.73rem;font-weight:800}
.completed-day-passdata-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0}
.completed-day-metric{min-width:0;padding:0 10px;border-left:1px solid var(--qp-line-soft,#eef2f4)}
.completed-day-metric:first-child{padding-left:0;border-left:0}
.completed-day-metric:last-child{padding-right:0}
.completed-day-metric span{display:block;color:var(--qp-tertiary,#64748b);font-size:.67rem;line-height:1.25}
.completed-day-metric strong{display:block;margin-top:2px;color:var(--qp-text,#111827);font-size:.9rem;line-height:1.3;font-variant-numeric:tabular-nums;white-space:nowrap}
.completed-day-details{margin-top:12px;border:1px solid var(--qp-line,#e2e8f0);border-radius:15px;background:rgba(255,255,255,.55)}
.completed-day-details>summary{position:relative;cursor:pointer;list-style:none;padding:12px 38px 12px 13px}
.completed-day-details>summary::-webkit-details-marker{display:none}
.completed-day-details>summary:after{content:"⌄";position:absolute;right:14px;top:50%;transform:translateY(-53%);color:var(--qp-tertiary,#64748b);font-size:1rem}
.completed-day-details[open]>summary:after{content:"⌃"}
.completed-day-details-title{display:block;color:var(--qp-text,#111827);font-size:.84rem;font-weight:820}
.completed-day-details-subtitle{display:block;margin-top:2px;color:var(--qp-tertiary,#64748b);font-size:.72rem;font-weight:500}
.completed-day-details-inner{padding:0 13px 13px;border-top:1px solid var(--qp-line-soft,#eef2f4)}
.completed-day-detail-block{padding-top:11px}
.completed-day-detail-block+.completed-day-detail-block{margin-top:10px;border-top:1px solid var(--qp-line-soft,#eef2f4)}
.completed-day-detail-block>span{display:block;margin-bottom:4px;color:var(--qp-tertiary,#64748b);font-size:.63rem;font-weight:850;letter-spacing:.065em;text-transform:uppercase}
.completed-day-detail-block p{margin:0;color:var(--qp-secondary,#475569);font-size:.79rem;line-height:1.46}
.completed-day-detail-line{display:flex;gap:5px;align-items:baseline;color:var(--qp-secondary,#475569);font-size:.78rem;line-height:1.4}
.completed-day-detail-line strong{color:var(--qp-text,#111827)}
.completed-day-analysis-item+.completed-day-analysis-item{margin-top:8px}
.completed-day-analysis-item>strong{display:block;margin-bottom:2px;color:var(--qp-text,#111827);font-size:.76rem}
.completed-day-evidence{margin-top:9px}
.completed-day-evidence>summary{cursor:pointer;list-style:none;color:var(--qp-secondary,#59636f);font-size:.75rem;font-weight:780}
.completed-day-evidence>summary::-webkit-details-marker{display:none}
.completed-day-evidence>summary:after{content:" +"}
.completed-day-evidence[open]>summary:after{content:" −"}
.completed-day-evidence-body{display:grid;gap:9px;margin-top:8px;padding:10px;border-radius:11px;background:var(--qp-surface-soft,#f8fafc)}
.completed-day-evidence-block+.completed-day-evidence-block{padding-top:8px;border-top:1px solid var(--qp-line-soft,#e2e8f0)}
.completed-day-evidence-block>strong{display:block;margin-bottom:4px;color:var(--qp-secondary,#475569);font-size:.65rem;text-transform:uppercase;letter-spacing:.055em}
.completed-day-evidence-block ul{margin:0;padding-left:17px;color:var(--qp-secondary,#475569);font-size:.75rem;line-height:1.43}
.completed-day-evidence-block li+li{margin-top:3px}
@media(max-width:620px){
  .completed-day-summary-panel,.completed-day-passdata,.completed-day-details{border-radius:13px}
  .completed-day-passdata-grid{grid-template-columns:repeat(2,minmax(0,1fr));row-gap:9px}
  .completed-day-metric:nth-child(3){padding-left:0;border-left:0}
  .completed-day-summary-row{padding:11px 12px}
}
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


def compact_text(value: str, max_chars: int = 150) -> str:
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


def training_input_blocks(page: str) -> dict[int, dict[str, str]]:
    blocks: dict[int, dict[str, str]] = {}
    for match in TRAINING_INPUT_BLOCK_RE.finditer(page):
        section = match.group("section")
        activity_match = ACTIVITY_ID_RE.search(section)
        if not activity_match:
            continue
        activity_id = int(activity_match.group("id"))
        embedded = section.replace(
            '<section class="training-input"',
            '<section class="training-input completed-day-inline-input"',
            1,
        )
        blocks[activity_id] = {
            "full": match.group(0),
            "section": embedded,
        }
    return blocks


def processed_event_keys_from_override(override: dict) -> list[str]:
    values = override.get("training_input_event_keys") or []
    if not isinstance(values, list):
        values = []
    keys = [
        str(value).strip()
        for value in values
        if re.fullmatch(r"training-input:[0-9a-f]{24}", str(value).strip())
    ]
    legacy = str(override.get("last_training_input_event_key") or "").strip()
    if re.fullmatch(r"training-input:[0-9a-f]{24}", legacy) and legacy not in keys:
        keys.append(legacy)
    return keys[-8:]


def ensure_activity_input_blocks(
    input_blocks: dict[int, dict[str, str]],
    activities_state: dict,
    overrides: dict,
) -> dict[int, dict[str, str]]:
    mapping = overrides.get("overrides") or {}
    for activity in activities_state.get("activities") or []:
        activity_id = activity.get("id")
        if not isinstance(activity_id, int) or activity_id in input_blocks:
            continue
        override = mapping.get(str(activity_id)) or {}
        rendered = render_block(
            activity,
            processed_event_keys_from_override(override),
            feedback_from_override(override),
        )
        match = TRAINING_INPUT_BLOCK_RE.search(rendered)
        if not match:
            raise RuntimeError(
                f"Completed-day summary: kunde inte materialisera editor för aktivitet {activity_id}."
            )
        section = match.group("section").replace(
            '<section class="training-input"',
            '<section class="training-input completed-day-inline-input"',
            1,
        )
        input_blocks[activity_id] = {
            "full": "",
            "section": section,
        }
    return input_blocks


def performed_title_html(activities: list[dict], icon_registry: dict) -> tuple[str, list[str]]:
    seen = set()
    parts = []
    icon_keys = []
    for activity in activities:
        label = activity_label(activity)
        key = activity_icon_key(activity)
        identity = (key, label)
        if identity in seen:
            continue
        seen.add(identity)
        icon_keys.append(key)
        parts.append(
            f'<span class="completed-day-title-sport" data-visible-sport-icon="{html.escape(key)}">'
            f'{render_icon(key, icon_registry)}<span>{html.escape(label)}</span></span>'
        )
    if not parts:
        return html.escape("Genomfört pass"), []
    return '<span class="completed-day-title-sep">+</span>'.join(parts), icon_keys


def performed_meta(activities: list[dict]) -> str:
    if len(activities) == 1:
        activity = activities[0]
        parts = [fmt_duration(activity.get("elapsed_time_s")), fmt_distance(activity)]
        return " · ".join(value for value in parts if value and value != "—")

    parts = []
    for activity in activities:
        duration = fmt_duration(activity.get("elapsed_time_s"))
        parts.append(f"{activity_label(activity)} {duration}")
    return " · ".join(parts)


def feedback_rows(
    activities: list[dict],
    overrides: dict,
    input_blocks: dict[int, dict[str, str]] | None = None,
    consumed_input_ids: set[int] | None = None,
) -> list[str]:
    rows = []
    mapping = overrides.get("overrides") or {}
    input_blocks = input_blocks or {}
    consumed_input_ids = consumed_input_ids if consumed_input_ids is not None else set()
    show_sport = len(activities) > 1

    for activity in activities:
        activity_id = activity.get("id")
        override = mapping.get(str(activity_id)) or {}
        feedback = feedback_from_override(override)
        input_block = input_blocks.get(activity_id) if isinstance(activity_id, int) else None
        if not feedback and not input_block:
            continue

        bits = []
        if feedback and isinstance(feedback.get("rpe"), int):
            bits.append(f"RPE {feedback['rpe']}")
        if feedback:
            for code in feedback.get("feeling") or []:
                label = FEELING_LABELS.get(code)
                if label and label not in bits:
                    bits.append(label)

        status = " · ".join(bits) if bits else "Inte utvärderat"
        if show_sport:
            feedback_main = (
                f'<strong>{html.escape(activity_label(activity))}</strong>'
                f'<span>{html.escape(status)}</span>'
            )
        else:
            feedback_main = f'<strong>{html.escape(status)}</strong>'

        editor = ""
        if input_block and isinstance(activity_id, int):
            editor = input_block["section"]
            consumed_input_ids.add(activity_id)

        rows.append(
            f'<div class="completed-day-feedback-row" data-feedback-activity-id="{html.escape(str(activity_id))}">'
            f'<div class="completed-day-feedback-main">{feedback_main}</div>{editor}</div>'
        )
    return rows


def feedback_comments(activities: list[dict], overrides: dict) -> list[tuple[str, str]]:
    mapping = overrides.get("overrides") or {}
    comments = []
    for activity in activities:
        feedback = feedback_from_override(mapping.get(str(activity.get("id"))) or {})
        text = str((feedback or {}).get("text") or "").strip()
        if text:
            comments.append((activity_label(activity), text))
    return comments


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
    if not title:
        title = strip_tags(extract(r'class="swim-session-head".*?<strong[^>]*>(.*?)</strong>', block))
        meta = strip_tags(extract(r'class="swim-meta">(.*?)</span>', block))
    result = strip_tags(title)
    meta = strip_tags(meta)
    if meta and meta.lower() not in result.lower():
        result += f" · {meta}"
    if result.lower() == "ingen planerad träning":
        return "Vilodag"
    return result


def primary_plan_block(block: str) -> tuple[int, int] | None:
    """Find the visible planned-workout node independent of sport-specific markup."""
    candidates = []
    for marker in ('<div class="session', '<div class="swim-workout'):
        start = block.find(marker)
        if start >= 0:
            candidates.append(start)
    if not candidates:
        return None
    start = min(candidates)
    return start, balanced_div_end(block, start)


def summary_reason(value: str) -> str:
    plain = strip_tags(value)
    if not plain:
        return ""
    clauses = [
        clause.strip()
        for clause in re.split(r";|(?<=[.!?])\s+", plain)
        if clause.strip()
    ]
    feedback_tokens = (
        "användaren rapporterar",
        "du rapporterar",
        "rpe ",
        "pigg känsla",
        "trött känsla",
        "subjektiv känsla",
    )
    for clause in clauses:
        lower = clause.lower()
        if any(token in lower for token in feedback_tokens):
            continue
        return compact_text(clause, 135)
    return ""


def clean_next_step(value: str, plan_title: str) -> str:
    plain = strip_tags(value)
    if not plain:
        return ""
    plain = re.sub(r"\b20\d{2}-\d{2}-\d{2}\b", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if plan_title == "Planen ligger kvar" and ";" in plain:
        plain = plain.split(";", 1)[0].strip()
    if plain and plain[-1] not in ".!?":
        plain += "."
    return compact_text(plain, 145)


def max_hr(activity: dict) -> str:
    value = activity.get("max_heartrate")
    return str(round(float(value))) if value else "—"


def passdata_html(activities: list[dict]) -> str:
    groups = []
    show_sport = len(activities) > 1
    for activity in activities:
        metrics = [
            ("Distans", fmt_distance(activity)),
            ("Tid", fmt_duration(activity.get("elapsed_time_s"))),
            ("Snittpuls", fmt_hr(activity)),
            ("Maxpuls", max_hr(activity)),
        ]
        metrics = [(label, value) for label, value in metrics if value and value != "—"]
        if not metrics:
            continue
        cells = "".join(
            '<div class="completed-day-metric">'
            f'<span>{html.escape(label)}</span><strong>{html.escape(value)}</strong>'
            '</div>'
            for label, value in metrics
        )
        sport = (
            f'<strong class="completed-day-passdata-sport">{html.escape(activity_label(activity))}</strong>'
            if show_sport
            else ""
        )
        groups.append(
            '<div class="completed-day-passdata-group">'
            + sport
            + f'<div class="completed-day-passdata-grid">{cells}</div>'
            + '</div>'
        )
    if not groups:
        return ""
    return (
        '<div class="completed-day-passdata">'
        '<span class="completed-day-passdata-title">Passdata</span>'
        + "".join(groups)
        + '</div>'
    )


def insight_copy(rest: str, activity_id: object) -> str:
    if activity_id is None:
        return ""
    match = re.search(
        rf'<section class="week-activity-insight" data-week-activity-insight="{re.escape(str(activity_id))}">(.*?)</section>',
        rest,
        re.S | re.I,
    )
    if not match:
        return ""
    return compact_text(
        extract(r'class="week-activity-insight-copy">(.*?)</p>', match.group(1)),
        260,
    )


def evidence_blocks(rest: str) -> list[str]:
    blocks = []
    for raw in re.findall(
        r'<div class="week-activity-evidence-block">(.*?)</div>',
        rest,
        re.S | re.I,
    ):
        clean = raw.strip()
        if clean:
            blocks.append(
                '<div class="completed-day-evidence-block">' + clean + '</div>'
            )
    return blocks


def details_html(
    block: str,
    rest: str,
    activities: list[dict],
    overrides: dict,
    coach_summary: str,
) -> str:
    planned = planned_copy(block)
    analysis_items = []
    for activity in activities:
        copy = insight_copy(rest, activity.get("id"))
        if copy:
            label = (
                f'<strong>{html.escape(activity_label(activity))}</strong>'
                if len(activities) > 1
                else ""
            )
            analysis_items.append(
                f'<div class="completed-day-analysis-item">{label}<p>{html.escape(copy)}</p></div>'
            )
    if not analysis_items and coach_summary:
        analysis_items.append(
            '<div class="completed-day-analysis-item">'
            f'<p>{html.escape(compact_text(coach_summary, 260))}</p></div>'
        )

    comments = feedback_comments(activities, overrides)
    evidence = evidence_blocks(rest)

    body = []
    if planned:
        body.append(
            '<div class="completed-day-detail-block">'
            '<span>Ursprungsplan</span>'
            f'<div class="completed-day-detail-line"><strong>{html.escape(planned)}</strong></div>'
            '</div>'
        )
    if analysis_items:
        body.append(
            '<div class="completed-day-detail-block">'
            '<span>Passets effekt</span>'
            + "".join(analysis_items)
            + '</div>'
        )
    if comments:
        comment_html = "".join(
            (
                f'<div class="completed-day-analysis-item"><strong>{html.escape(label)}</strong>'
                f'<p>{html.escape(text)}</p></div>'
                if len(comments) > 1
                else f'<div class="completed-day-analysis-item"><p>{html.escape(text)}</p></div>'
            )
            for label, text in comments
        )
        body.append(
            '<div class="completed-day-detail-block">'
            '<span>Din kommentar</span>'
            + comment_html
            + '</div>'
        )
    if evidence:
        body.append(
            '<div class="completed-day-detail-block">'
            '<details class="completed-day-evidence"><summary>Motivering</summary>'
            '<div class="completed-day-evidence-body">'
            + "".join(evidence)
            + '</div></details></div>'
        )

    if not body:
        return ""

    return (
        '<details class="completed-day-details">'
        '<summary><span class="completed-day-details-title">Analys och motivering</span>'
        '<span class="completed-day-details-subtitle">Passets effekt, kommentar och underlag</span></summary>'
        '<div class="completed-day-details-inner">'
        + "".join(body)
        + '</div></details>'
    )


def render_summary(
    block: str,
    activities: list[dict],
    overrides: dict,
    rest: str,
    input_blocks: dict[int, dict[str, str]] | None = None,
    consumed_input_ids: set[int] | None = None,
    icon_registry: dict | None = None,
) -> str:
    decision = extract(r'class="coach-decision".*?<strong>(.*?)</strong>', block)
    if not decision:
        decision = extract(
            r'class="week-activity-plan-impact".*?<strong>(.*?)</strong>',
            block,
        )
    coach_summary = extract(r'class="coach-summary">(.*?)</div>', block)
    if not coach_summary and activities:
        coach_summary = insight_copy(block, activities[0].get("id"))
    next_step = extract(r'class="coach-next".*?<div>(.*?)</div>\s*</div>', block)

    plan_title = normalize_decision(decision)
    plan_reason = summary_reason(coach_summary)
    next_copy = clean_next_step(next_step, plan_title)
    feedback = feedback_rows(
        activities,
        overrides,
        input_blocks=input_blocks,
        consumed_input_ids=consumed_input_ids,
    )
    title_html, visible_icon_keys = performed_title_html(activities, icon_registry or {})
    visible_icons_attr = ",".join(visible_icon_keys)

    plan_row = (
        '<div class="completed-day-summary-row">'
        '<div class="completed-day-summary-copy">'
        '<span class="completed-day-label">Sammanfattning</span>'
        f'<strong>{html.escape(plan_title)}</strong>'
        + (f'<p>{html.escape(plan_reason)}</p>' if plan_reason else "")
        + '</div></div>'
    )

    feedback_row = ""
    if feedback:
        feedback_row = (
            '<div class="completed-day-summary-row">'
            '<div class="completed-day-summary-copy">'
            '<span class="completed-day-label">Din känsla</span>'
            f'<div class="completed-day-feedback-list">{"".join(feedback)}</div>'
            '</div></div>'
        )

    next_row = ""
    if next_copy:
        next_row = (
            '<div class="completed-day-summary-row">'
            '<div class="completed-day-summary-copy">'
            '<span class="completed-day-label">Nästa steg</span>'
            f'<p>{html.escape(next_copy)}</p>'
            '</div></div>'
        )

    details = details_html(block, rest, activities, overrides, coach_summary)

    return (
        f'<div class="completed-day-summary" data-visible-sport-icons="{html.escape(visible_icons_attr)}">'
        '<span class="completed-day-kicker">Genomfört</span>'
        f'<div class="completed-day-title">{title_html}</div>'
        f'<div class="completed-day-meta">{html.escape(performed_meta(activities))}</div>'
        '<div class="completed-day-summary-panel">'
        + plan_row
        + feedback_row
        + next_row
        + '</div>'
        + passdata_html(activities)
        + details
        + '</div>'
    )


def simplify_completed_days(
    page: str,
    activities_state: dict,
    overrides: dict,
    today: str,
    icon_registry: dict | None = None,
) -> tuple[str, int]:
    input_blocks = ensure_activity_input_blocks(
        training_input_blocks(page), activities_state, overrides
    )
    consumed_input_ids: set[int] = set()
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

        primary = primary_plan_block(block)
        if primary is None:
            continue
        primary_start, primary_end = primary
        rest = block[primary_end:-6]
        summary = render_summary(
            block,
            activities,
            overrides,
            rest,
            input_blocks=input_blocks,
            consumed_input_ids=consumed_input_ids,
            icon_registry=icon_registry or {},
        )

        opening = block[: block.find(">") + 1]
        if "completed-day-simplified" not in opening:
            opening = opening.replace('class="day', 'class="day completed-day-simplified', 1)
        # Keep the original session in the DOM for accessibility/icon contracts;
        # CSS hides it in the compact completed state.
        new_block = opening + block[block.find(">") + 1:primary_end] + summary + '</div>'
        page = page[:start] + new_block + page[end:]
        changed += 1

    for activity_id in consumed_input_ids:
        source = input_blocks.get(activity_id)
        if source:
            page = page.replace(source["full"], "", 1)

    return page, changed


def install_css(page: str) -> str:
    page = re.sub(
        r'/\* completed-day-summary-v1 \*/.*?(?=(?:/\*|</style>))',
        "",
        page,
        flags=re.S,
    )
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Completed-day summary: </style> saknas.")
    return page.replace("</style>", CSS + "\n</style>", 1)


def main() -> int:
    page = INDEX_FILE.read_text(encoding="utf-8")
    plan = load_json(PLAN_FILE, {"meta": {}})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    overrides = load_json(OVERRIDES_FILE, {"schema_version": 1, "overrides": {}})
    icon_registry = load_json(ICON_FILE, {"icons": {}}).get("icons") or {}
    tz = ZoneInfo((plan.get("meta") or {}).get("timezone", "Europe/Stockholm"))
    today = datetime.now(tz).date().isoformat()

    page, changed = simplify_completed_days(
        page,
        activities,
        overrides,
        today,
        icon_registry=icon_registry,
    )
    if changed:
        page = install_css(page)

    INDEX_FILE.write_text(page, encoding="utf-8")
    print(f"Completed-day summary v2 OK: {changed} genomförd(a) dag(ar) förenklade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
