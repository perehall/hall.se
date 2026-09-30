#!/usr/bin/env python3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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




def publish_v2_upcoming_page(local_date=None):
    """Publish the next planned week from the same canonical PostgreSQL read model."""
    sys.path.insert(0, str(ROOT))
    from v2_presentation_probe import build_snapshot
    from training_core.presentation.navigation import iso_week_key
    from training_core.presentation.renderer import render_document

    if not cutover_contract_ready():
        raise RuntimeError("V2 publication blocked by cutover contract")

    local_date = local_date or datetime.now(ZoneInfo("Europe/Stockholm")).date()
    current_start = local_date - timedelta(days=local_date.weekday())
    upcoming_start = current_start + timedelta(days=7)
    snapshot = build_snapshot(upcoming_start, current_date=local_date)
    if snapshot.week.planned_count <= 0:
        print(
            f"V2_UPCOMING_SKIP week={iso_week_key(upcoming_start)} reason=no_planned_workouts",
            flush=True,
        )
        return None

    document = render_document(snapshot, title=f"Träning · {snapshot.navigation.label}")
    required = (
        "<!doctype html>",
        'class="v2-shell"',
        'class="v2-week-context"',
        "Kommande vecka",
        "· kommande",
    )
    missing = [marker for marker in required if marker not in document]
    if 'class="v2-today"' in document:
        missing.append("future_page_must_not_render_today")
    if missing:
        raise RuntimeError(
            "V2 upcoming publication missing required structure: " + ", ".join(missing)
        )

    key = iso_week_key(upcoming_start)
    target = ROOT / "vecka" / key / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    print(
        f"V2_UPCOMING_PUBLICATION_OK {target.relative_to(ROOT)} week={key}",
        flush=True,
    )
    return target

def main():
    from build_development_page import publish_development_page
    from build_overview_page import publish_overview_page

    # The v2 cutover is complete. Production must fail closed rather than
    # falling back to legacy HTML mutators that can rewrite canonical state.
    publish_v2_current_page()
    publish_v2_upcoming_page()
    publish_overview_page()
    publish_development_page()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
