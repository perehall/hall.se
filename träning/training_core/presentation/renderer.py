"""Pure HTML renderer for v2 presentation read models."""

from __future__ import annotations

import html

from training_core.application.presentation import PresentationSnapshot


def render_today(snapshot: PresentationSnapshot) -> str:
    model = snapshot.today
    detail_html = "".join(f"<li>{html.escape(detail)}</li>" for detail in model.details)
    details = f'<ul class="v2-today-details">{detail_html}</ul>' if detail_html else ""
    prescription_html = "".join(
        f"<li>{html.escape(line)}</li>" for line in model.prescription
    )
    prescription = (
        f'<section class="v2-prescription"><h2>Passupplägg</h2><ul>{prescription_html}</ul></section>'
        if prescription_html else ""
    )
    rationale_parts = [
        part for part in (model.reason, model.development_focus) if part
    ]
    rationale = (
        '<details class="v2-rationale"><summary>Plan och motivering</summary>'
        + "".join(f"<p>{html.escape(part)}</p>" for part in rationale_parts)
        + "</details>"
        if rationale_parts else ""
    )
    next_html = (
        f'<p class="v2-next"><span>Nästa</span> {html.escape(model.next_session)}</p>'
        if model.next_session else ""
    )
    return (
        f'<section class="v2-today" data-state="{html.escape(model.state)}">'
        f'<p class="v2-kicker">Idag</p><h1>{html.escape(model.title)}</h1>'
        f'{details}{prescription}{rationale}{next_html}</section>'
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
