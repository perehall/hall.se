#!/usr/bin/env python3
"""Add a non-critical live Supabase backend-status probe to system info.

The browser receives only the public Supabase publishable key. No database
password, secret/service-role key, table endpoint or training content is
embedded. The RPC itself is a sanitized SECURITY DEFINER function.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
WEEK_DIR = ROOT / "vecka"
GOAL_PAGE = ROOT / "malbild" / "index.html"
GOAL_PUBLIC_PAGE = ROOT / "malbild-2027" / "index.html"

PROJECT_URL = "https://izzevnhgtsvffpkccoai.supabase.co"
RPC_URL = PROJECT_URL + "/rest/v1/rpc/training_backend_status"
START = "<!-- backend-status-ui-v1:start -->"
END = "<!-- backend-status-ui-v1:end -->"


def page_paths() -> list[Path]:
    paths = [INDEX_FILE]
    if WEEK_DIR.exists():
        paths.extend(sorted(WEEK_DIR.glob("*/index.html")))
    paths.extend([GOAL_PAGE, GOAL_PUBLIC_PAGE])
    unique: list[Path] = []
    for path in paths:
        if path.exists() and path not in unique:
            unique.append(path)
    return unique


def replace_existing(page: str, row: str, script: str) -> str | None:
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END),
        flags=re.S,
    )
    matches = list(pattern.finditer(page))
    if not matches:
        return None
    if len(matches) != 2:
        raise RuntimeError(
            f"Backendstatus: väntade 2 markerade block, hittade {len(matches)}"
        )
    replacements = iter((row, script))
    return pattern.sub(lambda _match: next(replacements), page, count=2)


def status_markup(publishable_key: str) -> tuple[str, str]:
    key_js = json.dumps(publishable_key)
    rpc_js = json.dumps(RPC_URL)

    row = f'''{START}
<li class="backend-status-row" data-backend-status-row>
  <strong>Backend:</strong> <span data-training-backend-status>Kontrollerar Supabase…</span>
</li>
{END}'''

    script = f'''{START}
<script>
(function() {{
  const row = document.querySelector('[data-backend-status-row]');
  const target = document.querySelector('[data-training-backend-status]');
  if (!row || !target) return;

  const publishableKey = {key_js};
  const endpoint = {rpc_js};
  if (!publishableKey) {{
    row.hidden = true;
    return;
  }}

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);

  fetch(endpoint, {{
    method: 'POST',
    headers: {{
      'apikey': publishableKey,
      'Content-Type': 'application/json'
    }},
    body: '{{}}',
    cache: 'no-store',
    signal: controller.signal
  }})
    .then((response) => {{
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }})
    .then((data) => {{
      if (!data || data.status !== 'ok') {{
        target.textContent = 'Supabase · avvikelse';
        return;
      }}
      target.textContent = 'Supabase · OK';
      const details = [];
      if (Number.isInteger(data.current_workouts)) {{
        details.push(data.current_workouts + ' aktuella pass');
      }}
      if (data.snapshot) details.push('snapshot ' + data.snapshot);
      if (data.last_sync_at) {{
        const when = new Date(data.last_sync_at);
        if (!Number.isNaN(when.getTime())) {{
          details.push('synkad ' + when.toLocaleString('sv-SE'));
        }}
      }}
      if (details.length) target.title = details.join(' · ');
    }})
    .catch(() => {{
      target.textContent = 'Supabase · status ej tillgänglig';
    }})
    .finally(() => clearTimeout(timeout));
}})();
</script>
{END}'''
    return row, script


def patch_page(page: str, publishable_key: str) -> str:
    row, script = status_markup(publishable_key)
    existing = replace_existing(page, row, script)
    if existing is not None:
        return existing

    dialog = re.search(
        r'(<dialog id="trainingSystemSheet"(?:\s[^>]*)?>.*?</dialog>)',
        page,
        flags=re.S,
    )
    if not dialog:
        raise RuntimeError("Backendstatus: systemdialog saknas")

    block = dialog.group(1)
    list_match = re.search(r'(<ul class="system-list">.*?)(</ul>)', block, flags=re.S)
    if not list_match:
        raise RuntimeError("Backendstatus: systemlistan saknas")

    list_prefix = block[: list_match.start(1)]
    list_body = list_match.group(1).rstrip()
    list_suffix = block[list_match.start(2) :]
    patched_block = (
        list_prefix
        + list_body
        + "\n      "
        + row
        + "\n    "
        + list_suffix
    )

    page = page[: dialog.start()] + patched_block + script + page[dialog.end() :]
    return page


def main() -> int:
    publishable_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()

    paths = page_paths()
    if not paths:
        raise RuntimeError("Backendstatus: inga träningssidor hittades")

    for path in paths:
        rendered = patch_page(path.read_text(encoding="utf-8"), publishable_key)
        path.write_text(rendered, encoding="utf-8")

        verify = path.read_text(encoding="utf-8")
        if verify.count(START) != 2 or verify.count(END) != 2:
            raise RuntimeError(f"Backendstatus {path}: markörerna är inte idempotenta")
        if "SUPABASE_DB_URL" in verify or "sb_secret_" in verify:
            raise RuntimeError(f"Backendstatus {path}: serverhemlighet har läckt till HTML")
        if publishable_key and publishable_key not in verify:
            raise RuntimeError(f"Backendstatus {path}: publishable key saknas")
        if not publishable_key and 'row.hidden = true' not in verify:
            raise RuntimeError(f"Backendstatus {path}: säker fallback saknas")

    state = "aktiv" if publishable_key else "inaktiv utan SUPABASE_PUBLISHABLE_KEY"
    print(f"Supabase live-backendstatus OK: {len(paths)} sidor · {state}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
