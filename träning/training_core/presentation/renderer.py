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
from training_core.presentation.manual_activity import ManualActivityReadModel
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


def _render_sport_icon(
    snapshot: PresentationSnapshot | HistoricalPresentationSnapshot,
    key: str,
) -> str:
    registry = snapshot.sport_icons
    if registry is None:
        return ""
    icon = registry.require(key)
    escaped_key = html.escape(icon.key, quote=True)
    view_box = html.escape(icon.view_box, quote=True)
    path = html.escape(icon.path, quote=True)
    if icon.solid:
        return (
            f'<svg class="v2-sport-icon icon-{escaped_key}" '
            f'data-sport-icon="{escaped_key}" aria-hidden="true" '
            f'viewBox="{view_box}" fill="currentColor" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{path}"/></svg>'
        )
    return (
        f'<svg class="v2-sport-icon icon-{escaped_key}" '
        f'data-sport-icon="{escaped_key}" aria-hidden="true" '
        f'viewBox="{view_box}" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{path}"/></svg>'
    )


def _render_icon_group(
    snapshot: PresentationSnapshot | HistoricalPresentationSnapshot,
    keys: tuple[str, ...],
) -> str:
    if not keys or snapshot.sport_icons is None:
        return ""
    icons = "".join(_render_sport_icon(snapshot, key) for key in keys)
    return (
        f'<span class="v2-sport-icons" data-sport-icons="{html.escape(",".join(keys), quote=True)}">'
        f'{icons}</span>'
    )


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


