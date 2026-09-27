"""Pure HTML renderer for v2 presentation read models."""

from __future__ import annotations

import html

from training_core.application.presentation import (
    HistoricalPresentationSnapshot,
    PresentationSnapshot,
)
from training_core.presentation.history import (
    HistoricalActivityReadModel,
    HistoricalDayReadModel,
    HistoricalWeekReviewReadModel,
)
from training_core.presentation.today import (
    ActivityOutcomeReadModel,
    FEELING_LABELS,
    TodayReadModel,
)


RPE_OPTIONS = (
    (2, "Mycket lätt"),
    (4, "Lätt"),
    (6, "Lagom"),
    (8, "Tungt"),
    (10, "För tungt"),
)

FEEDBACK_SCRIPT = r"""
<script>
/* training-v2-feedback */
(() => {
  const roots = [...document.querySelectorAll('[data-v2-feedback-editor]')];
  if (!roots.length) return;

  const PENDING_PREFIX = 'training-v2-feedback:';
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const pendingKey = (activityId) => PENDING_PREFIX + activityId;
  const savePending = (activityId, value) => {
    try { localStorage.setItem(pendingKey(activityId), JSON.stringify(value)); }
    catch (error) { console.debug('V2_FEEDBACK_PENDING_WRITE_FAILED', error); }
  };
  const readPending = (activityId) => {
    try {
      const raw = localStorage.getItem(pendingKey(activityId));
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      console.debug('V2_FEEDBACK_PENDING_READ_FAILED', error);
      return null;
    }
  };
  const clearPending = (activityId) => {
    try { localStorage.removeItem(pendingKey(activityId)); }
    catch (error) { console.debug('V2_FEEDBACK_PENDING_CLEAR_FAILED', error); }
  };

  async function waitForPublished(activityId, eventKey, status) {
    for (let attempt = 0; attempt < 150; attempt += 1) {
      await sleep(2000);
      try {
        const probe = new URL(window.location.href);
        probe.searchParams.set('_feedback_sync', String(Date.now()));
        const response = await fetch(probe.toString(), {
          method: 'GET',
          credentials: 'same-origin',
          cache: 'no-store'
        });
        if (!response.ok) continue;
        const source = await response.text();
        const doc = new DOMParser().parseFromString(source, 'text/html');
        const fresh = [...doc.querySelectorAll('[data-v2-feedback-editor]')]
          .find((item) => item.dataset.activityId === String(activityId));
        if (fresh && fresh.dataset.feedbackEventKey === eventKey) {
          clearPending(activityId);
          window.location.reload();
          return;
        }
      } catch (error) {
        console.debug('V2_FEEDBACK_POLL_RETRY', error);
      }
      if (attempt === 5) status.textContent = 'Sparat · analys uppdateras…';
    }
    status.textContent = 'Sparat · analysen uppdateras senare.';
  }

  roots.forEach((root) => {
    const activityId = root.dataset.activityId;
    const editor = root.querySelector('[data-v2-feedback-panel]');
    const toggle = root.querySelector('[data-v2-feedback-toggle]');
    const cancel = root.querySelector('[data-v2-feedback-cancel]');
    const save = root.querySelector('[data-v2-feedback-save]');
    const status = root.querySelector('[data-v2-feedback-status]');
    const summary = root.querySelector('[data-v2-feedback-summary]');
    const note = root.querySelector('[data-v2-feedback-note]');
    const textarea = root.querySelector('textarea');
    const rpeButtons = [...root.querySelectorAll('[data-v2-rpe]')];
    const feelingButtons = [...root.querySelectorAll('[data-v2-feeling]')];

    let rpe = null;
    let feelings = new Set();

    const readControls = () => {
      const activeRpe = rpeButtons.find((button) => button.getAttribute('aria-pressed') === 'true');
      rpe = activeRpe ? Number(activeRpe.dataset.v2Rpe) : null;
      feelings = new Set(
        feelingButtons
          .filter((button) => button.getAttribute('aria-pressed') === 'true')
          .map((button) => button.dataset.v2Feeling)
      );
    };
    readControls();

    const feelingLabel = (code) => {
      const button = feelingButtons.find((item) => item.dataset.v2Feeling === code);
      return button ? button.textContent.trim() : code;
    };
    const state = () => ({
      rpe,
      feelings: [...feelings],
      text: textarea.value
    });
    let initial = state();

    const apply = (value) => {
      rpe = Number.isInteger(value.rpe) ? value.rpe : null;
      feelings = new Set(Array.isArray(value.feelings) ? value.feelings : []);
      textarea.value = typeof value.text === 'string' ? value.text : '';
      rpeButtons.forEach((button) => {
        button.setAttribute(
          'aria-pressed',
          Number(button.dataset.v2Rpe) === rpe ? 'true' : 'false'
        );
      });
      feelingButtons.forEach((button) => {
        button.setAttribute(
          'aria-pressed',
          feelings.has(button.dataset.v2Feeling) ? 'true' : 'false'
        );
      });
    };

    const updateSummary = (prefix = 'Sparat') => {
      const parts = [];
      if (rpe !== null) parts.push('RPE ' + rpe);
      [...feelings].forEach((code) => parts.push(feelingLabel(code)));
      summary.textContent = parts.length ? parts.join(' · ') : prefix;
      note.textContent = textarea.value.trim();
      toggle.textContent = 'Ändra';
    };

    const pending = readPending(activityId);
    if (pending && pending.eventKey === root.dataset.feedbackEventKey) {
      clearPending(activityId);
    } else if (pending && pending.eventKey) {
      apply(pending);
      initial = state();
      updateSummary('Sparat');
      status.textContent = 'Sparat · analys uppdateras…';
      void waitForPublished(activityId, pending.eventKey, status);
    }

    toggle.addEventListener('click', () => {
      apply(initial);
      editor.hidden = false;
      toggle.hidden = true;
      status.textContent = '';
      textarea.focus({preventScroll: true});
    });

    cancel.addEventListener('click', () => {
      apply(initial);
      editor.hidden = true;
      toggle.hidden = false;
      status.textContent = '';
    });

    rpeButtons.forEach((button) => button.addEventListener('click', () => {
      const value = Number(button.dataset.v2Rpe);
      rpe = rpe === value ? null : value;
      rpeButtons.forEach((item) => {
        item.setAttribute(
          'aria-pressed',
          Number(item.dataset.v2Rpe) === rpe ? 'true' : 'false'
        );
      });
    }));

    feelingButtons.forEach((button) => button.addEventListener('click', () => {
      const value = button.dataset.v2Feeling;
      if (feelings.has(value)) feelings.delete(value);
      else feelings.add(value);
      button.setAttribute('aria-pressed', feelings.has(value) ? 'true' : 'false');
    }));

    save.addEventListener('click', async () => {
      const comment = textarea.value.trim();
      if (!comment && rpe === null && feelings.size === 0) {
        status.textContent = 'Välj ansträngning/känsla eller skriv en kommentar.';
        return;
      }

      let operation = comment ? 'UPDATE_COMPLETED_WORKOUT' : 'ADD_FEEDBACK';
      if (!comment && feelings.has('pain')) operation = 'REPORT_PAIN';
      else if (!comment && feelings.has('tired')) operation = 'REPORT_FATIGUE';

      save.disabled = true;
      status.textContent = 'Sparar…';

      try {
        const response = await fetch('/träning/training-api/input', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'content-type': 'application/json'},
          body: JSON.stringify({
            operation,
            activity_id: Number(activityId),
            text: comment,
            rpe,
            feeling: [...feelings],
            source: 'training-gui-v2'
          })
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || 'request_failed');
        if (body.status !== 'saved' || body.persistence !== 'supabase' || !body.event_key) {
          throw new Error('durable_ack_missing');
        }

        const saved = {
          eventKey: body.event_key,
          rpe,
          feelings: [...feelings],
          text: comment
        };
        savePending(activityId, saved);
        initial = state();
        updateSummary('Sparat');
        editor.hidden = true;
        toggle.hidden = false;
        save.disabled = false;
        status.textContent = body.processing === 'deferred'
          ? 'Sparat · analysen köas om automatiskt.'
          : 'Sparat · analys uppdateras…';
        void waitForPublished(activityId, body.event_key, status);
      } catch (error) {
        status.textContent = 'Kunde inte spara (' + error.message + ').';
        save.disabled = false;
        editor.hidden = false;
        toggle.hidden = true;
        console.error('V2_FEEDBACK_FAILED', error);
      }
    });
  });
})();
</script>
""".strip()


