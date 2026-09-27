#!/usr/bin/env python3
"""Canonical v2 publisher for the current training page.

The current page is rendered once from canonical PostgreSQL state. Legacy HTML
mutation is intentionally excluded from production publication after the v2
cutover; historical/goal maintenance remains owned by its dedicated workflows.
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def publish_v2_current_page():
    sys.path.insert(0, str(ROOT))
    from v2_presentation_probe import build_snapshot
    from training_core.presentation.cutover import cutover_ready
    from training_core.presentation.renderer import render_document

    if not cutover_ready():
        raise RuntimeError("V2 publication blocked by cutover contract")
    snapshot = build_snapshot(date.today())
    document = render_document(snapshot)
    if not document.startswith("<!doctype html>"):
        raise RuntimeError("V2 publication did not produce a complete document")
    target = ROOT / "index.html"
    target.write_text(document, encoding="utf-8")
    print("V2_PUBLICATION_OK träning/index.html", flush=True)


def main():
    publish_v2_current_page()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
