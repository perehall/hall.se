#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SOURCE = ROOT / "malbild" / "index.html"
TARGET_DIR = ROOT / "malbild-2027"
TARGET = TARGET_DIR / "index.html"


def validate_goal(page: str, label: str) -> None:
    required = [
        "Målbild 2027",
        'data-goal-hierarchy="true"',
        'data-current-mesocycle="true"',
        "Så styr målbilden träningen",
        "Aktuell utvecklingsväg",
        "Beslutsprinciper",
        "När målbilden ändras",
        "← Veckoplan",
    ]
    missing = [item for item in required if item not in page]
    if missing:
        raise RuntimeError(f"Målbild: {label} saknar kontrakt: {missing!r}")
    forbidden = [
        "mountain-phase-point",
        "phase-trail",
        "Faser och periodisering",
        "Kvalitativ utvecklingsstatus",
    ]
    leaked = [item for item in forbidden if item in page]
    if leaked:
        raise RuntimeError(f"Målbild: {label} innehåller gammal fas/status-UX: {leaked!r}")


def main() -> None:
    if not SOURCE.exists():
        raise RuntimeError("Målbild: canonical sida saknas")

    canonical = SOURCE.read_text(encoding="utf-8")
    validate_goal(canonical, "canonical")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, TARGET)
    mirrored = TARGET.read_text(encoding="utf-8")
    validate_goal(mirrored, "cache-bypass")
    if mirrored != canonical:
        raise RuntimeError("Målbild: cache-bypass-sidan är inte identisk med canonical")

    index = INDEX.read_text(encoding="utf-8")
    if 'href="/träning/malbild-2027/"' not in index:
        raise RuntimeError("Målbild: huvudsidan länkar inte till publicerad målbildsväg")

    print("Målbild OK: canonical och /malbild-2027/ är identiska och följer systemhierarkin.")


if __name__ == "__main__":
    main()
