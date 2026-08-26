#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
DAY_RE = re.compile(r'<div class="day(?P<classes>[^"]*)" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">')
COACH_MARKER = '<div class="coach yoda-v2">'


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


def wrap_past_coaches(page):
    ranges = day_ranges(page)
    for start, end, match in reversed(ranges):
        classes = set((match.group("classes") or "").split())
        if "past-completed" not in classes:
            continue
        block = page[start:end]
        if 'class="historical-coach"' in block:
            continue
        coach_start = block.find(COACH_MARKER)
        if coach_start < 0:
            continue
        coach_end = balanced_div_end(block, coach_start)
        if coach_end is None:
            raise RuntimeError(f"Historisk coach: kunde inte avgränsa coachblock för {match.group('date')}")
        coach = block[coach_start:coach_end]
        wrapped = (
            '<details class="historical-coach">'
            '<summary>AI-analys · historik</summary>'
            f'{coach}'
            '</details>'
        )
        block = block[:coach_start] + wrapped + block[coach_end:]
        page = page[:start] + block + page[end:]
    return page


def validate(page):
    for start, end, match in day_ranges(page):
        classes = set((match.group("classes") or "").split())
        if "past-completed" not in classes:
            continue
        block = page[start:end]
        if COACH_MARKER in block and 'class="historical-coach"' not in block:
            raise RuntimeError(f"Historisk coach: aktiv coachtext läcker på genomförd dag {match.group('date')}")


def main():
    page = INDEX_FILE.read_text(encoding="utf-8")
    rendered = wrap_past_coaches(page)
    validate(rendered)
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    print("Historisk coach OK: gamla AI-råd är infällda och kan inte se aktiva ut.")


if __name__ == "__main__":
    main()
