#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def clean_file(path):
    text = path.read_text(encoding="utf-8")
    had_final_newline = text.endswith("\n")
    cleaned = "\n".join(line.rstrip() for line in text.splitlines())
    if had_final_newline:
        cleaned += "\n"
    if cleaned != text:
        path.write_text(cleaned, encoding="utf-8")
        return True
    return False


def main():
    candidates = []
    for path in (
        ROOT / "index.html",
        ROOT / "malbild" / "index.html",
        ROOT / "malbild-2027" / "index.html",
    ):
        if path.exists():
            candidates.append(path)
    weeks = ROOT / "vecka"
    if weeks.exists():
        candidates.extend(sorted(weeks.rglob("*.html")))

    changed = sum(1 for path in candidates if clean_file(path))
    print(f"HTML-whitespace OK: {changed} fil(er) normaliserade.")


if __name__ == "__main__":
    main()
