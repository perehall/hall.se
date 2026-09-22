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
.training-input{margin-top:16px;padding-top:15px;border-top:1px solid var(--qp-line,#e2e8f0)}
.training-input h3{margin:0 0 5px;font-size:.95rem;color:var(--qp-text,#111827)}
.training-input-intro{margin:0 0 12px;color:var(--qp-secondary,#5e6661);font-size:.8rem;line-height:1.4}
.training-input-label{display:block;margin:10px 0 6px;color:var(--qp-text-label,#475569);font-size:.68rem;font-weight:850;letter-spacing:.055em;text-transform:uppercase}
.training-input-options{display:flex;flex-wrap:wrap;gap:6px}
.training-input-chip{appearance:none;border:1px solid var(--qp-line,#d9dedb);background:transparent;color:var(--qp-secondary,#5e6661);border-radius:999px;padding:7px 10px;font:inherit;font-size:.76rem;cursor:pointer}
.training-input-chip[aria-pressed="true"]{border-color:var(--qp-accent,#5964e8);color:var(--qp-accent,#5964e8);box-shadow:inset 0 0 0 1px var(--qp-accent,#5964e8)}
.training-input textarea{width:100%;min-height:72px;resize:vertical;border:1px solid var(--qp-line,#d9dedb);border-radius:10px;background:transparent;color:var(--qp-text,#111827);padding:9px 10px;font:inherit;font-size:.82rem;line-height:1.4}
.training-input-actions{display:flex;align-items:center;gap:10px;margin-top:8px}
.training-input-save{appearance:none;border:0;border-radius:9px;background:var(--qp-accent,#5964e8);color:#fff;padding:8px 12px;font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}
.training-input-save:disabled{opacity:.55;cursor:default}
.training-input-status{color:var(--qp-secondary,#5e6661);font-size:.75rem}
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

  async function waitForProcessed(activityId, eventKey) {
    for (let attempt = 0; attempt < 90; attempt += 1) {
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
        if (fresh && fresh.dataset.processedEventKey === eventKey) return true;
      } catch (error) {
        console.debug('TRAINING_INPUT_POLL_RETRY', error);
      }
    }
    return false;
  }

  roots.forEach((root) => {
    const rpeButtons = [...root.querySelectorAll('[data-rpe]')];
    const feelingButtons = [...root.querySelectorAll('[data-feeling]')];
    const text = root.querySelector('textarea');
    const save = root.querySelector('[data-training-input-save]');
    const status = root.querySelector('[data-training-input-status]');
    let rpe = null;
    const feelings = new Set();

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
      const note = text.value.trim();
      if (!note && rpe === null && feelings.size === 0) {
        status.textContent = 'Välj en känsla eller skriv en kort kommentar.';
        return;
      }

      let operation = note ? 'NATURAL_LANGUAGE' : 'ADD_FEEDBACK';
      if (!note && feelings.has('pain')) operation = 'REPORT_PAIN';
      else if (!note && feelings.has('tired')) operation = 'REPORT_FATIGUE';

      save.disabled = true;
      status.textContent = 'Sparar…';
      try {
        const response = await fetch('/träning/training-api/input', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'content-type': 'application/json'},
          body: JSON.stringify({
            operation,
            activity_id: Number(root.dataset.activityId),
            text: note,
            rpe,
            feeling: [...feelings],
            source: 'training-gui-v1'
          })
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || 'request_failed');
        if (!body.event_key) throw new Error('missing_event_key');

        status.textContent = 'Mottaget. Bearbetar…';
        text.value = '';
        rpe = null;
        feelings.clear();
        [...rpeButtons, ...feelingButtons].forEach((button) => button.setAttribute('aria-pressed', 'false'));

        const processed = await waitForProcessed(root.dataset.activityId, body.event_key);
        if (processed) {
          status.textContent = 'Klart. Uppdaterar…';
          const next = new URL(window.location.href);
          next.searchParams.set('_feedback_done', String(Date.now()));
          window.location.replace(next.toString());
          return;
        }

        status.textContent = 'Sparat. Automatisk uppdatering kunde inte bekräftas.';
        save.disabled = false;
      } catch (error) {
        status.textContent = `Kunde inte spara (${error.message}).`;
        save.disabled = false;
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


def render_block(activity: dict, processed_event_key: str = "") -> str:
    activity_id = int(activity["id"])
    activity_label = (
        str(activity.get("display_label") or "").strip()
        or str(activity.get("name") or "").strip()
        or str(activity.get("sport_type") or "").strip()
        or "Genomfört pass"
    )
    activity_date = local_date(activity) or ""
    rpe = [
        (2, "Mycket lätt"),
        (4, "Lätt"),
        (6, "Lagom"),
        (8, "Tungt"),
        (10, "För tungt"),
    ]
    feelings = [
        ("fresh", "Pigg"),
        ("tired", "Trött"),
        ("strong_legs", "Starka ben"),
        ("heavy_legs", "Tunga ben"),
        ("pain", "Smärta"),
        ("could_do_more", "Kunde gjort mer"),
    ]
    rpe_html = "".join(
        f'<button type="button" class="training-input-chip" data-rpe="{value}" aria-pressed="false">{html.escape(label)}</button>'
        for value, label in rpe
    )
    feeling_html = "".join(
        f'<button type="button" class="training-input-chip" data-feeling="{html.escape(key)}" aria-pressed="false">{html.escape(label)}</button>'
        for key, label in feelings
    )
    return f"""{BLOCK_START}
<section class="training-input" data-training-input data-activity-id="{activity_id}" data-processed-event-key="{html.escape(processed_event_key, quote=True)}" aria-label="Feedback efter pass">
  <h3>Feedback · {html.escape(activity_label)}</h3>
  <p class="training-input-intro">{html.escape(activity_date)} · Snabbval räcker. Fri text kan också korrigera vad du faktiskt gjorde; modellen får bara klassificera inputen, inte ändra planen direkt.</p>
  <span class="training-input-label">Ansträngning</span>
  <div class="training-input-options">{rpe_html}</div>
  <span class="training-input-label">Känsla</span>
  <div class="training-input-options">{feeling_html}</div>
  <span class="training-input-label">Kommentar eller ändring</span>
  <textarea maxlength="800" placeholder="T.ex. Blev 4 × 8 i stället för 3 × 10. Kändes kontrollerat och jag var pigg efteråt."></textarea>
  <div class="training-input-actions">
    <button type="button" class="training-input-save" data-training-input-save>Spara</button>
    <span class="training-input-status" data-training-input-status aria-live="polite"></span>
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

    def processed_event_key(activity: dict) -> str:
        row = override_map.get(str(activity.get("id"))) or {}
        return str(row.get("last_training_input_event_key") or "").strip()

    recent = []
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
        age_days = (today_date - activity_date).days
        if 0 <= age_days <= 1:
            recent.append(activity)
    recent.sort(key=lambda activity: str(activity.get("start_date_local") or ""), reverse=True)

    primary = None
    if 'class="today-outcome"' in page:
        day = next((item for item in plan.get("days") or [] if item.get("date") == today), None)
        if day:
            today_activities = [
                activity
                for activity in recent
                if local_date(activity) == today
            ]
            primary = matching_activity(day, today_activities)

    rendered_ids = set()
    if primary and isinstance(primary.get("id"), int):
        link = '<a class="today-outcome-link"'
        pos = page.find(link)
        if pos < 0:
            raise RuntimeError("Träningsinput UI: post-workout-länken saknas.")
        page = page[:pos] + render_block(primary, processed_event_key(primary)) + "\n" + page[pos:]
        rendered_ids.add(primary["id"])

    secondary = [
        activity for activity in recent
        if activity.get("id") not in rendered_ids
    ][:3]
    if secondary:
        marker = "<!-- training-brain-v1:end -->"
        pos = page.find(marker)
        if pos < 0:
            raise RuntimeError("Träningsinput UI: träningshjärnans slutmarkör saknas.")
        pos += len(marker)
        blocks = "\n".join(
            render_block(activity, processed_event_key(activity))
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