def _choice_button(
    *,
    css_class: str,
    data_name: str,
    data_value: str,
    label: str,
    selected: bool,
) -> str:
    return (
        f'<button type="button" class="{css_class}" '
        f'data-{data_name}="{html.escape(data_value, quote=True)}" '
        f'aria-pressed="{"true" if selected else "false"}">'
        f'{html.escape(label)}</button>'
    )


def _render_feedback_editor(outcome: ActivityOutcomeReadModel) -> str:
    rpe_html = "".join(
        _choice_button(
            css_class="v2-feedback-chip",
            data_name="v2-rpe",
            data_value=str(value),
            label=label,
            selected=outcome.rpe == value,
        )
        for value, label in RPE_OPTIONS
    )
    selected_feelings = set(outcome.feelings)
    feeling_html = "".join(
        _choice_button(
            css_class="v2-feedback-chip",
            data_name="v2-feeling",
            data_value=code,
            label=label,
            selected=code in selected_feelings,
        )
        for code, label in FEELING_LABELS.items()
    )
    reviewed = outcome.feedback_status != "Inte utvärderat"
    toggle_label = "Ändra" if reviewed else "Utvärdera"
    note = (
        f'<p class="v2-feedback-note" data-v2-feedback-note>'
        f'{html.escape(outcome.feedback_text)}</p>'
        if outcome.feedback_text
        else '<p class="v2-feedback-note" data-v2-feedback-note></p>'
    )
    return (
        '<div class="v2-outcome-row v2-feedback" data-v2-feedback-editor '
        f'data-activity-id="{html.escape(outcome.provider_activity_id, quote=True)}" '
        f'data-feedback-event-key="{html.escape(outcome.feedback_event_key, quote=True)}">'
        '<span class="v2-outcome-label">Din känsla</span>'
        '<div class="v2-feedback-compact">'
        f'<strong data-v2-feedback-summary>{html.escape(outcome.feedback_status)}</strong>'
        f'<button type="button" class="v2-feedback-toggle" data-v2-feedback-toggle>{toggle_label}</button>'
        '</div>'
        f'{note}<span class="v2-feedback-status" data-v2-feedback-status aria-live="polite"></span>'
        '<div class="v2-feedback-panel" data-v2-feedback-panel hidden>'
        '<span class="v2-feedback-label">Ansträngning</span>'
        f'<div class="v2-feedback-options">{rpe_html}</div>'
        '<span class="v2-feedback-label">Känsla</span>'
        f'<div class="v2-feedback-options">{feeling_html}</div>'
        '<span class="v2-feedback-label">Kommentar eller korrigering av passet</span>'
        f'<textarea maxlength="800">{html.escape(outcome.feedback_text)}</textarea>'
        '<div class="v2-feedback-actions">'
        '<button type="button" class="v2-feedback-save" data-v2-feedback-save>Spara</button>'
        '<button type="button" class="v2-feedback-cancel" data-v2-feedback-cancel>Avbryt</button>'
        '</div></div></div>'
    )


