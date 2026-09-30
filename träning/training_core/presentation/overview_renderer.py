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
        return '<div class="overview-blueprint-empty">Planeringsunderlag saknas.</div>'

    def card(item):
        title = _short_character(item.label)
        chip, chip_class = _progress_chip(
            intent=item.progression_intent,
            role=item.role,
        )
        chip_html = (
            f'<span class="overview-pass-chip chip-{_e(chip_class)}">{_e(chip)}</span>'
            if chip else ""
        )
        attrs = _detail_button_attrs(
            title=title,
            full_session=item.baseline_session or item.label,
            role=ROLE_LABELS.get(item.role, item.role),
            status="Preliminär",
            development=item.capability_label,
            baseline=item.baseline_session,
            target=item.conditional_target_session,
        )
        return (
            f'<button class="overview-blueprint-card" {attrs}>'
            f'<strong>{_e(title)}</strong>{chip_html}'
            '</button>'
        )

    cards = [
        card(item)
        for group in (
            blueprint.planned_variants,
            blueprint.protected_variants,
            blueprint.supporting_candidates,
        )
        for item in group
    ]
    return (
        '<div class="overview-week-blueprint">'
        '<div class="overview-blueprint-head"><span>Preliminär</span></div>'
        f'<div class="overview-blueprint-primary">{"".join(cards)}</div>'
        '</div>'
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
            '<section class="overview-planbar unavailable">'
            '<strong>Planeringskontext saknas</strong>'
            '</section>'
        )

    block = context.active_block
    if block is None:
        return ""

    wave = "".join(
        '<span class="overview-wave-step'
        + (' current' if item.start_date == model.current_week_start.isoformat() else '')
        + '">'
        f'<b>{item.index}</b>{_e(_intent_label(item.intent))}'
        '</span>'
        for item in block.microcycle_intents
    )
    primary = "".join(
        f'<span class="overview-capability-chip">{_e(value)}</span>'
        for value in block.primary_capabilities
    )
    axes = " · ".join(
        f"{axis.capability_label}: {AXIS_LABELS.get(axis.axis, axis.axis)}"
        for axis in block.progression_axes
        if axis.capability_label and axis.axis
    )
    checkpoint = _fmt_date(block.evaluation_date)

    goals = []
    for goal in context.goals[:3]:
        meta = " · ".join(
            value for value in (goal.target, _fmt_date(goal.target_date)) if value
        )
        goals.append(
            f'<li><strong>{_e(goal.label)}</strong>'
            + (f'<span>{_e(meta)}</span>' if meta else "")
            + '</li>'
        )

    details = []
    if axes:
        details.append(f'<p><b>Progressionsaxlar:</b> {_e(axes)}</p>')
    if checkpoint:
        details.append(f'<p><b>Checkpoint:</b> {_e(checkpoint)}</p>')
    if goals:
        details.append(
            '<div class="overview-planbar-goals"><b>Mot mål</b><ul>'
            + "".join(goals)
            + '</ul></div>'
        )

    more = (
        '<details class="overview-planbar-more"><summary>Planlogik</summary>'
        f'<div>{"".join(details)}</div></details>'
        if details else ""
    )

    return (
        '<section class="overview-planbar">'
        '<div class="overview-planbar-main">'
        '<div class="overview-planbar-title">'
        '<span>Aktuellt block</span>'
        f'<strong>{_e(block.title or "Aktivt block")}</strong>'
        f'<div class="overview-capability-chips">{primary}</div>'
        '</div>'
        f'<div class="overview-block-wave">{wave}</div>'
        '</div>'
        f'{more}'
        '</section>'
    )




