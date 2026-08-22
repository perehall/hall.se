#!/usr/bin/env python3
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SOURCE = ROOT / "malbild" / "index.html"
TARGET_DIR = ROOT / "malbild-2027"
TARGET = TARGET_DIR / "index.html"


def main():
    if not SOURCE.exists():
        raise RuntimeError("Cache-bypass: målbildssidan saknas")
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, TARGET)

    page = INDEX.read_text(encoding="utf-8")
    page = page.replace('href="/träning/malbild/"', 'href="/träning/malbild-2027/"')
    INDEX.write_text(page, encoding="utf-8")

    rendered = TARGET.read_text(encoding="utf-8")
    required = ["mountain-phase-point", 'href="#fas-2"', "Målbild 2027"]
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError("Cache-bypass: målbilden saknar interaktiva markörer: " + repr(missing))
    if 'href="/träning/malbild-2027/"' not in INDEX.read_text(encoding="utf-8"):
        raise RuntimeError("Cache-bypass: huvudsidan länkar inte till nya målbildsvägen")
    print("Cache-bypass OK: /träning/malbild-2027/ publicerad och länkad.")


if __name__ == "__main__":
    main()