def _render_outcome(outcome: ActivityOutcomeReadModel, *, show_label: bool) -> str:
    heading = (
        f'<h2 class="v2-outcome-title">{html.escape(outcome.label)}</h2>'
        if show_label else ""
    )
    feedback = _render_feedback_editor(outcome)
    evaluation = (
        '<div class="v2-outcome-row v2-evaluation">'
        '<span class="v2-outcome-label">Utvärdering</span>'
        f'<p>{html.escape(outcome.coach_summary)}</p></div>'
        if outcome.coach_summary else ""
    )
    impact_copy = outcome.plan_impact
    if outcome.action_reason:
        impact_copy += ((" · " if impact_copy else "") + outcome.action_reason)
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
        f'data-activity-id="{html.escape(outcome.provider_activity_id, quote=True)}">'
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


def render_navigation(
    snapshot: PresentationSnapshot | HistoricalPresentationSnapshot,
) -> str:
    model = snapshot.navigation

    def link(item, css_class: str, arrow: str) -> str:
        if item is None:
            return f'<span class="v2-week-link {css_class} disabled"></span>'
        label = (
            f'{arrow} {item.label}' if css_class == "prev"
            else f'{item.label} {arrow}'
        )
        return (
            f'<a class="v2-week-link {css_class}" '
            f'href="{html.escape(item.url, quote=True)}">{html.escape(label)}</a>'
        )

    return (
        '<nav class="v2-week-nav" aria-label="Veckonavigering">'
        + link(model.previous, "prev", "‹")
        + '<div class="v2-week-current">'
        f'<strong>{html.escape(model.label)}</strong>'
        f'<span>{html.escape(model.period)} · {html.escape(model.state)}</span>'
        '</div>'
        + link(model.next, "next", "›")
        + '</nav>'
    )


