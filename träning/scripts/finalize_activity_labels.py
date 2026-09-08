#!/usr/bin/env python3
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
INDEX_FILE = ROOT / "index.html"

# Public UI labels for raw provider activity types. A semantic display_label on
# the normalized activity always wins; this table is the safe fallback when the
# activity does not need a more specific label.
PUBLIC_ACTIVITY_LABELS = {
    "Run": "Löpning",
    "TrailRun": "Löpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "Swimrun": "Swimrun",
    "MountainBikeRide": "MTB/XC",
    "EMountainBikeRide": "MTB/XC",
    "Ride": "Cykel",
    "VirtualRide": "Cykel",
    "WeightTraining": "Styrka",
    "Enduro": "Enduro",
}


def fmt_duration(sec):
    if sec is None:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_activity(activity):
    bits = []
    if activity.get("distance_m"):
        bits.append(f'{activity["distance_m"] / 1000:.2f} km'.replace(".", ","))
    if activity.get("elapsed_time_s"):
        bits.append(fmt_duration(activity["elapsed_time_s"]))
    if activity.get("average_heartrate"):
        bits.append(f'snittpuls {round(activity["average_heartrate"])}')
    if activity.get("max_heartrate"):
        bits.append(f'max {round(activity["max_heartrate"])}')
    return " · ".join(bits)


def public_activity_label(activity):
    raw_label = str(activity.get("sport_type") or "Aktivitet").strip() or "Aktivitet"
    semantic_label = str(activity.get("display_label") or "").strip()
    if semantic_label:
        return semantic_label
    return PUBLIC_ACTIVITY_LABELS.get(raw_label, raw_label)


def render_activity_line(activity, label=None):
    label = label or activity.get("sport_type") or "Aktivitet"
    return (
        f'<div><strong>{html.escape(label)}</strong> · '
        f'{html.escape(fmt_activity(activity))}</div>'
    )


def local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date") or ""
    return value[:10] if len(value) >= 10 else ""


def main():
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
    page = INDEX_FILE.read_text(encoding="utf-8")

    week_start = plan["meta"]["week_start"]
    week_end = plan["meta"]["week_end"]
    expected = []
    replacements = 0

    for activity in state.get("activities", []):
        date = local_date(activity)
        if not date or not (week_start <= date <= week_end):
            continue

        raw_label = str(activity.get("sport_type") or "Aktivitet").strip() or "Aktivitet"
        display_label = public_activity_label(activity)
        if display_label == raw_label:
            continue

        raw_line = render_activity_line(activity, raw_label)
        normalized_line = render_activity_line(activity, display_label)
        expected.append((activity.get("id"), raw_label, display_label, normalized_line))

        if normalized_line in page:
            continue
        if raw_line not in page:
            raise RuntimeError(
                f"Aktivitetsetikett: kunde inte hitta genererad rad för aktivitet {activity.get('id')}"
            )
        page = page.replace(raw_line, normalized_line, 1)
        replacements += 1

    INDEX_FILE.write_text(page, encoding="utf-8")
    rendered = INDEX_FILE.read_text(encoding="utf-8")

    for activity_id, raw_label, display_label, normalized_line in expected:
        if normalized_line not in rendered:
            raise RuntimeError(
                f"Aktivitetsetikett: normaliserad etikett {display_label!r} saknas för {activity_id}"
            )
        raw_token = f"<strong>{html.escape(raw_label)}</strong>"
        if raw_token in rendered and raw_label in PUBLIC_ACTIVITY_LABELS:
            raise RuntimeError(
                f"Aktivitetsetikett: rå leverantörstyp {raw_label!r} finns kvar i synlig UI"
            )

    print(
        f"Aktivitetsetiketter OK: {len(expected)} normaliserade rad(er), "
        f"{replacements} ersättning(ar)."
    )


if __name__ == "__main__":
    main()
