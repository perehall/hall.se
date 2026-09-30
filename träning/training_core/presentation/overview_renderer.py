"""Pure renderer for the multi-week training overview."""

from __future__ import annotations

import html
import re
from datetime import date

from training_core.presentation.overview import TrainingOverviewReadModel
from training_core.repositories.icons import SportIconRegistry
from training_core.presentation.sport_identity import sport_icon_key


WEEKDAY_SHORT = ("Mån", "Tis", "Ons", "Tor", "Fre", "Lör", "Sön")
MONTH_SHORT = (
    "jan", "feb", "mar", "apr", "maj", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
)

INTENT_LABELS = {
    "establish": "Etablera",
    "develop": "Utveckla",
    "consolidate": "Konsolidera",
    "review": "Utvärdera",
    "conditional_build": "Villkorat bygge",
}
AXIS_LABELS = {
    "work_duration": "arbetstid",
    "repetitions": "repetitioner",
    "session_duration": "passlängd",
    "frequency": "frekvens",
    "technical_quality": "teknisk kvalitet",
    "consistency": "kontinuitet",
}
PROGRESSION_INTENT_LABELS = {
    "establish": "Etablera",
    "vary_structure": "Variera passkaraktär",
    "progress_if_ready": "Planerad progression om responsen stödjer",
    "consolidate": "Konsolidera",
    "protect": "Skyddad kapacitet",
    "support_if_absorbable": "Stöd om belastningen tillåter",
    "fixed_external_load": "Fast extern belastning",
}


def _e(value: object) -> str:
    return html.escape(str(value or ""))


