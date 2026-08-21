#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "index.html"
ARCHIVE_ROOT = ROOT / "vecka"
CSS_MARKER = "/* week-period-emphasis-v1 */"
CSS = """
/* week-period-emphasis-v1 */
.week-period{font-weight:800;color:#334155}
""".strip()

PERIOD_RE = re.compile(
    r'(<div class="sub">)(\d{4}-\d{2}-\d{2}–\d{4}-\d{2}-\d{2})(\s*·)'
)


def update_page(path):
    page = path.read_text(encoding="utf-8")

    if 'class="week-period"' not in page:
        page, count = PERIOD_RE.subn(
            r'\1<strong class="week-period">\2</strong>\3',
            page,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"Header UI: kunde inte markera period i {path}")

    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError(f"Header UI: kunde inte hitta </style> i {path}")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    if 'class="week-period"' not in page or CSS_MARKER not in page:
        raise RuntimeError(f"Header UI-validering misslyckades för {path}")

    path.write_text(page, encoding="utf-8")


def main():
    pages = [CURRENT]
    if ARCHIVE_ROOT.exists():
        pages.extend(sorted(ARCHIVE_ROOT.glob("*/index.html")))

    existing = [path for path in pages if path.exists()]
    if not existing:
        raise RuntimeError("Header UI: inga träningssidor hittades")

    for path in existing:
        update_page(path)

    print(f"Header UI OK: period markerad på {len(existing)} sida/sidor.")


if __name__ == "__main__":
    main()