def _planned_item(
    workout,
    registry: SportIconRegistry | None,
    *,
    progression_intent: str = "",
    plan_status: str = "",
) -> str:
    title = _short_workout_title(
        workout.session,
        workout.recipe_key,
        workout.sport,
        workout.session,
    )
    chip, chip_class = _progress_chip(
        intent=progression_intent,
        relation=workout.development_relation,
        state=workout.state,
        role=workout.priority_role,
    )
    chip_html = (
        f'<span class="overview-pass-chip chip-{_e(chip_class)}">{_e(chip)}</span>'
        if chip else ""
    )
    role = ROLE_LABELS.get(workout.priority_role, workout.priority_role)
    status = plan_status or ("Fast" if workout.state == "fixed" else "Planerad")
    attrs = _detail_button_attrs(
        title=title,
        full_session=workout.session,
        role=role,
        status=status,
        development=workout.development_focus,
        why=workout.development_reason,
    )
    return (
        f'<button class="overview-workout planned state-{_e(workout.state)}" '
        f'data-workout-key="{_e(workout.workout_key)}" {attrs}>'
        f'{_icon_group(registry, workout.icon_keys)}'
        '<span class="overview-workout-copy">'
        f'<strong>{_e(title)}</strong>{chip_html}'
        '</span></button>'
    )


def _actual_item(activity, registry: SportIconRegistry | None) -> str:
    facts = []
    if activity.distance_m > 0:
        facts.append(activity.distance)
    if activity.duration_s > 0:
        facts.append(activity.duration)
    detail = " · ".join(facts)
    title = _trim(activity.label or "Genomfört pass", 28)
    attrs = _detail_button_attrs(
        title=title,
        full_session=activity.label,
        status="Genomfört",
        development=detail,
    )
    return (
        f'<button class="overview-workout actual" {attrs}>'
        f'{_icon(registry, activity.icon_key)}'
        '<span class="overview-workout-copy">'
        f'<strong>{_e(title)}</strong>'
        '<span class="overview-pass-chip chip-completed">✓ Genomfört</span>'
        + (f'<span class="overview-facts">{_e(detail)}</span>' if detail else "")
        + '</span></button>'
    )


def _forward_slot_intent(forward, local_date: date, recipe_key: str) -> str:
    if forward is None or forward.planning_level != "preliminary":
        return ""
    day_index = local_date.weekday() + 1
    matches = [
        slot for slot in forward.slots
        if slot.day_index == day_index and slot.recipe_key == recipe_key
    ]
    return matches[0].progression_intent if len(matches) == 1 else ""


def _day_html(
    day,
    *,
    current_date: date,
    registry: SportIconRegistry | None,
    materialized: bool,
    forward=None,
    plan_status: str = "",
) -> str:
    classes = ["overview-day", f"state-{day.state}"]
    if day.local_date == current_date:
        classes.append("today")
    actual = "".join(_actual_item(item, registry) for item in day.actual_activities)
    planned = "".join(
        _planned_item(
            item,
            registry,
            progression_intent=_forward_slot_intent(
                forward,
                day.local_date,
                item.recipe_key,
            ),
            plan_status=plan_status,
        )
        for item in day.planned_workouts
    )

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
            else '<span class="overview-unplanned">Öppen</span>'
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


def _week_summary(week, relation: str, forward) -> str:
    if relation == "past":
        bits = [f"{week.completed_count} pass"]
        if week.completed_count and week.actual_duration_s:
            bits.append(week.actual_duration)
        if week.actual_distance_m > 0:
            bits.append(week.actual_distance)
        return " · ".join(bits)

    if week.planned_count > 0:
        workouts = list(week.planned_workouts)
        total = len(workouts)
        key_count = sum(item.priority_role == "anchor" for item in workouts)
        sport_counts = {}
        for item in workouts:
            sport = str(item.sport or "").lower()
            sport_counts[sport] = sport_counts.get(sport, 0) + 1
    elif forward is not None and forward.planning_level == "preliminary":
        slots = list(forward.slots)
        total = len(slots)
        key_count = sum(slot.role == "primary" for slot in slots)
        sport_counts = {}
        for slot in slots:
            sport = str(slot.sport or "").lower()
            sport_counts[sport] = sport_counts.get(sport, 0) + 1
    else:
        return "Riktning efter blockreview"

    bits = [f"{total} pass"]
    if key_count:
        bits.append(f"{key_count} nyckelpass")
    for sport, label in (("swim", "sim"), ("strength", "styrka"), ("bike", "cykel"), ("enduro", "enduro")):
        count = sport_counts.get(sport, 0)
        if count:
            bits.append(f"{count} {label}")
        if len(bits) >= 4:
            break
    return " · ".join(bits[:4])


