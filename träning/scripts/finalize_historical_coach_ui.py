#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
DAY_RE = re.compile(r'<div class="day(?P<classes>[^"]*)" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">')
COACH_MARKER = '<div class="coach yoda-v2">'
EMPTY_HISTORICAL_RE = re.compile(
    r'<details class="historical-coach">\s*'
    r'<summary>AI-analys · historik</summary>\s*'
    r'</details>',
    re.S,
)


def balanced_div_end(text, start):
    tag_re = re.compile(r'<div\b[^>]*>|</div>')
    depth = 0
    for match in tag_re.finditer(text, start):
        if match.group(0).startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.end()
    return None


def day_ranges(page):
    matches = list(DAY_RE.finditer(page))
    ranges = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
        ranges.append((match.start(), end, match))
    return ranges


def strip_past_coaches(page):
    """Past sessions show the distilled insight only; raw coach machinery is removed."""
    for start, end, match in reversed(day_ranges(page)):
        classes = set((match.group("classes") or "").split())
        if "past-completed" not in classes:
            continue
        block = page[start:end]

        while True:
            coach_start = block.find(COACH_MARKER)
            if coach_start < 0:
                break
            coach_end = balanced_div_end(block, coach_start)
            if coach_end is None:
                raise RuntimeError(
                    f"Historisk coach: kunde inte avgränsa coachblock för {match.group('date')}"
                )
            block = block[:coach_start] + block[coach_end:]

        # Compatibility cleanup for pages rendered by the former nested-accordion model.
        block = EMPTY_HISTORICAL_RE.sub("", block)
        page = page[:start] + block + page[end:]
    return page


def wrap_past_coaches(page):
    # Backward-compatible function name used by older tests/callers.
    return strip_past_coaches(page)


def validate(page):
    for start, end, match in day_ranges(page):
        classes = set((match.group("classes") or "").split())
        if "past-completed" not in classes:
            continue
        block = page[start:end]
        if COACH_MARKER in block or 'class="historical-coach"' in block:
            raise RuntimeError(
                f"Historisk coach: rå coach-UI läcker på genomförd dag {match.group('date')}"
            )


def main():
    page = INDEX_FILE.read_text(encoding="utf-8")
    rendered = strip_past_coaches(page)
    validate(rendered)
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    print("Historisk coach OK: rå coach-UI är borttagen; endast destillerad passinsikt visas.")


if __name__ == "__main__":
    main()
