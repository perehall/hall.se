"""Pure HTML renderer for v2 presentation read models."""

from __future__ import annotations

import html

from training_core.application.presentation import PresentationSnapshot
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


def render_navigation(snapshot: PresentationSnapshot) -> str:
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
    feedback_script = FEEDBACK_SCRIPT if snapshot.today.outcomes else ""
    return (
        render_navigation(snapshot)
        + render_today(snapshot)
        + render_week(snapshot)
        + feedback_script
    )