WEEKDAY_LABELS = (
    "Måndag",
    "Tisdag",
    "Onsdag",
    "Torsdag",
    "Fredag",
    "Lördag",
    "Söndag",
)


def _render_string_list(items: tuple[str, ...]) -> str:
    if not items:
        return ""
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def _render_historical_review(
    review: HistoricalWeekReviewReadModel | None,
) -> str:
    if review is None:
        return ""
    uncertainties = (
        '<details class="v2-history-uncertainties">'
        '<summary>Osäkerheter i underlaget</summary>'
        + _render_string_list(review.uncertainties)
        + "</details>"
        if review.uncertainties else ""
    )
    return (
        '<section class="v2-week-review">'
        '<p class="v2-kicker">Veckosummering</p>'
        f'<p class="v2-week-review-summary">{html.escape(review.summary)}</p>'
        '<div class="v2-week-review-metrics">'
        f'<span><strong>{review.training_activity_count}</strong> träningspass</span>'
        f'<span><strong>{html.escape(review.total_activity_time)}</strong> passtid</span>'
        f'<span><strong>{review.active_days}</strong> träningsdagar</span>'
        + (
            f'<span><strong>{review.recreation_activity_count}</strong> rekreation</span>'
            if review.recreation_activity_count else ""
        )
        + '</div>'
        '<div class="v2-week-review-grid">'
        '<section><h2>Det som fungerade</h2>'
        + _render_string_list(review.worked)
        + '</section>'
        '<section><h2>Inte enligt plan</h2>'
        + _render_string_list(review.not_as_planned)
        + '</section>'
        '<section><h2>Belastning & kontinuitet</h2>'
        f'<p>{html.escape(review.load_continuity)}</p></section>'
        '<section><h2>Viktigaste lärdomen</h2>'
        f'<p>{html.escape(review.key_lesson)}</p></section>'
        '</div>'
        + (
            '<section class="v2-week-review-next"><h2>Implikation framåt</h2>'
            f'<p>{html.escape(review.next_week_implication)}</p></section>'
            if review.next_week_implication else ""
        )
        + uncertainties
        + '</section>'
    )


