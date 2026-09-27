"""Pure HTML renderer for v2 presentation read models."""

from __future__ import annotations

import html

from training_core.application.presentation import PresentationSnapshot


def render_today(snapshot: PresentationSnapshot) -> str:
    model = snapshot.today
    detail_html = "".join(
        f"<li>{html.escape(detail)}</li>" for detail in model.details
    )
    details = f'<ul class="v2-today-details">{detail_html}</ul>' if detail_html else ""
    next_html = (
        f'<p class="v2-next"><span>Nästa</span> {html.escape(model.next_session)}</p>'
        if model.next_session
        else ""
    )
    return (
        f'<section class="v2-today" data-state="{html.escape(model.state)}">'
        f'<p class="v2-kicker">Idag</p>'
        f'<h1>{html.escape(model.title)}</h1>'
        f'{details}{next_html}'
        f'</section>'
    )