def _fmt_date(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return f"{parsed.day} {MONTH_SHORT[parsed.month - 1]} {parsed.year}"



SESSION_INTERVAL_RE = re.compile(r"(?P<count>\d+)\s*[×x]\s*(?P<minutes>\d+(?:[.,]\d+)?)\s*min", re.IGNORECASE)
DISTANCE_RE = re.compile(r"(?P<distance>\d[\d ]{2,})\s*m\b", re.IGNORECASE)
DURATION_RE = re.compile(r"(?P<minutes>\d{2,3})\s*min\b", re.IGNORECASE)
HILL_RE = re.compile(r"(?:(?P<sets>\d+)\s*[×x]\s*)?(?P<reps>\d+)\s*[×x]\s*150\s*m", re.IGNORECASE)

ROLE_LABELS = {
    "primary": "Primärt utvecklingspass",
    "anchor": "Primärt utvecklingspass",
    "support": "Stödpass",
    "supporting_candidate": "Stödpass",
    "protected": "Skyddad kapacitet",
    "protected_support": "Skyddad kapacitet",
    "external_fixed": "Fast extern belastning",
}


def _trim(value: str, limit: int = 76) -> str:
    value = " ".join(str(value or "").split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def _first_distance(value: str) -> str:
    match = DISTANCE_RE.search(str(value or ""))
    return match.group("distance").replace(" ", "") if match else ""


def _first_duration(value: str) -> str:
    match = DURATION_RE.search(str(value or ""))
    return match.group("minutes") if match else ""


def _short_workout_title(session: str, recipe_key: str = "", sport: str = "", fallback: str = "") -> str:
    raw = " ".join(str(session or fallback or "").split())
    key = str(recipe_key or "").strip()
    distance = _first_distance(raw)
    duration = _first_duration(raw)
    interval = SESSION_INTERVAL_RE.search(raw)
    hill = HILL_RE.search(raw)

    if key in {"run_threshold", "run_threshold_short_reps"} or ("trösk" in raw.lower() and interval):
        if interval:
            count = interval.group("count")
            minutes = interval.group("minutes").replace(",", ".")
            return f"Tröskel · {count}×{minutes}"
        return "Tröskel"

    if key in {"run_hill_quality", "run_hill_continuous"} or "back" in raw.lower():
        if hill:
            sets = hill.group("sets")
            reps = hill.group("reps")
            return f"Backe · {sets + '×' if sets else ''}{reps}×150"
        return "Backe"

    if key == "run_easy_trail" or ("stig" in raw.lower() and str(sport).lower() == "run"):
        return f"Lugn stig · {duration} min" if duration else "Lugn stig"

    if key == "run_easy_distance":
        return f"Lugn distans · {duration} min" if duration else "Lugn distans"

    if key == "swim_aerobic_endurance":
        return f"Aerob sim · {distance}" if distance else "Aerob sim"
    if key == "swim_aerobic_skills":
        return f"Grepp + aerob · {distance}" if distance else "Grepp + aerob"
    if key == "swim_aerobic_technique":
        return f"Aerob + teknik · {distance}" if distance else "Aerob + teknik"
    if key == "swim_aerobic_threshold":
        return f"Simtröskel · {distance}" if distance else "Simtröskel"

    if key == "mtb_technical":
        return f"MTB teknik · {duration} min" if duration else "MTB teknik"
    if key == "mtb_aerobic_endurance":
        return f"MTB aerob · {duration} min" if duration else "MTB aerob"

    if key == "strength_core" or str(sport).lower() == "strength":
        return f"Styrka + core · {duration} min" if duration else "Styrka + core"

    if str(sport).lower() == "enduro" or "enduro" in raw.lower():
        return "Enduro"

    cleaned = raw
    for prefix in ("Löpning · ", "Simning · ", "MTB/XC · ", "Styrka/core · "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return _trim(cleaned or str(fallback or sport or "Pass"), 34)


def _short_character(value: str) -> str:
    raw = " ".join(str(value or "").split())
    replacements = (
        ("Löptröskel · längre repetitioner", "Tröskel · längre rep"),
        ("Löptröskel · kortare repetitioner", "Tröskel · kortare rep"),
        ("Sim · aerob uthållighet", "Aerob sim"),
        ("Sim · aerob teknik", "Aerob + teknik"),
        ("Sim · grepp/teknik + aerob", "Grepp + aerob"),
        ("Backkvalitet · klustrade 150 m-reps", "Backe · klustrade reps"),
        ("Backkvalitet · sammanhängande 150 m-reps", "Backe · sammanhängande"),
        ("Lugn löpdistans · jämn", "Lugn distans"),
        ("Lugn löpdistans · stig/grus", "Lugn stig/grus"),
        ("MTB/XC · teknik och flyt", "MTB teknik/flyt"),
        ("MTB/XC · aerob uthållighet", "MTB aerob"),
        ("Styrka/core · unilateral + bål", "Styrka + core"),
    )
    for source, target in replacements:
        if raw == source:
            return target
    return _trim(raw, 30)


def _progress_chip(intent: str = "", relation: str = "", state: str = "", role: str = "") -> tuple[str, str]:
    if state == "fixed" or intent == "fixed_external_load" or role == "external_fixed":
        return "Låst", "fixed"
    mapping = {
        "progress_if_ready": ("↑ Progression", "progress"),
        "vary_structure": ("~ Variation", "variation"),
        "consolidate": ("= Konsolidera", "consolidate"),
        "establish": ("• Etablera", "establish"),
        "support_if_absorbable": ("◇ Stöd", "support"),
        "protect": ("◇ Skyddad", "protected"),
    }
    if intent in mapping:
        return mapping[intent]
    if relation == "progress":
        return "↑ Progression", "progress"
    if relation == "establish":
        return "• Etablera", "establish"
    if role in {"support", "supporting_candidate"}:
        return "◇ Stöd", "support"
    if role in {"protected", "protected_support"}:
        return "◇ Skyddad", "protected"
    return "", ""


def _detail_button_attrs(**values) -> str:
    attrs = ['type="button"', 'data-overview-detail="1"']
    for key, value in values.items():
        if value is None or str(value).strip() == "":
            continue
        attr = "data-" + key.replace("_", "-")
        attrs.append(f'{attr}="{_e(value)}"')
    return " ".join(attrs)


def _expected_intent(model: TrainingOverviewReadModel, week_start: date):
    block = model.context.active_block if model.context else None
    if block is None:
        return None
    for item in block.microcycle_intents:
        if item.start_date == week_start.isoformat():
            return item
    return None


def _intent_label(value: str) -> str:
    return INTENT_LABELS.get(str(value or "").strip(), str(value or "").strip())


def _expected_blueprint(model: TrainingOverviewReadModel, week_start: date):
    block = model.context.active_block if model.context else None
    if block is None:
        return None
    for item in block.development_blueprint:
        if item.start_date == week_start.isoformat():
            return item
    return None


def _expected_forward_week(model: TrainingOverviewReadModel, week_start: date):
    block = model.context.active_block if model.context else None
    if block is None:
        return None
    for item in block.forward_horizon:
        if item.start_date == week_start.isoformat():
            return item
    return None


def _forward_preliminary_html(forward, week_start: date, registry: SportIconRegistry | None) -> str:
    by_day = {}
    for slot in forward.slots:
        by_day.setdefault(slot.day_index, []).append(slot)

    cells = []
    for day_index in range(1, 8):
        local_date = week_start.fromordinal(week_start.toordinal() + day_index - 1)
        cards = []
        for slot in by_day.get(day_index, ()):
            full_session = slot.baseline_session or slot.label
            title = _short_workout_title(
                full_session,
                slot.recipe_key,
                slot.sport,
                slot.label,
            )
            chip, chip_class = _progress_chip(
                intent=slot.progression_intent,
                role=slot.role,
            )
            chip_html = (
                f'<span class="overview-pass-chip chip-{_e(chip_class)}">{_e(chip)}</span>'
                if chip else ""
            )
            role = ROLE_LABELS.get(slot.role, slot.role)
            attrs = _detail_button_attrs(
                title=title,
                full_session=full_session,
                role=role,
                status=forward.planning_label,
                development=PROGRESSION_INTENT_LABELS.get(
                    slot.progression_intent,
                    slot.progression_intent,
                ),
                baseline=slot.baseline_session,
                target=slot.conditional_target_session,
                why=forward.decision_gate,
            )
            icon_key = sport_icon_key(slot.sport)
            icon_html = _icon(registry, icon_key) if icon_key else ""
            cards.append(
                f'<button class="overview-workout planned preliminary" {attrs}>'
                f'{icon_html}'
                '<span class="overview-workout-copy">'
                f'<strong>{_e(title)}</strong>{chip_html}'
                '</span></button>'
            )
        body = "".join(cards) or '<span class="overview-forward-open">Öppen</span>'
        cells.append(
            '<div class="overview-day forward-preliminary">'
            '<div class="overview-day-head">'
            f'<span>{WEEKDAY_SHORT[day_index - 1]}</span><b>{local_date.day}</b>'
            '</div>'
            f'<div class="overview-day-body">{body}</div>'
            '</div>'
        )
    return "".join(cells)


def _forward_block_sketch_html(forward) -> str:
    primary_labels = [
        item.capability_label for item in forward.capability_directions
        if item.capability_label
    ]
    characters = []
    for item in forward.capability_directions:
        for value in item.candidate_recipe_characters:
            short = _short_character(value)
            if short and short not in characters:
                characters.append(short)

    support_labels = [
        item.capability_label for item in forward.support_candidates
        if item.capability_label
    ]
    protected_labels = list(dict.fromkeys(forward.protected_capabilities))

    def chips(values, kind):
        return "".join(
            f'<span class="overview-sketch-chip sketch-{kind}">{_e(value)}</span>'
            for value in values
        )

    groups = []
    if primary_labels:
        groups.append(
            '<div class="overview-sketch-group"><span>Primärt</span>'
            f'<div>{chips(primary_labels, "primary")}</div></div>'
        )
    if characters:
        groups.append(
            '<div class="overview-sketch-group"><span>Passkaraktärer</span>'
            f'<div>{chips(characters[:6], "character")}</div></div>'
        )
    if support_labels:
        groups.append(
            '<div class="overview-sketch-group"><span>Stöd</span>'
            f'<div>{chips(support_labels, "support")}</div></div>'
        )
    if protected_labels:
        groups.append(
            '<div class="overview-sketch-group"><span>Skyddas</span>'
            f'<div>{chips(protected_labels, "protected")}</div></div>'
        )

    title = (
        "Blockreview"
        if forward.block_intent == "review"
        else "Nästa block"
    )
    return (
        '<div class="overview-forward-sketch">'
        '<div class="overview-sketch-heading">'
        f'<strong>{_e(title)}</strong>'
        f'<span>{_e(forward.planning_label)}</span>'
        '</div>'
        f'<div class="overview-sketch-groups">{"".join(groups)}</div>'
        '</div>'
    )


def _blueprint_html(blueprint) -> str:
    if blueprint is None:
        return '<div class="overview-blueprint-empty">Grundplan saknas.</div>'

    def card(item, extra_class=""):
        intent = PROGRESSION_INTENT_LABELS.get(
            item.progression_intent,
            item.progression_intent,
        )
        baseline = (
            f'<small><b>Bas:</b> {_e(item.baseline_session)}</small>'
            if item.baseline_session else ""
        )
        target = (
            f'<small class="overview-target"><b>Villkorat mål:</b> '
            f'{_e(item.conditional_target_session)}</small>'
            if item.conditional_target_session else ""
        )
        return (
            f'<article class="overview-blueprint-card {extra_class}">'
            f'<strong>{_e(item.label)}</strong>'
            f'<span>{_e(intent)}</span>'
            f'{baseline}{target}'
            '</article>'
        )

    primary = "".join(card(item) for item in blueprint.planned_variants)
    protected = "".join(
        card(item, "protected")
        for item in blueprint.protected_variants
    )
    support = "".join(
        card(item, "support")
        for item in blueprint.supporting_candidates
    )
    return (
        '<div class="overview-week-blueprint">'
        '<div class="overview-blueprint-head">'
        '<span>Preliminär grundplan</span>'
        '<small>Passkaraktär och progression är planerade. Exakt dag och dos materialiseras senare.</small>'
        '</div>'
        f'<div class="overview-blueprint-primary">{primary}</div>'
        + (
            '<div class="overview-blueprint-secondary">'
            f'{protected}{support}</div>'
            if protected or support else ""
        )
        + '</div>'
    )


def _week_url(week_start: date, current_week_start: date) -> str:
    if week_start == current_week_start:
        return "/träning/"
    year, week, _ = week_start.isocalendar()
    return f"/träning/vecka/{year}-W{week:02d}/"


def _icon(registry: SportIconRegistry | None, key: str) -> str:
    if registry is None:
        return ""
    icon = registry.require(key)
    key_escaped = _e(icon.key)
    if icon.solid:
        return (
            f'<svg class="overview-icon icon-{key_escaped}" aria-hidden="true" '
            f'viewBox="{_e(icon.view_box)}" fill="currentColor" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{_e(icon.path)}"/></svg>'
        )
    return (
        f'<svg class="overview-icon icon-{key_escaped}" aria-hidden="true" '
        f'viewBox="{_e(icon.view_box)}" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{_e(icon.path)}"/></svg>'
    )


def _icon_group(registry: SportIconRegistry | None, keys: tuple[str, ...]) -> str:
    if not keys:
        return ""
    return '<span class="overview-icons">' + "".join(_icon(registry, key) for key in keys) + "</span>"


def _context_html(model: TrainingOverviewReadModel) -> str:
    context = model.context
    if context is None:
        return (
            '<section class="overview-context unavailable">'
            '<div><span>Utvecklingsblock</span><strong>Kontext saknas</strong></div>'
            '<p>Mål- och blockkopplingen kunde inte byggas från nuvarande planeringsdata.</p>'
            '</section>'
        )

    block = context.active_block
    block_html = ""
    if block is not None:
        primary = " · ".join(block.primary_capabilities) or "Ej specificerat"
        dates = " – ".join(
            value for value in (_fmt_date(block.start_date), _fmt_date(block.end_date)) if value
        )
        checkpoint = _fmt_date(block.evaluation_date)
        axes = " · ".join(
            f"{axis.capability_label}: {AXIS_LABELS.get(axis.axis, axis.axis)}"
            for axis in block.progression_axes
            if axis.capability_label and axis.axis
        )
        wave = "".join(
            '<div class="overview-wave-step'
            + (' current' if item.start_date == model.current_week_start.isoformat() else '')
            + '">'
            f'<b>V{item.index}</b><span>{_e(_intent_label(item.intent))}</span>'
            '</div>'
            for item in block.microcycle_intents
        )
        block_html = (
            '<div class="overview-context-block">'
            '<span>Aktuellt utvecklingsblock</span>'
            f'<strong>{_e(block.title or "Aktivt block")}</strong>'
            f'<small>{_e(dates)}</small>'
            f'<p><b>Primärt nu:</b> {_e(primary)}</p>'
            + (f'<p><b>Progressionsaxlar:</b> {_e(axes)}</p>' if axes else "")
            + (f'<div class="overview-block-wave">{wave}</div>' if wave else "")
            + (f'<p><b>Nästa checkpoint:</b> {_e(checkpoint)}</p>' if checkpoint else "")
            + '</div>'
        )

    goals = []
    for goal in context.goals[:3]:
        meta = " · ".join(value for value in (goal.target, _fmt_date(goal.target_date)) if value)
        goals.append(
            '<article class="overview-goal">'
            f'<strong>{_e(goal.label)}</strong>'
            + (f'<span>{_e(meta)}</span>' if meta else "")
            + '</article>'
        )
    goals_html = "".join(goals) or '<p class="overview-empty">Inga kanoniska mål publicerade.</p>'

    return (
        '<section class="overview-context">'
        f'{block_html}'
        '<div class="overview-context-goals"><span>Mot mål</span>'
        f'<div>{goals_html}</div></div>'
        '</section>'
    )


def _planned_item(workout, registry: SportIconRegistry | None) -> str:
    focus = (
        f'<span class="overview-focus">{_e(workout.development_focus)}</span>'
        if workout.development_focus else ""
    )
    return (
        f'<div class="overview-workout planned state-{_e(workout.state)}" '
        f'data-workout-key="{_e(workout.workout_key)}">'
        f'{_icon_group(registry, workout.icon_keys)}'
        f'<span class="overview-workout-copy"><strong>{_e(workout.session)}</strong>{focus}</span>'
        '</div>'
    )


def _actual_item(activity, registry: SportIconRegistry | None) -> str:
    facts = []
    if activity.distance_m > 0:
        facts.append(activity.distance)
    if activity.duration_s > 0:
        facts.append(activity.duration)
    detail = " · ".join(facts)
    return (
        '<div class="overview-workout actual">'
        f'{_icon(registry, activity.icon_key)}'
        f'<span class="overview-workout-copy"><strong>{_e(activity.label)}</strong>'
        + (f'<span class="overview-facts">{_e(detail)}</span>' if detail else "")
        + '</span></div>'
    )


def _day_html(
    day,
    *,
    current_date: date,
    registry: SportIconRegistry | None,
    materialized: bool,
) -> str:
    classes = ["overview-day", f"state-{day.state}"]
    if day.local_date == current_date:
        classes.append("today")
    actual = "".join(_actual_item(item, registry) for item in day.actual_activities)
    planned = "".join(_planned_item(item, registry) for item in day.planned_workouts)

    if actual and planned:
        body = (
            f'<div class="overview-layer actual-layer">{actual}</div>'
            '<div class="overview-plan-label">Plan</div>'
            f'<div class="overview-layer planned-layer">{planned}</div>'
        )
    elif actual:
        body = f'<div class="overview-layer actual-layer">{actual}</div>'
    elif planned:
        body = f'<div class="overview-layer planned-layer">{planned}</div>'
    else:
        body = (
            '<span class="overview-rest">Vila</span>'
            if materialized or day.local_date <= current_date
            else '<span class="overview-unplanned">Ej detaljplanerad</span>'
        )

    return (
        f'<div class="{" ".join(classes)}" data-date="{day.local_date.isoformat()}">'
        '<div class="overview-day-head">'
        f'<span>{WEEKDAY_SHORT[day.local_date.weekday()]}</span>'
        f'<b>{day.local_date.day}</b>'
        '</div>'
        f'<div class="overview-day-body">{body}</div>'
        '</div>'
    )


def _week_html(
    week,
    *,
    model: TrainingOverviewReadModel,
    current_date: date,
    current_week_start: date,
    registry: SportIconRegistry | None,
) -> str:
    relation = (
        "current" if week.start == current_week_start
        else "past" if week.end < current_date
        else "future"
    )
    expected = _expected_intent(model, week.start)
    materialized = week.planned_count > 0 or relation != "future"
    rest_days = max(0, 7 - week.planned_training_days)
    blueprint = _expected_blueprint(model, week.start)
    forward = _expected_forward_week(model, week.start)
    if relation == "future" and week.planned_count == 0:
        if forward is not None and forward.planning_level == "preliminary":
            metrics = ["Preliminär dagstruktur · exakta dagar/doser ej låsta"]
        elif forward is not None and forward.planning_level == "block_sketch":
            metrics = ["Blockskiss · nästa beslut tas vid checkpoint"]
        elif blueprint is not None:
            metrics = ["Grundplan finns · detaljdagar ej materialiserade"]
        else:
            metrics = ["Planeringsunderlag saknas"]
    else:
        metrics = [
            f"Plan {week.planned_count} pass",
            f"Utfört {week.completed_count}",
        ]
        if week.completed_count:
            metrics.append(week.actual_duration)
            if week.actual_distance_m > 0:
                metrics.append(week.actual_distance)
        if relation != "past":
            metrics.append(f"{rest_days} planerade vilodagar")
    metric_text = " · ".join(metrics)

    observed_intent = week.block_intents[0] if len(week.block_intents) == 1 else ""
    intent = observed_intent or (expected.intent if expected else "") or (
        forward.block_intent if forward is not None else ""
    )
    progress_bits = []
    if week.primary_progress_count:
        progress_bits.append(f"{week.primary_progress_count} primär progression")
    if week.primary_hold_count:
        progress_bits.append(f"{week.primary_hold_count} primär hold")
    if week.primary_establish_count:
        progress_bits.append(f"{week.primary_establish_count} etablering")
    intent_meta = " · ".join(progress_bits)
    intent_html = (
        '<div class="overview-week-intent">'
        f'<strong>{_e(_intent_label(intent))}</strong>'
        + (f'<span>{_e(intent_meta)}</span>' if intent_meta else "")
        + '</div>'
        if intent else ""
    )
    if relation == "future" and week.planned_count == 0 and forward is not None:
        if forward.planning_level == "preliminary":
            days = _forward_preliminary_html(forward, week.start)
            display_mode = "forward-preliminary-mode"
        else:
            days = _forward_block_sketch_html(forward)
            display_mode = "blueprint-mode"
    elif relation == "future" and week.planned_count == 0 and blueprint is not None:
        days = _blueprint_html(blueprint)
        display_mode = "blueprint-mode"
    else:
        days = "".join(
            _day_html(
                day,
                current_date=current_date,
                registry=registry,
                materialized=materialized,
            )
            for day in week.days
        )
        display_mode = ""

    commitment = (
        "Planerad"
        if relation == "future" and week.planned_count > 0
        else forward.planning_label
        if relation == "future" and forward is not None
        else ""
    )
    commitment_html = (
        f'<span class="overview-commitment level-{_e((forward.planning_level if forward else "planned"))}">'
        f'{_e(commitment)}</span>'
        if commitment else ""
    )
    week_heading = (
        f'<strong>V{week.week_number}</strong>{commitment_html}'
        f'<span>{week.start.day} {MONTH_SHORT[week.start.month - 1]} – '
        f'{week.end.day} {MONTH_SHORT[week.end.month - 1]}</span>'
    )
    if relation != "future" or week.planned_count > 0:
        week_heading = (
            f'<a href="{_week_url(week.start, current_week_start)}">'
            f'{week_heading}</a>'
        )
    else:
        week_heading = f'<div class="overview-week-label">{week_heading}</div>'

    return (
        f'<section class="overview-week relation-{relation}" data-week="{_e(week.iso_key)}">'
        '<header class="overview-week-summary">'
        f'{week_heading}'
        f'<p>{_e(metric_text)}</p>'
        f'{intent_html}'
        '</header>'
        f'<div class="overview-week-days {display_mode}">{days}</div>'
        '</section>'
    )


def _review_html(model: TrainingOverviewReadModel) -> str:
    future_weeks = [week for week in model.weeks if week.start > model.current_week_start]
    block = model.context.active_block if model.context else None
    active_future = [
        week for week in future_weeks
        if _expected_intent(model, week.start) is not None
    ]
    materialized_active = [week for week in active_future if week.planned_count > 0]
    missing_active = [week for week in active_future if week.planned_count == 0]

    visible_future = [
        week for week in future_weeks[:5]
    ]
    horizon_coverage = [
        week
        for week in visible_future
        if week.planned_count > 0
        or _expected_forward_week(model, week.start) is not None
        or _expected_blueprint(model, week.start) is not None
    ]
    horizon_levels = []
    for week in visible_future:
        if week.planned_count > 0:
            horizon_levels.append(f"V{week.week_number} Planerad")
            continue
        forward = _expected_forward_week(model, week.start)
        if forward is not None:
            horizon_levels.append(
                f"V{week.week_number} {forward.planning_label}"
            )
        elif _expected_blueprint(model, week.start) is not None:
            horizon_levels.append(f"V{week.week_number} Preliminär")
        else:
            horizon_levels.append(f"V{week.week_number} saknas")

    multipass_days = [
        day
        for week in model.weeks
        for day in week.days
        if day.planned_count > 1
    ]
    fixed_count = sum(week.fixed_count for week in model.weeks)

    rhythm_mismatches = []
    progression_issues = []
    primary_coverage_issues = []
    progression_notes = []
    for week in materialized_active:
        expected = _expected_intent(model, week.start)
        observed = set(week.block_intents)
        if expected and observed and observed != {expected.intent}:
            rhythm_mismatches.append(
                f"V{week.week_number}: väntat {_intent_label(expected.intent)}, "
                f"materialiserat {', '.join(_intent_label(value) for value in sorted(observed))}"
            )
        elif expected and not observed:
            rhythm_mismatches.append(
                f"V{week.week_number}: block_intent saknas i materialiserade pass"
            )

        if expected and expected.intent == "develop":
            anchors = week.primary_workouts
            if week.primary_progress_count:
                progression_notes.append(
                    f"V{week.week_number}: {week.primary_progress_count} primär progression"
                )
            elif anchors:
                explicit_holds = [
                    workout for workout in anchors
                    if workout.development_relation in {"hold", "establish"}
                    and workout.development_reason
                ]
                if len(explicit_holds) == len(anchors):
                    progression_notes.append(
                        f"V{week.week_number}: primära pass hålls/etableras med explicit skäl"
                    )
                else:
                    progression_issues.append(
                        f"V{week.week_number}: develop-vecka saknar både primär progression och fullständig hold-motivering"
                    )
            else:
                progression_issues.append(
                    f"V{week.week_number}: develop-vecka saknar materialiserat primärt utvecklingspass"
                )

        if block is not None:
            planned_stimuli = {
                stimulus
                for workout in week.planned_workouts
                for stimulus in workout.stimuli
            }
            missing_primary = [
                key for key in block.primary_capability_keys
                if key not in planned_stimuli
            ]
            if missing_primary:
                primary_coverage_issues.append(
                    f"V{week.week_number}: saknar {', '.join(missing_primary)}"
                )

    rows = [
        (
            "Planeringshorisont",
            (
                f"{len(horizon_coverage)} av {len(visible_future)} kommande veckor har "
                "planeringsinnehåll: " + " · ".join(horizon_levels)
                if visible_future
                else "Ingen framtidsvecka finns i den synliga perioden."
            ),
            "attention" if len(horizon_coverage) != len(visible_future) else "neutral",
        ),
        (
            "Blockrytm",
            (
                "Materialiserade mikrocykler följer blockets etablera/utveckla/konsolidera-roll."
                if not rhythm_mismatches
                else " · ".join(rhythm_mismatches)
            ),
            "ok" if not rhythm_mismatches else "attention",
        ),
        (
            "Progressionslogik",
            (
                " · ".join(progression_notes)
                if progression_notes and not progression_issues
                else " · ".join(progression_issues or ["Ingen framtida develop-mikrocykel är ännu materialiserad."])
            ),
            "attention" if progression_issues else "neutral",
        ),
        (
            "Primär täckning",
            (
                "Alla materialiserade framtidsveckor i blocket täcker blockets primära kapaciteter."
                if not primary_coverage_issues
                else " · ".join(primary_coverage_issues)
            ),
            "ok" if not primary_coverage_issues else "attention",
        ),
        (
            "Multipass",
            f"{len(multipass_days)} dagar innehåller fler än ett självständigt planerat pass.",
            "neutral",
        ),
        (
            "Fasta pass",
            f"{fixed_count} pass är markerade som fasta i den synliga perioden.",
            "neutral",
        ),
    ]
    if missing_active:
        labels = ", ".join(f"V{week.week_number}" for week in missing_active)
        rows.append(
            (
                "Ej detaljplanerad",
                f"{labels} ligger i det beslutade blocket men saknar ännu materialiserade pass. "
                "De visas därför inte som viloveckor.",
                "neutral",
            )
        )

    content = "".join(
        f'<article class="overview-review-item {state}"><span>{_e(label)}</span>'
        f'<p>{_e(copy)}</p></article>'
        for label, copy, state in rows
    )
    return (
        '<details class="overview-review">'
        '<summary>Granska plan</summary>'
        '<div class="overview-review-copy">'
        '<p>Kontrollen jämför den materialiserade kalendern mot mesocykelns egna strukturerade beslut: '
        'blockroll, primära stimuli och explicit progress/hold. Den sätter inget fysiologiskt totalscore.</p>'
        f'<div class="overview-review-grid">{content}</div></div></details>'
    )


OVERVIEW_CSS = r"""
:root{
  color-scheme:light;
  --bg:#F6F7F5;--card:#FCFCFB;--elevated:#FFFFFF;
  --text:#171918;--secondary:#5E6661;--muted:#737A75;
  --line:#E2E6E1;--line-soft:#ECEFEB;--accent:#5964E8;
  --accent-soft:#F1F2FD;--green:#287A54;--green-soft:#EDF7F1;
  --amber:#8A6418;--amber-soft:#FBF6E7;
  font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif
}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);line-height:1.4}
a{color:inherit}.overview-shell{width:min(1500px,100%);margin:auto;padding:24px 18px 72px}
.overview-topnav{display:flex;justify-content:flex-end;gap:18px;margin-bottom:38px;font-size:.78rem}
.overview-topnav a{color:var(--muted);text-decoration:none}.overview-topnav a.active{color:var(--text);font-weight:720}
.overview-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin:0 0 22px}
.overview-kicker{font-size:.67rem;text-transform:uppercase;letter-spacing:.08em;font-weight:800;color:var(--muted)}
.overview-hero h1{font-size:clamp(2rem,4vw,3.4rem);letter-spacing:-.05em;line-height:1;margin:7px 0 8px}
.overview-hero p{margin:0;color:var(--secondary);max-width:760px}.overview-range{color:var(--muted);font-size:.76rem;white-space:nowrap}
.overview-context{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:12px;margin-bottom:18px}
.overview-context>div{border:1px solid var(--line);background:var(--card);border-radius:16px;padding:15px 17px}
.overview-context span{display:block;color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;font-weight:760}
.overview-context strong{display:block;margin-top:5px;font-size:.98rem}.overview-context small{display:block;color:var(--muted);font-size:.72rem;margin-top:3px}
.overview-context p{margin:9px 0 0;color:var(--secondary);font-size:.78rem}
.overview-context p+p{margin-top:4px}.overview-context-goals>div{display:grid;gap:7px;margin-top:8px}
.overview-block-wave{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin-top:11px}
.overview-wave-step{padding:7px 6px;border:1px solid var(--line-soft);border-radius:9px;background:var(--elevated)}
.overview-wave-step.current{border-color:#c9cdf8;background:var(--accent-soft)}
.overview-wave-step b{display:block;font-size:.64rem}.overview-wave-step span{margin-top:2px;font-size:.58rem;text-transform:none;letter-spacing:0}
.overview-goal{padding:8px 0;border-top:1px solid var(--line-soft)}.overview-goal:first-child{border-top:0;padding-top:0}
.overview-goal strong{font-size:.82rem;margin:0}.overview-goal span{font-size:.7rem;text-transform:none;letter-spacing:0;margin-top:2px}
.overview-calendar{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:var(--card)}
.overview-week{display:grid;grid-template-columns:165px minmax(0,1fr);border-top:1px solid var(--line)}
.overview-week:first-child{border-top:0}.overview-week.relation-current{background:#FAFAFF;box-shadow:inset 3px 0 0 var(--accent)}
.overview-week-summary{padding:14px 14px;border-right:1px solid var(--line);background:rgba(255,255,255,.46)}
.overview-week-summary a{text-decoration:none}.overview-week-label{color:inherit}.overview-week-summary strong{display:block;font-size:1.05rem}.overview-week-summary span{display:block;margin-top:2px;color:var(--muted);font-size:.68rem}
.overview-week-summary p{margin:10px 0 0;color:var(--secondary);font-size:.7rem;line-height:1.5}
.overview-week-intent{margin-top:8px;padding-top:7px;border-top:1px solid var(--line-soft)}
.overview-week-intent strong{display:block;font-size:.68rem}.overview-week-intent span{margin-top:2px;font-size:.62rem}
.overview-week-days{display:grid;grid-template-columns:repeat(7,minmax(125px,1fr));min-width:875px}
.overview-week-days.blueprint-mode{display:block;min-width:875px}
.overview-week-days.forward-preliminary-mode{display:grid}
.overview-commitment{display:inline-flex;margin-left:7px;padding:2px 6px;border-radius:999px;background:var(--elevated);font-size:.56rem;font-weight:700;color:var(--secondary);vertical-align:middle}
.overview-commitment.level-preliminary{background:#F2F4F8}
.overview-commitment.level-block_sketch{background:var(--accent-soft)}
.overview-forward-slot{margin-bottom:6px;padding:7px 8px;border:1px solid var(--line-soft);border-radius:9px;background:#F7F8FA}
.overview-forward-slot strong{display:block;font-size:.65rem;line-height:1.28}
.overview-forward-slot span,.overview-forward-slot small{display:block;margin-top:3px;font-size:.56rem;line-height:1.3;color:var(--muted)}
.overview-forward-open{font-size:.6rem;color:var(--muted)}
.overview-forward-sketch{min-height:140px;padding:13px 14px;display:grid;grid-template-columns:190px minmax(0,1fr);gap:12px}
.overview-forward-sketch .overview-blueprint-head strong{display:block;margin-top:4px;font-size:.82rem}
.overview-sketch-primary,.overview-sketch-support{display:flex;flex-wrap:wrap;gap:7px}
.overview-sketch-support{grid-column:2}
.overview-sketch-card{min-width:190px;max-width:280px;padding:8px 9px;border:1px solid var(--line-soft);border-radius:10px;background:#F2F4F8}
.overview-sketch-card.support{background:var(--elevated)}
.overview-sketch-card strong{display:block;font-size:.68rem}
.overview-sketch-card span,.overview-sketch-card small{display:block;margin-top:4px;font-size:.58rem;line-height:1.35;color:var(--muted)}
.overview-forward-sketch>p{grid-column:2;margin:0;font-size:.61rem;color:var(--secondary)}
.overview-week-blueprint{min-height:126px;padding:12px 14px;display:grid;grid-template-columns:180px minmax(0,1fr);gap:12px;align-items:start}
.overview-blueprint-head span{display:block;font-size:.66rem;font-weight:800;text-transform:uppercase;letter-spacing:.04em;color:var(--secondary)}
.overview-blueprint-head small{display:block;margin-top:4px;font-size:.62rem;line-height:1.35;color:var(--muted)}
.overview-blueprint-primary,.overview-blueprint-secondary{display:flex;flex-wrap:wrap;gap:7px}
.overview-blueprint-secondary{grid-column:2;margin-top:-4px}
.overview-blueprint-card{min-width:150px;max-width:230px;padding:8px 9px;border-radius:10px;background:#F2F4F8;border:1px solid var(--line-soft)}
.overview-blueprint-card.protected{background:var(--accent-soft)}
.overview-blueprint-card.support{background:var(--elevated)}
.overview-blueprint-card strong{display:block;font-size:.68rem;line-height:1.3}
.overview-blueprint-card span{display:block;margin-top:3px;font-size:.59rem;line-height:1.3;color:var(--muted)}
.overview-blueprint-card small{display:block;margin-top:5px;font-size:.58rem;line-height:1.35;color:var(--secondary)}
.overview-blueprint-card small.overview-target{padding-top:4px;border-top:1px solid var(--line-soft)}
.overview-blueprint-empty{padding:14px;color:var(--muted);font-size:.7rem}
.overview-day{min-height:126px;padding:10px 9px;border-left:1px solid var(--line-soft);position:relative}
.overview-day:first-child{border-left:0}.overview-day.today{box-shadow:inset 0 0 0 2px var(--accent);z-index:1}
.overview-day-head{display:flex;align-items:baseline;justify-content:space-between;gap:6px;margin-bottom:9px}
.overview-day-head span{font-size:.62rem;color:var(--muted);font-weight:760;text-transform:uppercase;letter-spacing:.04em}
.overview-day-head b{font-size:.7rem;color:var(--secondary)}.overview-day-body{display:grid;gap:7px}
.overview-layer{display:grid;gap:6px}.overview-plan-label{color:var(--muted);font-size:.58rem;font-weight:760;text-transform:uppercase;letter-spacing:.05em;margin-top:2px}
.overview-workout{display:flex;gap:6px;align-items:flex-start;min-width:0;padding:7px;border-radius:9px}
.overview-workout.planned{background:#F2F4F8}.overview-workout.planned.state-fixed{background:var(--accent-soft)}
.overview-workout.actual{background:var(--green-soft)}.overview-workout-copy{min-width:0;display:block}
.overview-workout strong{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;font-size:.7rem;line-height:1.32}
.overview-focus,.overview-facts{display:block;margin-top:3px;color:var(--muted);font-size:.61rem;line-height:1.28}
.overview-icon{width:13px;height:13px;flex:0 0 13px;color:var(--secondary);margin-top:1px}.overview-icons{display:flex;gap:2px}
.overview-rest{display:block;color:#9AA09C;font-size:.67rem;padding-top:4px}.overview-unplanned{display:block;color:var(--muted);font-size:.64rem;padding-top:4px;font-style:italic}.overview-empty{color:var(--muted);font-size:.76rem}
.overview-review{margin-top:18px;border:1px solid var(--line);border-radius:16px;background:var(--card);overflow:hidden}
.overview-review>summary{cursor:pointer;list-style:none;padding:14px 16px;font-size:.8rem;font-weight:760}
.overview-review>summary::-webkit-details-marker{display:none}.overview-review>summary:after{content:" +";color:var(--muted)}
.overview-review[open]>summary:after{content:" −"}.overview-review-copy{padding:0 16px 16px}
.overview-review-copy>p{margin:0 0 12px;color:var(--muted);font-size:.72rem;max-width:900px}
.overview-review-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.overview-review-item{padding:10px 11px;border:1px solid var(--line-soft);border-radius:12px;background:var(--elevated)}
.overview-review-item.attention{background:var(--amber-soft);border-color:#EFE3BF}
.overview-review-item span{font-size:.63rem;color:var(--muted);font-weight:800;text-transform:uppercase;letter-spacing:.04em}
.overview-review-item p{margin:5px 0 0;font-size:.73rem;color:var(--secondary)}
@media(max-width:900px){
  .overview-shell{padding:20px 12px 56px}.overview-topnav{justify-content:flex-start;overflow:auto;white-space:nowrap}
  .overview-hero{display:block}.overview-range{display:block;margin-top:9px}
  .overview-context{grid-template-columns:1fr}.overview-calendar{overflow-x:auto}
  .overview-week{grid-template-columns:135px minmax(875px,1fr)}
  .overview-review-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:620px){
  .overview-review-grid{grid-template-columns:1fr}
}
"""


def render_overview_document(
    model: TrainingOverviewReadModel,
    *,
    current_date: date,
    sport_icons: SportIconRegistry | None = None,
) -> str:
    weeks = "".join(
        _week_html(
            week,
            model=model,
            current_date=current_date,
            current_week_start=model.current_week_start,
            registry=sport_icons,
        )
        for week in model.weeks
    )
    start_label = f"{model.start.day} {MONTH_SHORT[model.start.month - 1]}"
    end_label = f"{model.end.day} {MONTH_SHORT[model.end.month - 1]} {model.end.year}"
    return (
        '<!doctype html><html lang="sv"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Översikt · Träning</title>'
        f'<style>{OVERVIEW_CSS}</style></head><body><div class="overview-shell">'
        '<nav class="overview-topnav">'
        '<a href="/träning/">Aktuell vecka</a>'
        '<a class="active" href="/träning/oversikt/">Översikt</a>'
        '<a href="/träning/utveckling/">Mål &amp; utveckling</a>'
        '<a href="/träning/onboarding/">Träningsprofil</a>'
        '</nav>'
        '<header class="overview-hero"><div>'
        '<div class="overview-kicker">Coachens planeringsyta</div>'
        '<h1>Översikt</h1>'
        '<p>Åtta veckor i samma vy. Plan och utfall visas sida vid sida så att rytm, '
        'multipass, vilodagar, planeringshorisont och koppling till utvecklingsblocket går att granska utan att lämna kalendern.</p>'
        '</div>'
        f'<span class="overview-range">{_e(start_label)} – {_e(end_label)}</span></header>'
        f'{_context_html(model)}'
        f'<main class="overview-calendar" aria-label="Åtta veckors träningsöversikt">{weeks}</main>'
        f'{_review_html(model)}'
        '</div></body></html>'
    )