def _week_focus(model: TrainingOverviewReadModel, week, forward, blueprint, expected) -> str:
    if forward is not None and forward.planning_level == "block_sketch":
        labels = [item.capability_label for item in forward.capability_directions if item.capability_label]
        prefix = "Blockreview" if forward.block_intent == "review" else "Nästa block"
        return _trim(
            "Fokus: " + prefix + (f" · {' + '.join(labels[:2])}" if labels else ""),
            80,
        )

    labels = []
    if blueprint is not None:
        for item in blueprint.planned_variants:
            if item.capability_label and item.capability_label not in labels:
                labels.append(item.capability_label)
    if not labels and model.context and model.context.active_block:
        labels = list(model.context.active_block.primary_capabilities[:2])

    intent = _intent_label(
        week.block_intents[0]
        if len(week.block_intents) == 1
        else expected.intent if expected else forward.block_intent if forward else ""
    )
    if not intent and not labels:
        return ""
    value = intent
    if labels:
        value += (" · " if value else "") + " + ".join(labels[:2])
    return _trim(f"Fokus: {value}", 80)




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
    blueprint = _expected_blueprint(model, week.start)
    forward = _expected_forward_week(model, week.start)

    if relation == "past":
        status = "Genomförd"
        status_class = "completed"
    elif relation == "current":
        status = "Aktuell"
        status_class = "current"
    elif week.planned_count > 0:
        status = "Planerad"
        status_class = "planned"
    elif forward is not None and forward.planning_level == "preliminary":
        status = "Preliminär"
        status_class = "preliminary"
    elif forward is not None and forward.planning_level == "block_sketch":
        status = "Blockskiss"
        status_class = "block-sketch"
    else:
        status = "Öppen"
        status_class = "open"

    summary = _week_summary(week, relation, forward)
    focus = _week_focus(model, week, forward, blueprint, expected)

    if relation == "future" and week.planned_count == 0 and forward is not None:
        if forward.planning_level == "preliminary":
            days = _forward_preliminary_html(forward, week.start, registry)
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
                forward=forward,
                plan_status=status,
            )
            for day in week.days
        )
        display_mode = ""

    heading = (
        '<div class="overview-week-titleline">'
        f'<strong>V{week.week_number}</strong>'
        f'<span class="overview-status-chip status-{_e(status_class)}">{_e(status.upper())}</span>'
        '</div>'
        f'<span class="overview-week-dates">{week.start.day} {MONTH_SHORT[week.start.month - 1]} – '
        f'{week.end.day} {MONTH_SHORT[week.end.month - 1]}</span>'
    )
    if relation != "future" or week.planned_count > 0:
        heading = f'<a href="{_week_url(week.start, current_week_start)}">{heading}</a>'

    return (
        f'<section class="overview-week relation-{relation}" data-week="{_e(week.iso_key)}">'
        '<header class="overview-week-summary">'
        f'{heading}'
        f'<p class="overview-week-metrics">{_e(summary)}</p>'
        + (f'<p class="overview-week-focus">{_e(focus)}</p>' if focus else "")
        + '</header>'
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
    attention_count = sum(state == "attention" for _, _, state in rows)
    summary = (
        f"Granska plan · {attention_count} saker att kontrollera"
        if attention_count
        else "Granska plan ✓"
    )
    return (
        '<details class="overview-review">'
        f'<summary>{_e(summary)}</summary>'
        '<div class="overview-review-copy">'
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
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);line-height:1.4}
button,input,textarea,select{font:inherit}
button{color:inherit}
a{color:inherit}
.overview-shell{width:min(1500px,100%);margin:auto;padding:24px 18px 72px}
.overview-topnav{display:flex;justify-content:flex-end;gap:18px;margin-bottom:34px;font-size:.78rem}
.overview-topnav a{color:var(--muted);text-decoration:none}
.overview-topnav a.active{color:var(--text);font-weight:720}
.overview-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin:0 0 18px}
.overview-kicker{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;font-weight:780;color:var(--muted)}
.overview-hero h1{font-size:clamp(2rem,4vw,3.25rem);letter-spacing:-.05em;line-height:1;margin:7px 0 7px}
.overview-hero p{margin:0;color:var(--secondary);font-size:.86rem}
.overview-range{color:var(--muted);font-size:.73rem;white-space:nowrap}

