#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cutover_contract_ready():
    sys.path.insert(0, str(ROOT))
    from training_core.presentation.cutover import cutover_ready

    return cutover_ready()


def publish_v2_current_page():
    """Publish production directly from canonical PostgreSQL presentation state."""
    sys.path.insert(0, str(ROOT))
    from v2_presentation_probe import build_snapshot
    from training_core.presentation.renderer import render_document
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if not cutover_contract_ready():
        raise RuntimeError("V2 publication blocked by cutover contract")

    local_date = datetime.now(ZoneInfo("Europe/Stockholm")).date()
    snapshot = build_snapshot(local_date)
    document = render_document(snapshot)
    required = (
        "<!doctype html>",
        'class="v2-shell"',
        'class="v2-today"',
        'class="v2-week-context"',
    )
    missing = [marker for marker in required if marker not in document]
    if missing:
        raise RuntimeError(
            "V2 publication missing required structure: " + ", ".join(missing)
        )

    target = ROOT / "index.html"
    target.write_text(document, encoding="utf-8")
    print(
        f"V2_PUBLICATION_OK träning/index.html date={local_date.isoformat()}",
        flush=True,
    )


def main():
    # The v2 cutover is complete. Production must fail closed rather than
    # falling back to legacy HTML mutators that can rewrite canonical state.
    publish_v2_current_page()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
