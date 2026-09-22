#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def humanize_rest_day_language(page: str) -> str:
    page = page.replace(">Ingen planerad träning<", ">Vilodag<")
    page = page.replace(" · Ingen planerad träning</strong>", " · Vilodag</strong>")
    return page


def targets():
    paths = [ROOT / "index.html"]
    archive = ROOT / "vecka"
    if archive.exists():
        paths.extend(sorted(archive.glob("*/index.html")))
    return [path for path in paths if path.exists()]


def main() -> int:
    changed = 0
    for path in targets():
        page = path.read_text(encoding="utf-8")
        rendered = humanize_rest_day_language(page)
        if rendered != page:
            path.write_text(rendered, encoding="utf-8")
            changed += 1
    print(f"Vilodagsspråk OK: {changed} sida/sidor uppdaterade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