.overview-planbar{margin-bottom:16px;border:1px solid var(--line);background:var(--card);border-radius:16px;padding:13px 15px}
.overview-planbar-main{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(360px,1.2fr);gap:18px;align-items:center}
.overview-planbar-title>span{display:block;color:var(--muted);font-size:.61rem;text-transform:uppercase;letter-spacing:.06em;font-weight:760}
.overview-planbar-title>strong{display:block;margin-top:3px;font-size:.92rem}
.overview-capability-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
.overview-capability-chip,.overview-sketch-chip{display:inline-flex;align-items:center;min-height:23px;padding:3px 8px;border-radius:999px;border:1px solid var(--line-soft);background:var(--elevated);font-size:.61rem;color:var(--secondary)}
.overview-block-wave{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px}
.overview-wave-step{display:flex;align-items:center;justify-content:center;gap:4px;min-height:31px;padding:5px;border:1px solid var(--line-soft);border-radius:9px;background:var(--elevated);font-size:.6rem;color:var(--secondary)}
.overview-wave-step b{font-size:.58rem;color:var(--muted)}
.overview-wave-step.current{border-color:#c9cdf8;background:var(--accent-soft);color:var(--text)}
.overview-planbar-more{margin-top:8px;border-top:1px solid var(--line-soft);padding-top:7px}
.overview-planbar-more>summary{cursor:pointer;list-style:none;width:max-content;color:var(--muted);font-size:.64rem;font-weight:700}
.overview-planbar-more>summary::-webkit-details-marker{display:none}
.overview-planbar-more>summary:after{content:" +"}
.overview-planbar-more[open]>summary:after{content:" −"}
.overview-planbar-more>div{display:grid;grid-template-columns:1fr 1fr;gap:8px 18px;margin-top:8px;color:var(--secondary);font-size:.69rem}
.overview-planbar-more p{margin:0}
.overview-planbar-goals ul{margin:4px 0 0;padding-left:18px}
.overview-planbar-goals li+li{margin-top:3px}
.overview-planbar-goals li span{margin-left:5px;color:var(--muted)}

.overview-calendar{display:grid;gap:10px;background:transparent}
.overview-week{display:grid;grid-template-columns:178px minmax(0,1fr);border:1px solid var(--line);border-radius:16px;overflow:hidden;background:var(--card)}
.overview-week.relation-current{background:#FAFAFF;box-shadow:inset 3px 0 0 var(--accent)}
.overview-week-summary{padding:13px 13px;border-right:1px solid var(--line);background:rgba(255,255,255,.5)}
.overview-week-summary a{text-decoration:none}
.overview-week-titleline{display:flex;align-items:center;gap:7px}
.overview-week-titleline>strong{font-size:1.02rem;letter-spacing:-.02em}
.overview-status-chip{display:inline-flex;align-items:center;padding:2px 6px;border-radius:999px;font-size:.52rem;font-weight:800;letter-spacing:.035em;color:var(--secondary);background:#F0F2F0}
.overview-status-chip.status-current{background:var(--accent-soft);color:#4D56C9}
.overview-status-chip.status-completed{background:var(--green-soft);color:var(--green)}
.overview-status-chip.status-preliminary{background:#F1F2F4}
.overview-status-chip.status-block-sketch{background:var(--accent-soft)}
.overview-week-dates{display:block;margin-top:2px;color:var(--muted);font-size:.64rem}
.overview-week-metrics{margin:9px 0 0;color:var(--secondary);font-size:.67rem;line-height:1.35}
.overview-week-focus{margin:6px 0 0;padding-top:6px;border-top:1px solid var(--line-soft);color:var(--text);font-size:.64rem;line-height:1.34}

.overview-week-days{display:grid;grid-template-columns:repeat(7,minmax(124px,1fr));min-width:868px}
.overview-week-days.blueprint-mode{display:block;min-width:868px}
.overview-week-days.forward-preliminary-mode{display:grid}
.overview-day{min-height:104px;padding:8px 7px;border-left:1px solid var(--line-soft);position:relative}
.overview-day:first-child{border-left:0}
.overview-day.today{box-shadow:inset 0 0 0 2px var(--accent);z-index:1}
.overview-day-head{display:flex;align-items:baseline;justify-content:space-between;gap:6px;margin-bottom:7px}
.overview-day-head span{font-size:.57rem;color:var(--muted);font-weight:760;text-transform:uppercase;letter-spacing:.04em}
.overview-day-head b{font-size:.65rem;color:var(--secondary)}
.overview-day-body,.overview-layer{display:grid;gap:5px}
.overview-plan-label{color:var(--muted);font-size:.52rem;font-weight:760;text-transform:uppercase;letter-spacing:.05em;margin-top:1px}

.overview-workout{appearance:none;width:100%;border:0;text-align:left;display:flex;gap:6px;align-items:flex-start;min-width:0;padding:6px 7px;border-radius:9px;cursor:pointer}
.overview-workout:focus-visible,.overview-blueprint-card:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.overview-workout.planned{background:#F2F4F8}
.overview-workout.planned.preliminary{background:#F7F8F9;border:1px dashed #E3E6E4}
.overview-workout.planned.state-fixed{background:var(--accent-soft)}
.overview-workout.actual{background:var(--green-soft)}
.overview-workout-copy{min-width:0;display:block}
.overview-workout strong{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:.66rem;line-height:1.25;font-weight:700}
.overview-facts{display:block;margin-top:2px;color:var(--muted);font-size:.56rem;line-height:1.2}
.overview-pass-chip{display:block;width:max-content;max-width:100%;margin-top:3px;padding:1px 5px;border-radius:999px;font-size:.51rem;line-height:1.45;color:var(--muted);background:rgba(255,255,255,.72);white-space:nowrap}
.chip-progress{color:#4D56C9;background:var(--accent-soft)}
.chip-variation{color:var(--secondary)}
.chip-consolidate{color:var(--secondary)}
.chip-establish{color:var(--secondary)}
.chip-support,.chip-protected{color:var(--muted)}
.chip-fixed{color:#4D56C9;background:var(--accent-soft)}
.chip-completed{color:var(--green);background:rgba(255,255,255,.5)}
.overview-icon{width:12px;height:12px;flex:0 0 12px;color:var(--secondary);margin-top:1px}
.overview-icons{display:flex;gap:2px}
.overview-rest,.overview-unplanned,.overview-forward-open{display:block;color:#989E9A;font-size:.6rem;padding-top:3px}
.overview-unplanned{font-style:normal}

.overview-forward-sketch{min-height:112px;padding:12px 14px}
.overview-sketch-heading{display:flex;align-items:baseline;gap:8px;margin-bottom:9px}
.overview-sketch-heading strong{font-size:.76rem}
.overview-sketch-heading span{color:var(--muted);font-size:.58rem}
.overview-sketch-groups{display:grid;grid-template-columns:1.05fr 1.45fr 1fr 1fr;gap:11px}
.overview-sketch-group>span{display:block;margin-bottom:5px;color:var(--muted);font-size:.55rem;text-transform:uppercase;letter-spacing:.045em;font-weight:760}
.overview-sketch-group>div{display:flex;flex-wrap:wrap;gap:5px}
.overview-sketch-chip.sketch-primary{background:var(--accent-soft);color:#4D56C9}
.overview-sketch-chip.sketch-character{background:#F2F4F8}
.overview-sketch-chip.sketch-support{background:var(--elevated)}
.overview-sketch-chip.sketch-protected{background:#F7F8F7;color:var(--muted)}

.overview-week-blueprint{min-height:105px;padding:12px 14px;display:grid;grid-template-columns:105px minmax(0,1fr);gap:10px;align-items:start}
.overview-blueprint-head span{display:block;font-size:.57rem;font-weight:780;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.overview-blueprint-primary{display:flex;flex-wrap:wrap;gap:6px}
.overview-blueprint-card{appearance:none;border:1px solid var(--line-soft);min-width:145px;max-width:220px;padding:7px 8px;border-radius:9px;background:#F2F4F8;text-align:left;cursor:pointer}
.overview-blueprint-card strong{display:block;font-size:.64rem}
.overview-blueprint-empty{padding:14px;color:var(--muted);font-size:.68rem}

.overview-review{margin-top:14px;border:1px solid var(--line);border-radius:14px;background:var(--card);overflow:hidden}
.overview-review>summary{cursor:pointer;list-style:none;padding:11px 14px;font-size:.72rem;font-weight:720;color:var(--secondary)}
.overview-review>summary::-webkit-details-marker{display:none}
.overview-review>summary:after{content:"  +";color:var(--muted)}
.overview-review[open]>summary:after{content:"  −"}
.overview-review-copy{padding:0 13px 13px}
.overview-review-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
.overview-review-item{padding:9px 10px;border:1px solid var(--line-soft);border-radius:10px;background:var(--elevated)}
.overview-review-item.attention{background:var(--amber-soft);border-color:#EFE3BF}
.overview-review-item>span{font-size:.57rem;color:var(--muted);font-weight:800;text-transform:uppercase;letter-spacing:.04em}
.overview-review-item p{margin:4px 0 0;font-size:.67rem;color:var(--secondary);line-height:1.35}

.overview-detail{width:min(430px,100%);max-width:none;height:100dvh;max-height:100dvh;margin:0 0 0 auto;padding:0;border:0;border-left:1px solid var(--line);background:var(--elevated);color:var(--text)}
.overview-detail::backdrop{background:rgba(23,25,24,.18)}
.overview-detail-shell{min-height:100%;padding:22px 20px 32px}
.overview-detail-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.overview-detail-head span{display:block;color:var(--muted);font-size:.58rem;text-transform:uppercase;letter-spacing:.055em;font-weight:760}
.overview-detail-head h2{margin:4px 0 0;font-size:1.25rem;letter-spacing:-.025em}
.overview-detail-close{appearance:none;border:1px solid var(--line);background:var(--card);border-radius:999px;width:32px;height:32px;cursor:pointer;font-size:1rem}
.overview-detail-grid{display:grid;gap:12px;margin-top:22px}
.overview-detail-row{padding-top:11px;border-top:1px solid var(--line-soft)}
.overview-detail-row:first-child{padding-top:0;border-top:0}
.overview-detail-row>span{display:block;color:var(--muted);font-size:.57rem;text-transform:uppercase;letter-spacing:.05em;font-weight:760}
.overview-detail-row>p{margin:4px 0 0;color:var(--secondary);font-size:.78rem;line-height:1.45}
.overview-detail-row[hidden]{display:none}

@media(max-width:900px){
  .overview-shell{padding:20px 12px 56px}
  .overview-topnav{justify-content:flex-start;overflow:auto;white-space:nowrap}
  .overview-hero{display:block}.overview-range{display:block;margin-top:7px}
  .overview-planbar-main{grid-template-columns:1fr}
  .overview-calendar{overflow-x:auto}
  .overview-week{grid-template-columns:160px minmax(868px,1fr);min-width:1028px}
  .overview-sketch-groups{grid-template-columns:repeat(2,minmax(0,1fr))}
  .overview-review-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:620px){
  .overview-review-grid{grid-template-columns:1fr}
  .overview-detail{width:100%}
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

    detail_dialog = (
        '<dialog class="overview-detail" id="overview-detail" aria-labelledby="overview-detail-title">'
        '<div class="overview-detail-shell">'
        '<div class="overview-detail-head"><div>'
        '<span id="overview-detail-status">Passdetalj</span>'
        '<h2 id="overview-detail-title">Pass</h2>'
        '</div><button class="overview-detail-close" type="button" aria-label="Stäng">×</button></div>'
        '<div class="overview-detail-grid">'
        '<div class="overview-detail-row" data-detail-row="full-session"><span>Pass</span><p></p></div>'
        '<div class="overview-detail-row" data-detail-row="role"><span>Roll</span><p></p></div>'
        '<div class="overview-detail-row" data-detail-row="development"><span>Utveckling</span><p></p></div>'
        '<div class="overview-detail-row" data-detail-row="baseline"><span>Bas</span><p></p></div>'
        '<div class="overview-detail-row" data-detail-row="target"><span>Villkorat nästa steg</span><p></p></div>'
        '<div class="overview-detail-row" data-detail-row="why"><span>Varför?</span><p></p></div>'
        '</div></div></dialog>'
    )
    detail_script = r"""
<script>
(() => {
  const dialog = document.getElementById('overview-detail');
  if (!dialog) return;
  const title = document.getElementById('overview-detail-title');
  const status = document.getElementById('overview-detail-status');
  const rows = {
    fullSession: dialog.querySelector('[data-detail-row="full-session"]'),
    role: dialog.querySelector('[data-detail-row="role"]'),
    development: dialog.querySelector('[data-detail-row="development"]'),
    baseline: dialog.querySelector('[data-detail-row="baseline"]'),
    target: dialog.querySelector('[data-detail-row="target"]'),
    why: dialog.querySelector('[data-detail-row="why"]')
  };
  const fill = (row, value) => {
    const text = (value || '').trim();
    row.hidden = !text;
    const p = row.querySelector('p');
    if (p) p.textContent = text;
  };
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-overview-detail]');
    if (!trigger) return;
    title.textContent = trigger.dataset.title || 'Pass';
    status.textContent = trigger.dataset.status || 'Passdetalj';
    fill(rows.fullSession, trigger.dataset.fullSession);
    fill(rows.role, trigger.dataset.role);
    fill(rows.development, trigger.dataset.development);
    fill(rows.baseline, trigger.dataset.baseline);
    fill(rows.target, trigger.dataset.target);
    fill(rows.why, trigger.dataset.why);
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  });
  dialog.querySelector('.overview-detail-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
})();
</script>
"""

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
        '<p>2 veckor bakåt · aktuell vecka · 5 veckor framåt</p>'
        '</div>'
        f'<span class="overview-range">{_e(start_label)} – {_e(end_label)}</span></header>'
        f'{_context_html(model)}'
        f'<main class="overview-calendar" aria-label="Åtta veckors träningsöversikt">{weeks}</main>'
        f'{_review_html(model)}'
        f'{detail_dialog}'
        '</div>'
        f'{detail_script}'
        '</body></html>'
    )
