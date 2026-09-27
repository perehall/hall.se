"""Pure HTML renderer for v2 presentation read models."""

from __future__ import annotations

import html

from training_core.application.presentation import PresentationSnapshot
from training_core.presentation.today import ActivityOutcomeReadModel, TodayReadModel


def _render_outcome(outcome: ActivityOutcomeReadModel, *, show_label: bool) -> str:
    heading = (
        f'<h2 class="v2-outcome-title">{html.escape(outcome.label)}</h2>'
        if show_label else ""
    )
    feedback_note = (
        f'<p class="v2-feedback-note">{html.escape(outcome.feedback_text)}</p>'
        if outcome.feedback_text else ""
    )
    feedback = (
        '<div class="v2-outcome-row v2-feedback">'
        '<span class="v2-outcome-label">Din känsla</span>'
        f'<strong>{html.escape(outcome.feedback_status)}</strong>'
        f'{feedback_note}</div>'
    )
    evaluation = (
        '<div class="v2-outcome-row v2-evaluation">'
        '<span class="v2-outcome-label">Utvärdering</span>'
        f'<p>{html.escape(outcome.coach_summary)}</p></div>'
        if outcome.coach_summary else ""
    )
    impact_copy = outcome.plan_impact
    if outcome.action_reason:
        impact_copy += (
            (" · " if impact_copy else "")
            + outcome.action_reason
        )
    impact = (
        '<div class="v2-outcome-row v2-plan-impact">'
        '<span class="v2-outcome-label">Planpåverkan</span>'
        f'<p>{html.escape(impact_copy)}</p></div>'
        if impact_copy else ""
    )
    next_step = (
        '<div class="v2-outcome-row v2-next-step">'
        '<span class="v2-outcome-label">Nästa steg</span>'
        f'<p>{html.escape(outcome.next_step)}</p></div>'
        if outcome.next_step else ""
    )
    return (
        f'<article class="v2-activity-outcome" '
        f'data-activity-id="{html.escape(outcome.provider_activity_id)}">'
        f'{heading}{feedback}{evaluation}{impact}{next_step}</article>'
    )


def _render_completed_context(model: TodayReadModel) -> str:
    if not model.outcomes:
        return ""
    cards = "".join(
        _render_outcome(outcome, show_label=len(model.outcomes) > 1)
        for outcome in model.outcomes
    )
    planned = (
        '<details class="v2-completed-context">'
        '<summary>Analys och motivering</summary>'
        '<div class="v2-completed-context-body">'
        '<span class="v2-outcome-label">Ursprungsplan</span>'
        f'<p>{html.escape(model.planned_session)}</p></div></details>'
        if model.planned_session else ""
    )
    return f'<section class="v2-completed-outcomes">{cards}</section>{planned}'


def render_today(snapshot: PresentationSnapshot) -> str:
    model = snapshot.today
    detail_html = "".join(f"<li>{html.escape(detail)}</li>" for detail in model.details)
    details = f'<ul class="v2-today-details">{detail_html}</ul>' if detail_html else ""
    completed_context = _render_completed_context(model)

    prescription_html = "".join(
        f"<li>{html.escape(line)}</li>" for line in model.prescription
    )
    prescription = (
        f'<section class="v2-prescription"><h2>Passupplägg</h2><ul>{prescription_html}</ul></section>'
        if prescription_html and not model.outcomes else ""
    )
    rationale_parts = [
        part for part in (model.reason, model.development_focus) if part
    ]
    rationale = (
        '<details class="v2-rationale"><summary>Plan och motivering</summary>'
        + "".join(f"<p>{html.escape(part)}</p>" for part in rationale_parts)
        + "</details>"
        if rationale_parts and not model.outcomes else ""
    )
    next_html = (
        f'<p class="v2-next"><span>Nästa</span> {html.escape(model.next_session)}</p>'
        if model.next_session else ""
    )
    return (
        f'<section class="v2-today" data-state="{html.escape(model.state)}">'
        f'<p class="v2-kicker">Idag</p><h1>{html.escape(model.title)}</h1>'
        f'{details}{completed_context}{prescription}{rationale}{next_html}</section>'
    )


def render_week(snapshot: PresentationSnapshot) -> str:
    model = snapshot.week
    rows = []
    for day in model.days:
        actual = " + ".join(day.actual_labels)
        shown = actual or day.planned_session
        rows.append(
            f'<li data-date="{day.local_date.isoformat()}" data-state="{html.escape(day.state)}">'
            f'<strong>{html.escape(shown)}</strong></li>'
        )
    return (
        f'<section class="v2-week" data-start="{model.start.isoformat()}" '
        f'data-end="{model.end.isoformat()}">'
        f'<p>{model.training_day_count} träningsdagar · '
        f'{model.completed_activity_count} aktiviteter</p>'
        f'<ol>{"".join(rows)}</ol></section>'
    )


def render_snapshot(snapshot: PresentationSnapshot) -> str:
    return render_today(snapshot) + render_week(snapshot)