def _render_historical_activity(
    activity: HistoricalActivityReadModel,
) -> str:
    classification = (
        '<span class="v2-history-classification">Rekreation</span>'
        if activity.classification == "recreation" else ""
    )
    detail = (
        f'<p class="v2-history-activity-detail">{html.escape(activity.detail)}</p>'
        if activity.detail else ""
    )
    report = (
        '<div class="v2-history-user-report">'
        '<span class="v2-outcome-label">Din kommentar</span>'
        f'<p>{html.escape(activity.user_report)}</p></div>'
        if activity.user_report else ""
    )
    evaluation = (
        '<div class="v2-history-evaluation">'
        '<span class="v2-outcome-label">Utvärdering</span>'
        f'<p>{html.escape(activity.coach_summary)}</p></div>'
        if activity.coach_summary else ""
    )
    impact_copy = activity.plan_impact
    if activity.action_reason:
        impact_copy += ((" · " if impact_copy else "") + activity.action_reason)
    impact = (
        '<div class="v2-history-plan-impact">'
        '<span class="v2-outcome-label">Planpåverkan</span>'
        f'<p>{html.escape(impact_copy)}</p></div>'
        if impact_copy else ""
    )
    next_step = (
        '<div class="v2-history-next-step">'
        '<span class="v2-outcome-label">Nästa steg</span>'
        f'<p>{html.escape(activity.next_step)}</p></div>'
        if activity.next_step else ""
    )
    uncertainty = (
        '<details class="v2-history-activity-uncertainty">'
        '<summary>Osäkerhet</summary>'
        + _render_string_list(activity.uncertainties)
        + '</details>'
        if activity.uncertainties else ""
    )
    return (
        f'<article class="v2-history-activity" '
        f'data-activity-id="{html.escape(activity.provider_activity_id, quote=True)}">'
        '<header>'
        f'<h3>{html.escape(activity.label)}</h3>{classification}</header>'
        f'{detail}{report}{evaluation}{impact}{next_step}{uncertainty}</article>'
    )


def _render_historical_day(day: HistoricalDayReadModel) -> str:
    activities = "".join(
        _render_historical_activity(activity)
        for activity in day.activities
    )
    prescription = (
        '<div class="v2-history-prescription">'
        '<span class="v2-outcome-label">Passupplägg</span>'
        + _render_string_list(day.prescription)
        + '</div>'
        if day.prescription else ""
    )
    rationale = "".join(
        f"<p>{html.escape(value)}</p>"
        for value in (day.reason, day.development_focus)
        if value
    )
    planned = (
        '<details class="v2-history-original-plan">'
        '<summary>Ursprungsplan och motivering</summary>'
        '<div class="v2-history-original-plan-body">'
        f'<strong>{html.escape(day.planned_session)}</strong>'
        f'{prescription}{rationale}</div></details>'
        if day.planned_session or prescription or rationale else ""
    )
    label = WEEKDAY_LABELS[day.local_date.weekday()]
    return (
        f'<section class="v2-history-day" data-date="{day.local_date.isoformat()}" '
        f'data-state="{html.escape(day.state)}">'
        '<header class="v2-history-day-header">'
        f'<span>{html.escape(label)}</span>'
        f'<time datetime="{day.local_date.isoformat()}">{day.local_date.isoformat()}</time>'
        '</header>'
        f'<div class="v2-history-activities">{activities}</div>{planned}</section>'
    )


def render_historical_snapshot(
    snapshot: HistoricalPresentationSnapshot,
) -> str:
    model = snapshot.history
    days = "".join(_render_historical_day(day) for day in model.days)
    principle = (
        f'<p class="v2-history-principle">{html.escape(model.principle)}</p>'
        if model.principle else ""
    )
    header = (
        '<section class="v2-history-header">'
        '<p class="v2-kicker">Historisk vecka</p>'
        f'<h1>{html.escape(model.title or snapshot.navigation.label)}</h1>'
        f'{principle}</section>'
    )
    return (
        render_navigation(snapshot)
        + header
        + _render_historical_review(model.review)
        + f'<section class="v2-history-days">{days}</section>'
    )


def _render_weather_line(snapshot: PresentationSnapshot, local_date, css_class: str) -> str:
    weather = snapshot.weather.for_date(local_date)
    if weather is None or not weather.summary:
        return ""
    return (
        f'<p class="{css_class}" data-weather-date="{local_date.isoformat()}">'
        f'{html.escape(weather.summary)}</p>'
    )


