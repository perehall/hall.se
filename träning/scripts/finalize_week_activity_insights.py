#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finalize_post_workout_ui import (
    build_outcome_insight,
    first_sentence,
    fmt_distance,
    fmt_duration,
    fmt_hr,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
PERFORMANCE_FILE = ROOT / "data" / "performance_history.json"
COACH_FILE = ROOT / "data" / "coach.json"
INDEX_FILE = ROOT / "index.html"

CSS_MARKER = "/* week-activity-insight-v2 */"
CARD_MARKER = 'data-week-activity-insight="'

CSS = r"""
/* week-activity-insight-v2 */
.week-activity-insight{margin:9px 0 3px;padding:12px 13px;border:1px solid #dbe5df;border-radius:14px;background:#fff}
.week-activity-insight-kicker{font-size:.65rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#64748b}
.week-activity-insight h3{margin:4px 0 5px;font-size:1rem;line-height:1.28;letter-spacing:-.01em}
.week-activity-metrics{margin:0 0 7px;color:#64748b;font-size:.76rem;font-variant-numeric:tabular-nums}
.week-activity-insight-copy{margin:0;color:#475569;font-size:.82rem;line-height:1.45}
.week-activity-plan-impact{display:flex;gap:7px;align-items:baseline;margin-top:9px;padding-top:8px;border-top:1px solid #e2e8f0;font-size:.8rem}
.week-activity-plan-impact span{color:#64748b;font-size:.66rem;font-weight:900;letter-spacing:.06em;text-transform:uppercase}
.week-activity-plan-impact strong{color:#0f172a}
.week-activity-evidence{margin-top:8px}
.week-activity-evidence>summary{cursor:pointer;list-style:none;color:#64748b;font-size:.75rem;font-weight:800}
.week-activity-evidence>summary::-webkit-details-marker{display:none}
.week-activity-evidence>summary:after{content:" +"}
.week-activity-evidence[open]>summary:after{content:" −"}
.week-activity-evidence-body{margin-top:8px;padding:10px 11px;border-radius:11px;background:#f8fafc;color:#475569;font-size:.76rem;line-height:1.42}
.week-activity-evidence-block+.week-activity-evidence-block{margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0}
.week-activity-evidence-block strong{display:block;margin-bottom:3px;color:#334155;font-size:.67rem;text-transform:uppercase;letter-spacing:.05em}
.week-activity-evidence-block ul{margin:0;padding-left:17px}
.week-activity-evidence-block li+li{margin-top:3px}
@media(max-width:620px){.week-activity-insight{padding:11px 12px}.week-activity-plan-impact{align-items:flex-start;flex-direction:column;gap:2px}}
""".strip()

DAY_RE = re.compile(r'<div class="day(?P<classes>[^"]*)" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">')