def _render_outcome(
    snapshot: PresentationSnapshot,
    outcome: ActivityOutcomeReadModel,
    *,
    show_label: bool,
) -> str:
    heading = (
        '<h2 class="v2-outcome-title">'
        + _render_icon_group(snapshot, (outcome.icon_key,))
        + f'<span>{html.escape(outcome.label)}</span></h2>'
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


def _render_manual_activities(
    snapshot: PresentationSnapshot,
    activities: tuple[ManualActivityReadModel, ...],
    *,
    css_class: str,
) -> str:
    if not activities:
        return ""
    items = []
    for activity in activities:
        reason = (
            f'<p>{html.escape(activity.reason)}</p>'
            if activity.reason else ""
        )
        items.append(
            '<article class="v2-manual-activity" '
            f'data-sport="{html.escape(activity.sport, quote=True)}" '
            f'data-classification="{html.escape(activity.classification, quote=True)}">'
            '<header>'
            + _render_icon_group(snapshot, (activity.icon_key,))
            + f'<strong>{html.escape(activity.session)}</strong>'
            f'<span>{html.escape(activity.classification_label)}</span>'
            '</header>'
            f'{reason}</article>'
        )
    return (
        f'<section class="{css_class}" aria-label="Manuellt rapporterade aktiviteter">'
        + "".join(items)
        + "</section>"
    )


def _render_completed_context(
    snapshot: PresentationSnapshot,
    model: TodayReadModel,
) -> str:
    if not model.outcomes:
        return ""
    cards = "".join(
        _render_outcome(snapshot, outcome, show_label=len(model.outcomes) > 1)
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
    snapshot: HistoricalPresentationSnapshot,
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
        + _render_icon_group(snapshot, (activity.icon_key,))
        + f'<h3>{html.escape(activity.label)}</h3>{classification}</header>'
        f'{detail}{report}{evaluation}{impact}{next_step}{uncertainty}</article>'
    )


def _render_historical_day(
    snapshot: HistoricalPresentationSnapshot,
    day: HistoricalDayReadModel,
) -> str:
    activities = "".join(
        _render_historical_activity(snapshot, activity)
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
        + _render_icon_group(snapshot, day.planned_icon_keys)
        + f'<strong>{html.escape(day.planned_session)}</strong>'
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
    days = "".join(_render_historical_day(snapshot, day) for day in model.days)
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


WATCH_ICON = (
    '<svg class="v2-watch-icon" aria-hidden="true" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="7" y="5" width="10" height="14" rx="2.2"/>'
    '<path d="M9.5 5V2.5h5V5M9.5 19v2.5h5V19M12 9v3l2 1.5"/>'
    '</svg>'
)


def _render_device_sync(sync) -> str:
    if sync is None:
        return ""
    return (
        f'<div class="v2-device-sync {html.escape(sync.status, quote=True)}" '
        f'data-device-sync="{html.escape(sync.status, quote=True)}" '
        f'title="{html.escape(sync.help_text, quote=True)}">'
        f'{WATCH_ICON}<span>{html.escape(sync.label)}</span></div>'
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
    completed_context = _render_completed_context(snapshot, model)
    manual_html = _render_manual_activities(
        snapshot,
        model.manual_activities,
        css_class="v2-today-manual-activities",
    )
    weather_html = (
        _render_weather_line(snapshot, model.local_date, "v2-today-weather")
        if not model.outcomes else ""
    )
    device_sync_html = _render_device_sync(model.device_sync)

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
        '<p class="v2-kicker">Idag</p><h1 class="v2-today-title">'
        + _render_icon_group(snapshot, model.icon_keys)
        + f'<span>{html.escape(model.title)}</span></h1>'
        f'{details}{weather_html}{device_sync_html}{manual_html}{completed_context}{prescription}{rationale}{next_html}</section>'
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


def render_week_status(snapshot: PresentationSnapshot) -> str:
    model = snapshot.week
    sports = "".join(
        '<div class="v2-week-sport">'
        f'<span>{html.escape(item.label)}</span>'
        f'<strong>{html.escape(item.duration)}</strong>'
        '</div>'
        for item in model.sport_distribution
    )
    distribution = (
        '<div class="v2-week-sports">'
        '<h3>Grenfördelning · passtid</h3>'
        f'{sports}</div>'
        if sports else ""
    )
    return (
        '<details class="v2-week-status">'
        f'<summary>{html.escape(model.status_summary)}</summary>'
        '<div class="v2-week-status-body">'
        '<div class="v2-week-metrics">'
        f'<span><strong>{model.completed_activity_count}</strong> pass</span>'
        f'<span><strong>{html.escape(model.session_time)}</strong> passtid</span>'
        f'<span><strong>{model.training_day_count}</strong> träningsdagar</span>'
        '</div>'
        f'{distribution}</div></details>'
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
        manual_html = _render_manual_activities(
            snapshot,
            day.manual_activities,
            css_class="v2-week-manual-activities",
        )
        device_sync_html = _render_device_sync(day.device_sync)
        rows.append(
            f'<li data-date="{day.local_date.isoformat()}" data-state="{html.escape(day.state)}">'
            '<strong class="v2-week-session">'
            + _render_icon_group(snapshot, day.icon_keys)
            + f'<span>{html.escape(shown)}</span></strong>{weather_html}'
            + device_sync_html
            + f'{manual_html}</li>'
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


STRENGTH_REFERENCE = (
    "Liten dos explosivitet/plyometri när omkringliggande belastning tillåter.",
    "Bulgarian split squat som huvudalternativ för unilateral benstyrka.",
    "Marklyft eller RDL som normal höftdominant huvudövning.",
    "Vad + soleus regelbundet.",
    "Enarmsrodd + press som huvuddrag/press.",
    "Välj två bålövningar; låt inte accessoarer tränga undan huvudstyrkan.",
)

SYSTEM_REFERENCE = (
    ("Målbild", "Den långsiktiga riktningen är överordnad. Ändrad målbild kräver omprövning nedåt i planeringskedjan."),
    ("Mesocykel", "Flerveckors planeringsmotor för utvecklingsfokus, skyddade stimuli, progression och utvärdering."),
    ("Mikrocykel", "Organiserar arbetet till en absorberbar följd av pass, vila och öppna beslut."),
    ("Pass", "Verkställer ett tydligt stimulus eller en stödjande roll; stimuluset skyddas före exakt passform eller veckodag."),
    ("Återkoppling", "Faktisk respons går tillbaka uppåt och kan justera mikrocykel och mesocykel."),
)


def render_reference_tools() -> str:
    strength = "".join(f"<li>{html.escape(item)}</li>" for item in STRENGTH_REFERENCE)
    system = "".join(
        f"<li><strong>{html.escape(label)}:</strong> {html.escape(copy)}</li>"
        for label, copy in SYSTEM_REFERENCE
    )
    return (
        '<nav class="v2-reference-tools" aria-label="Referenser">'
        '<button type="button" data-v2-open-reference="strength">Styrkemall</button>'
        '<button type="button" data-v2-open-reference="system">Om systemet</button>'
        '</nav>'
        '<dialog id="v2-strength-reference" class="v2-reference-dialog">'
        '<form method="dialog"><button aria-label="Stäng">Stäng</button></form>'
        '<h2>Styrkemall</h2>'
        '<p>Referens. Aktuellt styrkebeslut styrs av mesocykeln, mikrocykelns ordning och faktisk närbelastning.</p>'
        f'<ul>{strength}</ul></dialog>'
        '<dialog id="v2-system-reference" class="v2-reference-dialog">'
        '<form method="dialog"><button aria-label="Stäng">Stäng</button></form>'
        '<h2>Om träningssystemet</h2>'
        '<p><strong>Målbilden anger vart. Mesocykeln väljer utvecklingsväg. Mikrocykeln organiserar arbetet.</strong></p>'
        f'<ul>{system}</ul></dialog>'
        '<script>document.querySelectorAll("[data-v2-open-reference]").forEach((b)=>'
        'b.addEventListener("click",()=>document.getElementById("v2-"+b.dataset.v2OpenReference+"-reference").showModal()));</script>'
    )


V2_SHELL_CSS = """
:root{color-scheme:light;--bg:#f5f7fb;--card:#fff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#2563eb;--shadow:0 8px 24px rgba(15,23,42,.06);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text);background:var(--bg)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);line-height:1.45}
.v2-shell{width:min(100%,760px);margin:auto;padding:20px 16px 56px}.v2-shell a{color:inherit}.v2-shell-main{display:grid;gap:18px}.v2-shell-meta{display:flex;justify-content:flex-end;margin:4px 2px 8px;font-size:.82rem;color:var(--muted)}
.v2-week-nav{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;padding:9px 10px;border:1px solid var(--line);border-radius:14px;background:#fff;box-shadow:0 6px 18px rgba(15,23,42,.04)}.v2-week-link{font-size:.82rem;font-weight:800;color:#1d4ed8!important;text-decoration:none}.v2-week-link.next{text-align:right}.v2-week-current{text-align:center;line-height:1.15}.v2-week-current strong{display:block;font-size:.86rem}.v2-week-current span{display:block;margin-top:3px;color:var(--muted);font-size:.65rem;font-weight:800}
.v2-today,.v2-week-context,.v2-week-status,.v2-week>ol>li,.v2-activity-outcome,.v2-manual-activity,.v2-week-review,.v2-history-day{background:var(--card);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow)}
.v2-today{padding:18px}.v2-kicker{text-transform:uppercase;letter-spacing:.1em;font-size:.72rem;font-weight:800;color:var(--muted);margin:0 0 7px}.v2-today-title{font-size:1.55rem;line-height:1.15;letter-spacing:-.025em;margin:0 0 10px;display:flex;align-items:center;gap:.55rem}.v2-today-details{margin:8px 0 14px;padding-left:20px;color:#334155}.v2-today-details li{margin:4px 0}
.v2-sport-icon{display:inline-block;width:1.25em;height:1.25em;max-width:1.25em;max-height:1.25em;flex:0 0 1.25em;vertical-align:-.18em}.v2-sport-icons{display:inline-flex;align-items:center;gap:.3em;flex:0 0 auto}.v2-week-session,.v2-outcome-title,.v2-history-activity header,.v2-manual-activity header{display:flex;align-items:center;gap:.5rem}.v2-watch-icon{width:1em;height:1em;flex:0 0 1em}
.v2-completed-outcomes{display:grid;gap:12px}.v2-activity-outcome{padding:14px 15px;box-shadow:none;border-radius:14px}.v2-outcome-row{margin-top:13px}.v2-outcome-label{display:block;color:var(--muted);font-size:.76rem;font-weight:800;margin-bottom:4px}.v2-outcome-row p{margin:3px 0;color:#334155}.v2-feedback-compact{display:flex;align-items:center;gap:8px}.v2-feedback-toggle{font:inherit;font-size:.75rem}.v2-feedback-note{margin:6px 0;color:#334155}.v2-feedback-panel{margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}.v2-feedback-options{display:flex;flex-wrap:wrap;gap:6px;margin:5px 0 10px}.v2-feedback-chip{border:1px solid #cbd5e1;background:#fff;border-radius:999px;padding:6px 9px}.v2-feedback-chip[aria-pressed="true"]{background:#dbeafe;border-color:#93c5fd}.v2-feedback textarea{width:100%;min-height:90px;margin-top:5px;border:1px solid #cbd5e1;border-radius:10px;padding:9px;font:inherit}.v2-feedback-actions{display:flex;gap:8px;margin-top:8px}
.v2-completed-context,.v2-rationale,.v2-week-status{border:1px solid var(--line);border-radius:14px;background:#fff;box-shadow:none;overflow:hidden}.v2-completed-context summary,.v2-rationale summary,.v2-week-status summary{cursor:pointer;padding:12px 14px;font-weight:800}.v2-completed-context-body,.v2-week-status-body,.v2-week-context-plan-body{padding:0 14px 14px}.v2-prescription{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}.v2-prescription h2{font-size:1rem;margin:0 0 7px}.v2-prescription ul{margin:0;padding-left:20px}
.v2-week-context{padding:17px 18px}.v2-week-context h2{font-size:1.2rem;margin:0 0 9px}.v2-week-focus{display:block;font-size:.98rem}.v2-week-meta{color:var(--muted);font-size:.86rem;margin:7px 0}.v2-week-context-plan{margin-top:10px}.v2-week-context-plan summary{cursor:pointer;font-weight:800}
.v2-week-status{border-radius:18px;box-shadow:var(--shadow)}.v2-week-metrics{display:flex;gap:16px;flex-wrap:wrap;color:#334155}.v2-week-sports{margin-top:12px}.v2-week-sports h3{font-size:.85rem}.v2-week-sport{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:7px 0}
.v2-week{background:transparent}.v2-week>p{color:var(--muted);font-size:.88rem;margin:0 2px 8px}.v2-week>ol{list-style:none;margin:0;padding:0;display:grid;gap:10px}.v2-week>ol>li{padding:14px 16px}.v2-week-session{font-size:.98rem}.v2-week-weather,.v2-today-weather{color:var(--muted);font-size:.82rem;margin:7px 0 0}.v2-weather-source{font-size:.75rem!important;margin-top:8px!important}
.v2-device-sync{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:.78rem;margin-top:7px}.v2-next{margin:14px 0 0;color:#334155}.v2-next span{font-size:.76rem;font-weight:800;color:var(--muted);text-transform:uppercase;margin-right:5px}
.v2-reference-tools{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}.v2-reference-tools button,.v2-reference-dialog button{font:inherit}.v2-reference-tools button{border:1px solid #cbd5e1;background:#fff;border-radius:999px;padding:9px 13px;font-size:.82rem;font-weight:700}.v2-reference-dialog{width:min(520px,calc(100vw - 32px));max-height:calc(100vh - 32px);border:1px solid var(--line);border-radius:18px;padding:18px}.v2-reference-dialog::backdrop{background:rgba(15,23,42,.38)}.v2-reference-dialog form{float:right}
.v2-history-header,.v2-week-review,.v2-history-day{padding:18px}.v2-history-days{display:grid;gap:12px}.v2-history-activity{padding:12px 0;border-top:1px solid var(--line)}.v2-history-activity:first-child{border-top:0}
@media(min-width:650px){.v2-shell{padding-top:34px}.v2-today,.v2-week-context,.v2-week>ol>li{padding:20px 22px}}
@media(max-width:620px){.v2-shell{padding:14px 12px 48px}.v2-week-nav{grid-template-columns:1fr auto 1fr;padding:8px}.v2-week-link{font-size:.75rem}.v2-week-current strong{font-size:.8rem}.v2-today-title{font-size:1.4rem}.v2-reference-dialog{width:calc(100vw - 16px);max-height:78vh}}
"""


def render_document(snapshot: PresentationSnapshot, *, title: str = "Träning") -> str:
    body = render_snapshot(snapshot)
    return (
        '<!doctype html><html lang="sv"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(title)}</title><style>{V2_SHELL_CSS}</style></head><body>'
        '<div class="v2-shell">'
        '<div class="v2-shell-meta"><a href="/träning/malbild-2027/" data-v2-goal-link>Målbild 2027 →</a></div>'
        f'<main class="v2-shell-main">{body}</main>'
        f'{render_reference_tools()}'
        '</div></body></html>'
    )


def render_snapshot(snapshot: PresentationSnapshot) -> str:
    feedback_script = FEEDBACK_SCRIPT if snapshot.today.outcomes else ""
    return (
        render_navigation(snapshot)
        + render_today(snapshot)
        + render_week_context(snapshot)
        + render_week_status(snapshot)
        + render_week(snapshot)
        + feedback_script
    )
