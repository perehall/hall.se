#!/usr/bin/env python3
"""Add a compact post-workout input surface to the generated training page."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from coach_rules import planning_window
from finalize_post_workout_ui import local_date, matching_activity

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
OVERRIDES_FILE = ROOT / "data" / "activity_overrides.json"

CSS_MARKER = "/* training-input-ui-v1 */"
BLOCK_START = "<!-- training-input-ui-v1:start -->"
BLOCK_END = "<!-- training-input-ui-v1:end -->"
SCRIPT_MARKER = "/* training-input-ui-js-v1 */"

CSS = r"""
/* training-input-ui-v1 */
.training-input{margin:0;padding:14px 0;border-top:1px solid var(--qp-line,#e2e8f0)}
.training-input-compact{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:start}
.training-input-title-row{display:flex;align-items:baseline;gap:8px;min-width:0}
.training-input-title{font-size:.9rem;font-weight:800;color:var(--qp-text,#111827)}
.training-input-date{font-size:.72rem;color:var(--qp-secondary,#64748b)}
.training-input-summary{margin-top:3px;color:var(--qp-secondary,#5e6661);font-size:.8rem;line-height:1.35}
.training-input[data-reviewed="true"] .training-input-summary{color:var(--qp-text,#111827);font-weight:700}
.training-input-note{margin-top:3px;max-width:62ch;color:var(--qp-secondary,#64748b);font-size:.76rem;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.training-input-note:empty{display:none}
.training-input-status{margin-top:3px;color:var(--qp-secondary,#64748b);font-size:.73rem;line-height:1.3}
.training-input[data-submitting="true"] .training-input-status::before{content:"";display:inline-block;width:6px;height:6px;margin-right:6px;border-radius:50%;background:currentColor;vertical-align:1px;animation:training-input-pulse 1.2s ease-in-out infinite}
@keyframes training-input-pulse{0%,100%{opacity:.25}50%{opacity:1}}
.training-input-toggle,.training-input-cancel{appearance:none;border:0;background:transparent;color:var(--qp-accent,#5964e8);padding:3px 0;font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}
.training-input-editor{padding-top:14px;animation:training-input-open .16s ease-out}
.training-input-editor[hidden]{display:none}
@keyframes training-input-open{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:none}}
.training-input-label{display:block;margin:10px 0 6px;color:var(--qp-text-label,#475569);font-size:.66rem;font-weight:850;letter-spacing:.055em;text-transform:uppercase}
.training-input-options{display:flex;flex-wrap:wrap;gap:6px}
.training-input-chip{appearance:none;border:1px solid var(--qp-line,#d9dedb);background:transparent;color:var(--qp-secondary,#5e6661);border-radius:999px;padding:7px 10px;font:inherit;font-size:.76rem;cursor:pointer}
.training-input-chip[aria-pressed="true"]{border-color:var(--qp-accent,#5964e8);color:var(--qp-accent,#5964e8);box-shadow:inset 0 0 0 1px var(--qp-accent,#5964e8)}
.training-input textarea{box-sizing:border-box;width:100%;min-height:68px;resize:vertical;border:1px solid var(--qp-line,#d9dedb);border-radius:10px;background:transparent;color:var(--qp-text,#111827);padding:9px 10px;font:inherit;font-size:.82rem;line-height:1.4}
.training-input-actions{display:flex;align-items:center;gap:14px;margin-top:9px}
.training-input-save{appearance:none;border:0;border-radius:9px;background:var(--qp-accent,#5964e8);color:#fff;padding:8px 13px;font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}
.training-input-save:disabled{opacity:.55;cursor:default}
@media (max-width:560px){.training-input-compact{grid-template-columns:minmax(0,1fr) auto;gap:10px}.training-input-note{max-width:42ch}}
""".strip()

JS = r"""
/* training-input-ui-js-v1 */
(() => {
  const roots = [...document.querySelectorAll('[data-training-input]')];
  if (!roots.length) return;

  const pageUrl = new URL(window.location.href);
  if (pageUrl.searchParams.has('_feedback_done')) {
    pageUrl.searchParams.delete('_feedback_done');
    history.replaceState(null, '', pageUrl.toString());
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const PENDING_PREFIX = 'training-input-pending-v1:';
  const pendingKey = (activityId) => `${PENDING_PREFIX}${activityId}`;

  const processedKeys = (root) => (root.dataset.processedEventKeys || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);

  const readPending = (activityId) => {
    try {
      const raw = localStorage.getItem(pendingKey(activityId));
      if (!raw) return null;
      const value = JSON.parse(raw);
      if (
        !value ||
        value.activityId !== Number(activityId) ||
        !/^training-input:[0-9a-f]{24}$/.test(String(value.eventKey || ''))
      ) {
        return null;
      }
      return value;
    } catch (error) {
      console.debug('TRAINING_INPUT_PENDING_READ_FAILED', error);
      return null;
    }
  };

  const writePending = (activityId, eventKey, state, durable) => {
    try {
      localStorage.setItem(
        pendingKey(activityId),
        JSON.stringify({
          activityId: Number(activityId),
          eventKey,
          rpe: state.rpe,
          feelings: state.feelings,
          text: state.text,
          durable: Boolean(durable),
          submittedAt: new Date().toISOString()
        })
      );
    } catch (error) {
      console.debug('TRAINING_INPUT_PENDING_WRITE_FAILED', error);
    }
  };

  const clearPending = (activityId) => {
    try {
      localStorage.removeItem(pendingKey(activityId));
    } catch (error) {
      console.debug('TRAINING_INPUT_PENDING_CLEAR_FAILED', error);
    }
  };

  async function waitForProcessed(activityId, eventKey, onProgress) {
    for (let attempt = 0; attempt < 240; attempt += 1) {
      if (attempt === 5) onProgress('Uppdaterar analys…');
      if (attempt === 15) onProgress('Väntar på färdig omräkning…');
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
        const fresh = [...doc.querySelectorAll('[data-training-input]')]
          .find((item) => item.dataset.activityId === String(activityId));
        if (fresh) {
          const freshProcessedKeys = (fresh.dataset.processedEventKeys || '')
            .split(',')
            .map((value) => value.trim())
            .filter(Boolean);
          if (freshProcessedKeys.includes(eventKey)) return true;
        }
      } catch (error) {
        console.debug('TRAINING_INPUT_POLL_RETRY', error);
      }
    }
    return false;
  }

  roots.forEach((root) => {
    const editor = root.querySelector('[data-training-input-editor]');
    const toggle = root.querySelector('[data-training-input-toggle]');
    const cancel = root.querySelector('[data-training-input-cancel]');
    const summary = root.querySelector('[data-training-input-summary]');
    const notePreview = root.querySelector('[data-training-input-note]');
    const rpeButtons = [...root.querySelectorAll('[data-rpe]')];
    const feelingButtons = [...root.querySelectorAll('[data-feeling]')];
    const text = root.querySelector('textarea');
    const save = root.querySelector('[data-training-input-save]');
    const status = root.querySelector('[data-training-input-status]');

    let rpe = null;
    const feelings = new Set();
    const selectedRpe = rpeButtons.find((button) => button.getAttribute('aria-pressed') === 'true');
    if (selectedRpe) rpe = Number(selectedRpe.dataset.rpe);
    feelingButtons
      .filter((button) => button.getAttribute('aria-pressed') === 'true')
      .forEach((button) => feelings.add(button.dataset.feeling));

    const snapshot = () => ({
      rpe,
      feelings: [...feelings],
      text: text.value
    });
    let initial = snapshot();

    const feelingLabel = (key) => {
      const button = feelingButtons.find((item) => item.dataset.feeling === key);
      return button ? button.textContent.trim() : key;
    };

    const compactSummary = (stateLabel = 'Sparat') => {
      const parts = [stateLabel];
      if (rpe !== null) parts.push(`RPE ${rpe}`);
      [...feelings].forEach((key) => parts.push(feelingLabel(key)));
      return parts.join(' · ');
    };

    const updateCompact = (stateLabel = 'Sparat') => {
      root.dataset.reviewed = 'true';
      summary.textContent = compactSummary(stateLabel);
      notePreview.textContent = text.value.trim();
      toggle.textContent = 'Ändra';
    };

    const restore = (state) => {
      rpe = state.rpe;
      feelings.clear();
      state.feelings.forEach((value) => feelings.add(value));
      text.value = state.text;
      rpeButtons.forEach((button) => {
        button.setAttribute('aria-pressed', Number(button.dataset.rpe) === rpe ? 'true' : 'false');
      });
      feelingButtons.forEach((button) => {
        button.setAttribute('aria-pressed', feelings.has(button.dataset.feeling) ? 'true' : 'false');
      });
    };

    const openEditor = () => {
      restore(initial);
      editor.hidden = false;
      toggle.hidden = true;
      status.textContent = '';
      text.focus({preventScroll: true});
    };

    const closeEditor = () => {
      restore(initial);
      editor.hidden = true;
      toggle.hidden = false;
      status.textContent = '';
    };

    const refreshWhenProcessed = async (eventKey, durable) => {
      const processed = await waitForProcessed(
        root.dataset.activityId,
        eventKey,
        (message) => { status.textContent = message; }
      );
      if (processed) {
        clearPending(root.dataset.activityId);
        status.textContent = 'Klart';
        const next = new URL(window.location.href);
        next.searchParams.set('_feedback_done', String(Date.now()));
        window.location.replace(next.toString());
        return true;
      }

      status.textContent = durable
        ? 'Sparat · analysen uppdateras senare.'
        : 'Mottaget · väntar på publicering.';
      root.dataset.submitting = 'false';
      save.disabled = false;
      return false;
    };

    const pending = readPending(root.dataset.activityId);
    if (pending && processedKeys(root).includes(pending.eventKey)) {
      clearPending(root.dataset.activityId);
    } else if (pending) {
      restore({
        rpe: Number.isInteger(pending.rpe) ? pending.rpe : null,
        feelings: Array.isArray(pending.feelings) ? pending.feelings : [],
        text: typeof pending.text === 'string' ? pending.text : ''
      });
      initial = snapshot();
      const durable = pending.durable === true;
      updateCompact(durable ? 'Sparat' : 'Mottaget');
      editor.hidden = true;
      toggle.hidden = false;
      root.dataset.submitting = durable ? 'false' : 'true';
      save.disabled = !durable;
      status.textContent = durable ? 'Sparat · analys uppdateras…' : 'Mottaget · bearbetas';
      void refreshWhenProcessed(pending.eventKey, durable);
    }

    toggle.addEventListener('click', openEditor);
    cancel.addEventListener('click', closeEditor);

    const pressOne = (button) => {
      rpeButtons.forEach((item) => item.setAttribute('aria-pressed', item === button ? 'true' : 'false'));
      rpe = Number(button.dataset.rpe);
    };

    rpeButtons.forEach((button) => button.addEventListener('click', () => pressOne(button)));
    feelingButtons.forEach((button) => button.addEventListener('click', () => {
      const key = button.dataset.feeling;
      if (feelings.has(key)) feelings.delete(key); else feelings.add(key);
      button.setAttribute('aria-pressed', feelings.has(key) ? 'true' : 'false');
    }));

    save.addEventListener('click', async () => {
      const comment = text.value.trim();
      if (!comment && rpe === null && feelings.size === 0) {
        status.textContent = 'Välj en känsla eller skriv en kort kommentar.';
        return;
      }

      let operation = comment ? 'NATURAL_LANGUAGE' : 'ADD_FEEDBACK';
      if (!comment && feelings.has('pain')) operation = 'REPORT_PAIN';
      else if (!comment && feelings.has('tired')) operation = 'REPORT_FATIGUE';

      save.disabled = true;
      root.dataset.submitting = 'true';
      status.textContent = 'Sparar…';

      try {
        const response = await fetch('/träning/training-api/input', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'content-type': 'application/json'},
          body: JSON.stringify({
            operation,
            activity_id: Number(root.dataset.activityId),
            text: comment,
            rpe,
            feeling: [...feelings],
            source: 'training-gui-v1'
          })
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || 'request_failed');
        if (!body.event_key) throw new Error('missing_event_key');

        const durable = body.status === 'saved' && body.persistence === 'supabase';
        writePending(root.dataset.activityId, body.event_key, snapshot(), durable);
        updateCompact(durable ? 'Sparat' : 'Mottaget');
        initial = snapshot();
        editor.hidden = true;
        toggle.hidden = false;
        root.dataset.submitting = durable ? 'false' : 'true';
        save.disabled = !durable;
        status.textContent = durable
          ? (body.processing === 'deferred'
              ? 'Sparat · analys köas om automatiskt'
              : 'Sparat · analys uppdateras…')
          : 'Mottaget · bearbetas';

        void refreshWhenProcessed(body.event_key, durable);
      } catch (error) {
        status.textContent = `Kunde inte spara (${error.message}).`;
        root.dataset.submitting = 'false';
        save.disabled = false;
        editor.hidden = false;
        toggle.hidden = true;
        console.error('TRAINING_INPUT_FAILED', error);
      }
    });
  });
})();
""".strip()


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def remove_existing(page: str) -> str:
    page = re.sub(
        re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END),
        "",
        page,
        flags=re.S,
    )
    page = re.sub(
        r"/\* training-input-ui-v1 \*/.*?(?=(?:/\*|</style>))",
        "",
        page,
        flags=re.S,
    )
    page = re.sub(
        r"<script>\s*/\* training-input-ui-js-v1 \*/.*?</script>",
        "",
        page,
        flags=re.S,
    )
    return page


FEELING_LABELS = {
    "fresh": "Pigg",
    "tired": "Trött",
    "strong_legs": "Starka ben",
    "heavy_legs": "Tunga ben",
    "pain": "Smärta",
    "could_do_more": "Kunde gjort mer",
}

PROVIDER_LABELS = {
    "WeightTraining": "Styrka",
    "Run": "Löpning",
    "TrailRun": "Traillöpning",
    "Swim": "Simning",
    "Ride": "Cykling",
    "MountainBikeRide": "MTB",
    "Workout": "Träning",
}


def human_activity_label(activity: dict) -> str:
    candidate = (
        str(activity.get("display_label") or "").strip()
        or str(activity.get("sport_type") or "").strip()
        or str(activity.get("name") or "").strip()
        or "Genomfört pass"
    )
    return PROVIDER_LABELS.get(candidate, candidate)


def feedback_from_override(override: dict) -> dict | None:
    structured = override.get("training_feedback")
    if isinstance(structured, dict):
        feeling = [
            value
            for value in structured.get("feeling") or []
            if value in FEELING_LABELS
        ]
        rpe = structured.get("rpe")
        if not isinstance(rpe, int) or isinstance(rpe, bool) or not 1 <= rpe <= 10:
            rpe = None
        return {
            "text": str(structured.get("text") or "").strip(),
            "rpe": rpe,
            "feeling": feeling,
        }

    event_key = str(override.get("last_training_input_event_key") or "").strip()
    report = str(override.get("user_report") or "").strip()
    if not event_key or not report:
        return None

    groups = list(
        re.finditer(
            r"RPE\s+(\d+)/10\.\s*(?:Känsla:\s*([^.]+)\.\s*)?",
            report,
        )
    )
    if groups:
        current = groups[-1]
        segment_start = groups[-2].end() if len(groups) > 1 else 0
        segment = report[segment_start:].strip()
        rpe = int(current.group(1))
        feeling_text = current.group(2) or ""
    else:
        segment = report
        rpe = None
        feeling_text = ""

    reverse_feelings = {label: code for code, label in FEELING_LABELS.items()}
    feeling = []
    for label in (part.strip() for part in feeling_text.split(",") if part.strip()):
        code = reverse_feelings.get(label)
        if code and code not in feeling:
            feeling.append(code)

    text = re.sub(
        r"\s*RPE\s+\d+/10\.\s*(?:Känsla:\s*[^.]+\.\s*)?$",
        "",
        segment,
    ).strip()
    return {"text": text, "rpe": rpe, "feeling": feeling}


def feedback_summary(feedback: dict | None) -> str:
    if not feedback:
        return "Hur kändes passet?"
    parts = ["Sparat"]
    if isinstance(feedback.get("rpe"), int):
        parts.append(f"RPE {feedback['rpe']}")
    for code in feedback.get("feeling") or []:
        label = FEELING_LABELS.get(code)
        if label:
            parts.append(label)
    return " · ".join(parts)


def render_block(
    activity: dict,
    processed_event_keys: list[str] | None = None,
    feedback: dict | None = None,
) -> str:
    activity_id = int(activity["id"])
    processed_event_keys = processed_event_keys or []
    processed_event_keys_attr = ",".join(processed_event_keys)
    activity_label = human_activity_label(activity)
    activity_date = local_date(activity) or ""
    reviewed = feedback is not None
    summary = feedback_summary(feedback)
    note = str((feedback or {}).get("text") or "").strip()
    selected_rpe = (feedback or {}).get("rpe")
    selected_feelings = set((feedback or {}).get("feeling") or [])

    rpe = [
        (2, "Mycket lätt"),
        (4, "Lätt"),
        (6, "Lagom"),
        (8, "Tungt"),
        (10, "För tungt"),
    ]
    feelings = list(FEELING_LABELS.items())
    rpe_html = "".join(
        f'<button type="button" class="training-input-chip" data-rpe="{value}" aria-pressed="{"true" if value == selected_rpe else "false"}">{html.escape(label)}</button>'
        for value, label in rpe
    )
    feeling_html = "".join(
        f'<button type="button" class="training-input-chip" data-feeling="{html.escape(key)}" aria-pressed="{"true" if key in selected_feelings else "false"}">{html.escape(label)}</button>'
        for key, label in feelings
    )

    return f"""{BLOCK_START}
<section class="training-input" data-training-input data-activity-id="{activity_id}" data-reviewed="{"true" if reviewed else "false"}" data-processed-event-keys="{html.escape(processed_event_keys_attr, quote=True)}" aria-label="Ändra eller utvärdera genomfört pass">
  <div class="training-input-compact">
    <div>
      <div class="training-input-title-row">
        <span class="training-input-title">{html.escape(activity_label)}</span>
        <span class="training-input-date">{html.escape(activity_date)}</span>
      </div>
      <div class="training-input-summary" data-training-input-summary>{html.escape(summary)}</div>
      <div class="training-input-note" data-training-input-note>{html.escape(note)}</div>
      <div class="training-input-status" data-training-input-status aria-live="polite"></div>
    </div>
    <button type="button" class="training-input-toggle" data-training-input-toggle>Ändra</button>
  </div>
  <div class="training-input-editor" data-training-input-editor hidden>
    <span class="training-input-label">Ansträngning</span>
    <div class="training-input-options">{rpe_html}</div>
    <span class="training-input-label">Känsla</span>
    <div class="training-input-options">{feeling_html}</div>
    <span class="training-input-label">Kommentar eller korrigering av passet</span>
    <textarea maxlength="800" placeholder="Kommentar om känslan, eller korrigera vad som faktiskt genomfördes.">{html.escape(note)}</textarea>
    <div class="training-input-actions">
      <button type="button" class="training-input-save" data-training-input-save>Spara</button>
      <button type="button" class="training-input-cancel" data-training-input-cancel>Avbryt</button>
    </div>
  </div>
</section>
{BLOCK_END}"""


def apply_training_input_ui(
    page: str,
    plan: dict,
    activities_state: dict,
    today: str,
    overrides_state: dict | None = None,
) -> str:
    page = remove_existing(page)
    today_date = datetime.strptime(today, "%Y-%m-%d").date()
    override_map = (overrides_state or {}).get("overrides") or {}

    def override_for(activity: dict) -> dict:
        return override_map.get(str(activity.get("id"))) or {}

    def processed_event_keys(activity: dict) -> list[str]:
        row = override_for(activity)
        values = row.get("training_input_event_keys") or []
        if not isinstance(values, list):
            values = []
        keys = [
            str(value).strip()
            for value in values
            if re.fullmatch(r"training-input:[0-9a-f]{24}", str(value).strip())
        ]
        legacy = str(row.get("last_training_input_event_key") or "").strip()
        if re.fullmatch(r"training-input:[0-9a-f]{24}", legacy) and legacy not in keys:
            keys.append(legacy)
        return keys[-8:]

    week_start = today_date - timedelta(days=today_date.weekday())
    current_week = []
    for activity in activities_state.get("activities") or []:
        if not isinstance(activity.get("id"), int):
            continue
        value = local_date(activity)
        if not value:
            continue
        try:
            activity_date = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            continue
        if week_start <= activity_date <= today_date:
            current_week.append(activity)
    current_week.sort(
        key=lambda activity: str(activity.get("start_date_local") or ""),
        reverse=True,
    )

    primary = None
    if 'class="today-outcome"' in page:
        day = next((item for item in plan.get("days") or [] if item.get("date") == today), None)
        if day:
            today_activities = [
                activity
                for activity in current_week
                if local_date(activity) == today
            ]
            primary = matching_activity(day, today_activities)

    rendered_ids = set()
    if primary and isinstance(primary.get("id"), int):
        link = '<a class="today-outcome-link"'
        pos = page.find(link)
        if pos < 0:
            raise RuntimeError("Träningsinput UI: post-workout-länken saknas.")
        page = page[:pos] + render_block(
            primary,
            processed_event_keys(primary),
            feedback_from_override(override_for(primary)),
        ) + "\n" + page[pos:]
        rendered_ids.add(primary["id"])

    secondary = [
        activity for activity in current_week
        if activity.get("id") not in rendered_ids
    ]
    if secondary:
        marker = "<!-- training-brain-v1:end -->"
        pos = page.find(marker)
        if pos < 0:
            raise RuntimeError("Träningsinput UI: träningshjärnans slutmarkör saknas.")
        pos += len(marker)
        blocks = "\n".join(
            render_block(
                activity,
                processed_event_keys(activity),
                feedback_from_override(override_for(activity)),
            )
            for activity in secondary
        )
        page = page[:pos] + "\n" + blocks + page[pos:]

    if not rendered_ids and not secondary:
        return page

    if "</style>" not in page:
        raise RuntimeError("Träningsinput UI: </style> saknas.")
    page = page.replace("</style>", CSS + "\n</style>", 1)
    if "</body>" not in page:
        raise RuntimeError("Träningsinput UI: </body> saknas.")
    page = page.replace("</body>", "<script>\n" + JS + "\n</script>\n</body>", 1)
    return page


def main() -> int:
    plan = load_json(PLAN_FILE, {"days": [], "meta": {}})
    upcoming = load_json(UPCOMING_FILE, {"days": [], "meta": {}})
    decision_plan = planning_window(plan, upcoming)
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    overrides = load_json(OVERRIDES_FILE, {"schema_version": 1, "overrides": {}})
    page = INDEX_FILE.read_text(encoding="utf-8")
    tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
    today = datetime.now(tz).date().isoformat()
    rendered = apply_training_input_ui(
        page,
        decision_plan,
        activities,
        today,
        overrides_state=overrides,
    )
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    print("Träningsinput UI OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
