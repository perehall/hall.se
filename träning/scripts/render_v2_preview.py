#!/usr/bin/env python3
"""Publish a human-verifiable architecture-v2 preview without cutting over production."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v2_presentation_probe import build_snapshot  # noqa: E402
from training_core.presentation.renderer import render_document  # noqa: E402


PREVIEW_DIR = ROOT / "v2-preview"
PREVIEW_FILE = PREVIEW_DIR / "index.html"


def render_preview(*, today=None, snapshot_builder=build_snapshot):
    local_date = today or datetime.now(ZoneInfo("Europe/Stockholm")).date()
    snapshot = snapshot_builder(local_date)
    document = render_document(snapshot, title="Träning · v2-förhandsvisning")
    required = ('class="v2-shell"', 'class="v2-today"', 'class="v2-week-context"')
    missing = [marker for marker in required if marker not in document]
    if missing:
        raise RuntimeError("V2 preview saknar obligatorisk struktur: " + ", ".join(missing))
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_FILE.write_text(document, encoding="utf-8")
    print(f"V2_PREVIEW_OK {PREVIEW_FILE.relative_to(ROOT.parent)} date={local_date.isoformat()}")
    return document


def main():
    render_preview()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