def load_json(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date") or ""
    return value[:10] if isinstance(value, str) and len(value) >= 10 else ""


def day_ranges(page):
    matches = list(DAY_RE.finditer(page))
    result = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
        result.append((match.start(), end, match))
    return result


def balanced_div_end(text, start):
    tag_re = re.compile(r'<div\b[^>]*>|</div>')
    depth = 0
    for match in tag_re.finditer(text, start):
        if match.group(0).startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.end()
    return None


def analysis_for(activity, coach_state):
    activity_id = activity.get("id")
    matches = [
        row for row in coach_state.get("analyses") or []
        if str(row.get("activity_id")) == str(activity_id)
    ]
    if not matches:
        return None
    return max(matches, key=lambda row: row.get("generated_at_utc") or "")


def performance_for(activity, performance_state):
    activity_id = activity.get("id")
    return next(
        (
            row for row in performance_state.get("entries") or []
            if str(row.get("activity_id")) == str(activity_id)
        ),
        None,
    )


def session_subject(day, activity):
    session = str(day.get("session") or "").lower()
    sport = str(activity.get("sport_type") or "").lower()
    if "tröskel" in session:
        return "Tröskelpasset"
    if sport == "enduro":
        return "Enduron"
    if sport == "swim":
        return "Simpasset"
    if sport in {"run", "trailrun", "virtualrun"}:
        return "Löppasset"
    if sport in {"mountainbikeride", "ride", "virtualride"}:
        return "Cykelpasset"
    if sport == "weighttraining":
        return "Styrkepasset"
    return "Passet"


def plan_impact(analysis):
    if not analysis:
        return ""
    action = (analysis.get("plan_action") or {}).get("action")
    applied = bool((analysis.get("auto_apply") or {}).get("applied"))
    if action == "keep":
        return "Ingen ändring"
    if action in {"reduce", "rest"}:
        return "Planen justerades" if applied else "Ändring rekommenderades"
    if action == "review":
        return "Fortsatt bedömning krävdes"
    return ""


def historical_insight(day, activity, analysis, performance):
    if performance:
        return build_outcome_insight(day, analysis, performance)

    subject = session_subject(day, activity)
    impact = plan_impact(analysis)
    if impact == "Ingen ändring":
        headline = f"{subject} krävde ingen planändring"
    elif impact == "Planen justerades":
        headline = f"{subject} ledde till en planjustering"
    elif impact == "Ändring rekommenderades":
        headline = f"{subject} gav skäl att rekommendera en justering"
    elif impact == "Fortsatt bedömning krävdes":
        headline = f"{subject} behövde vägas in före nästa beslut"
    else:
        headline = f"{subject} är registrerat"

    assessment = (analysis or {}).get("assessment") or {}
    interpretations = assessment.get("interpretations") or []
    body = first_sentence(interpretations[0]) if interpretations else ""
    if not body:
        body = first_sentence(assessment.get("load_interpretation"))
    if not body:
        body = first_sentence(assessment.get("summary"))
    body = re.sub(r"^Dagens tröskel\b", "Tröskelpasset", body, flags=re.IGNORECASE)
    body = re.sub(r"^Dagens\s+", "", body, flags=re.IGNORECASE)
    body = body.strip()
    return {
        "headline": headline,
        "body": body or "Registrerade passdata ger ingen ytterligare säker slutsats.",
    }


def metric_line(activity):
    values = [
        fmt_distance(activity),
        fmt_duration(activity.get("elapsed_time_s")),
    ]
    hr = fmt_hr(activity)
    if hr != "—":
        values.append(f"snittpuls {hr}")
    return " · ".join(value for value in values if value and value != "—")


def evidence_html(analysis):
    if not analysis:
        return ""
    assessment = analysis.get("assessment") or {}
    sections = [
        ("Fakta", assessment.get("facts") or []),
        ("Tolkning", assessment.get("interpretations") or []),
        ("Osäkerhet", assessment.get("unknowns") or []),
    ]
    blocks = []
    for label, items in sections:
        clean = [str(item).strip() for item in items if str(item).strip()]
        if not clean:
            continue
        lis = "".join(f"<li>{html.escape(item)}</li>" for item in clean)
        blocks.append(
            f'<div class="week-activity-evidence-block"><strong>{html.escape(label)}</strong><ul>{lis}</ul></div>'
        )
    if not blocks:
        return ""
    return (
        '<details class="week-activity-evidence"><summary>Visa underlag</summary>'
        '<div class="week-activity-evidence-body">'
        + "".join(blocks)
        + "</div></details>"
    )


def render_activity_insight(day, activity, analysis, performance):
    insight = historical_insight(day, activity, analysis, performance)
    impact = plan_impact(analysis)
    impact_html = (
        f'<div class="week-activity-plan-impact"><span>Planpåverkan</span>'
        f'<strong>{html.escape(impact)}</strong></div>'
        if impact else ""
    )
    metrics = metric_line(activity)
    metrics_html = (
        f'<div class="week-activity-metrics">{html.escape(metrics)}</div>'
        if metrics else ""
    )
    return f"""<section class="week-activity-insight" data-week-activity-insight="{html.escape(str(activity.get("id")))}">
  <div class="week-activity-insight-kicker">Passinsikt</div>
  <h3>{html.escape(insight["headline"])}</h3>
  {metrics_html}
  <p class="week-activity-insight-copy">{html.escape(insight["body"])}</p>
  {impact_html}
  {evidence_html(analysis)}
</section>"""


def add_css(page):
    page = re.sub(
        r'/\* week-activity-insight-v1 \*/.*?(?=(?:/\*|</style>))',
        "",
        page,
        flags=re.S,
    )
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Veckoinsikter: sidan saknar </style>")
    return page.replace("</style>", CSS + "\n</style>", 1)


def insertion_point(block):
    root_end = balanced_div_end(block, 0)
    if root_end is None:
        raise RuntimeError("Veckoinsikter: kunde inte avgränsa dagkort")
    closing = block.rfind("</div>", 0, root_end)
    if closing < 0:
        raise RuntimeError("Veckoinsikter: dagkort saknar avslutande div")
    return closing


def apply_week_activity_insights(page, plan, activities_state, coach_state, performance_state, today):
    week_start = str((plan.get("meta") or {}).get("week_start") or "")
    week_end = str((plan.get("meta") or {}).get("week_end") or "")
    days_by_date = {day.get("date"): day for day in plan.get("days") or []}

    activities = [
        activity for activity in activities_state.get("activities") or []
        if week_start <= local_date(activity) <= week_end and local_date(activity) < today
    ]
    if not activities:
        return page

    page = add_css(page)
    grouped = {}
    for activity in activities:
        grouped.setdefault(local_date(activity), []).append(activity)

    for start, end, match in reversed(day_ranges(page)):
        day_text = match.group("date")
        day_activities = grouped.get(day_text) or []
        if not day_activities:
            continue
        day = days_by_date.get(day_text) or {"date": day_text}
        block = page[start:end]

        cards = []
        for activity in sorted(day_activities, key=lambda row: row.get("start_date_local") or row.get("start_date") or ""):
            marker = f'{CARD_MARKER}{html.escape(str(activity.get("id")))}"'
            if marker in block:
                continue
            cards.append(
                render_activity_insight(
                    day,
                    activity,
                    analysis_for(activity, coach_state),
                    performance_for(activity, performance_state),
                )
            )
        if not cards:
            continue
        point = insertion_point(block)
        block = block[:point] + "".join(cards) + block[point:]
        page = page[:start] + block + page[end:]

    return page


def main():
    plan = load_json(PLAN_FILE, {})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    coach = load_json(COACH_FILE, {"analyses": []})
    performance = load_json(PERFORMANCE_FILE, {"entries": []})
    page = INDEX_FILE.read_text(encoding="utf-8")
    tz = ZoneInfo((plan.get("meta") or {}).get("timezone") or "Europe/Stockholm")
    today = datetime.now(tz).date().isoformat()

    rendered = apply_week_activity_insights(page, plan, activities, coach, performance, today)
    INDEX_FILE.write_text(rendered, encoding="utf-8")

    expected = [
        activity for activity in activities.get("activities") or []
        if str((plan.get("meta") or {}).get("week_start") or "") <= local_date(activity)
        <= str((plan.get("meta") or {}).get("week_end") or "")
        and local_date(activity) < today
    ]
    verify = INDEX_FILE.read_text(encoding="utf-8")
    missing = [
        str(activity.get("id")) for activity in expected
        if f'{CARD_MARKER}{html.escape(str(activity.get("id")))}"' not in verify
    ]
    if missing:
        raise RuntimeError("Veckoinsikter: saknar retroaktiv passinsikt för " + repr(missing))
    if expected and CSS_MARKER not in verify:
        raise RuntimeError("Veckoinsikter: CSS saknas")
    if 'class="historical-coach"' in verify:
        raise RuntimeError("Veckoinsikter: gammal rå AI-historik exponeras fortfarande")
    print(f"Veckoinsikter OK: {len(expected)} tidigare aktiviteter visar kompakt passinsikt.")


if __name__ == "__main__":
    main()