def render_today(snapshot: PresentationSnapshot) -> str:
    model = snapshot.today
    detail_html = "".join(f"<li>{html.escape(detail)}</li>" for detail in model.details)
    details = f'<ul class="v2-today-details">{detail_html}</ul>' if detail_html else ""
    completed_context = _render_completed_context(model)
    weather_html = (
        _render_weather_line(snapshot, model.local_date, "v2-today-weather")
        if not model.outcomes else ""
    )

    prescription_html = "".join(
        f"<li>{html.escape(line)}</li>" for line in model.prescription
    )
    prescription = (
        f'<section class="v2-prescription"><h2>Passupplägg</h2><ul>{prescription_html}</ul></section>'
        if prescription_html and not model.outcomes else ""
    )
    rationale_parts = [part for part in (model.reason, model.development_focus) if part]
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
        f'{details}{weather_html}{completed_context}{prescription}{rationale}{next_html}</section>'
    )


def render_week_context(snapshot: PresentationSnapshot) -> str:
    model = snapshot.week_context
    if model is None:
        return ""

    taxonomy = []
    for label, values in (
        ("Primärt", model.primary),
        ("Sekundärt", model.secondary),
        ("Underhåll", model.maintenance),
        ("Skyddat", model.protected),
    ):
        if values:
            taxonomy.append(
                f"<strong>{html.escape(label)}:</strong> "
                + html.escape(", ".join(values))
            )

    details_parts = []
    if model.principle:
        details_parts.append(f"<p>{html.escape(model.principle)}</p>")
    if model.hypothesis:
        details_parts.append(
            '<p><strong>Mesocykelhypotes:</strong> '
            + html.escape(model.hypothesis)
            + "</p>"
        )
    if taxonomy:
        details_parts.append("<p>" + " · ".join(taxonomy) + "</p>")

    details = (
        '<details class="v2-week-context-plan">'
        '<summary>Planidé</summary>'
        '<div class="v2-week-context-plan-body">'
        + "".join(details_parts)
        + "</div></details>"
        if details_parts else ""
    )
    return (
        '<section class="v2-week-context" aria-label="Aktuell veckas fokus">'
        '<h2>Aktuell vecka</h2>'
        f'<strong class="v2-week-focus">{html.escape(model.focus)}</strong>'
        f'<p class="v2-week-meta">{html.escape(model.meta_line)}</p>'
        f'{details}</section>'
    )


def render_week(snapshot: PresentationSnapshot) -> str:
    model = snapshot.week
    rows = []
    for day in model.days:
        actual = " + ".join(day.actual_labels)
        shown = actual or day.planned_session
        weather_html = (
            _render_weather_line(snapshot, day.local_date, "v2-week-weather")
            if not day.actual_labels else ""
        )
        rows.append(
            f'<li data-date="{day.local_date.isoformat()}" data-state="{html.escape(day.state)}">'
            f'<strong>{html.escape(shown)}</strong>{weather_html}</li>'
        )
    source = (
        '<p class="v2-weather-source">Väderprognos: '
        f'<a href="{html.escape(snapshot.weather.source_url, quote=True)}" '
        'target="_blank" rel="noopener">SMHI</a></p>'
        if snapshot.weather.days else ""
    )
    return (
        f'<section class="v2-week" data-start="{model.start.isoformat()}" '
        f'data-end="{model.end.isoformat()}">'
        f'<p>{model.training_day_count} träningsdagar · '
        f'{model.completed_activity_count} aktiviteter</p>'
        f'<ol>{"".join(rows)}</ol>{source}</section>'
    )


def render_snapshot(snapshot: PresentationSnapshot) -> str:
    feedback_script = FEEDBACK_SCRIPT if snapshot.today.outcomes else ""
    return (
        render_navigation(snapshot)
        + render_today(snapshot)
        + render_week_context(snapshot)
        + render_week(snapshot)
        + feedback_script
    )
