#!/usr/bin/env python3
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SOURCE = ROOT / "malbild" / "index.html"
TARGET_DIR = ROOT / "malbild-2027"
TARGET = TARGET_DIR / "index.html"

TRAIL_D = (
    "M104 250 "
    "C146 247 179 239 211 226 "
    "C240 214 260 198 279 181 "
    "C299 163 319 153 339 155 "
    "C360 157 373 169 393 158 "
    "C414 147 422 132 439 125 "
    "C456 118 469 119 482 113"
)

# Progress along the SVG path is the source of truth. Fallback x/y values are
# only used before JS runs; JS immediately replaces them from getPointAtLength().
PHASE_MARKERS = {
    1: (0.03, 20.0, 82.0),
    2: (0.28, 39.0, 72.0),
    3: (0.52, 57.0, 55.0),
    4: (0.76, 72.0, 49.0),
    5: (0.97, 85.0, 38.0),
}

SCRIPT_MARKER = "<!-- phase-trail-sync-v1 -->"


def patch_route(page: str, path: Path) -> str:
    white = (
        f'<path id="phase-trail-underlay" d="{TRAIL_D}" fill="none" '
        'stroke="#fff" stroke-width="8" stroke-linecap="round" opacity=".85"/>'
    )
    purple = (
        f'<path id="phase-trail" d="{TRAIL_D}" fill="none" '
        'stroke="url(#trail)" stroke-width="3.4" stroke-linecap="round" stroke-dasharray="8 9"/>'
    )

    page, n_white = re.subn(
        r'<path(?: id="phase-trail-underlay")? d="[^"]+" fill="none" '
        r'stroke="#fff" stroke-width="8" stroke-linecap="round" opacity="\.85"/>',
        white,
        page,
        count=1,
    )
    page, n_purple = re.subn(
        r'<path(?: id="phase-trail")? d="[^"]+" fill="none" '
        r'stroke="url\(#trail\)" stroke-width="3\.4" stroke-linecap="round" stroke-dasharray="8 9"/>',
        purple,
        page,
        count=1,
    )
    if n_white != 1 or n_purple != 1:
        raise RuntimeError(
            f"Målbild: kunde inte identifiera båda stiglagren i {path} "
            f"(vit={n_white}, lila={n_purple})"
        )

    flag = (
        '<circle cx="482" cy="113" r="17" fill="#eeecff" opacity=".72"/>'
        '<line x1="482" y1="83" x2="482" y2="114" stroke="#4938ee" stroke-width="3"/>'
        '<path d="M482 83 L507 92 L482 101Z" fill="#4938ee"/>'
    )
    # The preceding layout finalizer may already have moved/recolored the flag.
    # Match the semantic flag trio rather than a specific old geometry.
    flag_pattern = (
        r'<circle cx="[^"]+" cy="[^"]+" r="[^"]+" fill="#[0-9a-fA-F]{6}" opacity="[^"]+"/>'
        r'<line x1="[^"]+" y1="[^"]+" x2="[^"]+" y2="[^"]+" '
        r'stroke="#4938ee" stroke-width="3"/>'
        r'<path d="M[^"]+Z" fill="#4938ee"/>'
    )
    page, n_flag = re.subn(flag_pattern, flag, page, count=1)
    if n_flag != 1:
        raise RuntimeError(f"Målbild: kunde inte identifiera flaggan i {path}")
    return page


def patch_markers(page: str, path: Path) -> str:
    for phase, (progress, x, y) in PHASE_MARKERS.items():
        pattern = re.compile(
            rf'(<a class="mountain-phase-point [^"]+" href="#fas-{phase}") '
            rf'style="[^"]*" data-phase="{phase}"(?: data-progress="[^"]+")?'
        )
        replacement = (
            rf'\1 style="--x:{x}%;--y:{y}%" data-phase="{phase}" '
            rf'data-progress="{progress:.2f}"'
        )
        page, count = pattern.subn(replacement, page, count=1)
        if count != 1:
            raise RuntimeError(f"Målbild: fasmarkör {phase} kunde inte bindas till stigen i {path}")

    # Idempotent: replace an older copy of our own positioning script if present.
    page = re.sub(
        rf'{re.escape(SCRIPT_MARKER)}.*?{re.escape(SCRIPT_MARKER)}',
        '',
        page,
        flags=re.S,
    )

    sync_script = f'''{SCRIPT_MARKER}
<script>
(() => {{
  const syncPhaseMarkers = () => {{
    const trail = document.getElementById('phase-trail');
    if (!trail) return;
    const svg = trail.ownerSVGElement;
    if (!svg || !svg.viewBox || !svg.viewBox.baseVal) return;
    const vb = svg.viewBox.baseVal;
    if (!vb.width || !vb.height) return;
    const total = trail.getTotalLength();
    document.querySelectorAll('.mountain-phase-point[data-progress]').forEach((marker) => {{
      const progress = Number.parseFloat(marker.dataset.progress || '0');
      const point = trail.getPointAtLength(total * Math.max(0, Math.min(1, progress)));
      marker.style.setProperty('--x', `${{((point.x - vb.x) / vb.width) * 100}}%`);
      marker.style.setProperty('--y', `${{((point.y - vb.y) / vb.height) * 100}}%`);
    }});
  }};
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', syncPhaseMarkers, {{once:true}});
  }} else {{
    syncPhaseMarkers();
  }}
  window.addEventListener('resize', syncPhaseMarkers, {{passive:true}});
}})();
</script>
{SCRIPT_MARKER}'''

    if "</body>" not in page:
        raise RuntimeError(f"Målbild: </body> saknas i {path}")
    page = page.replace("</body>", sync_script + "\n</body>", 1)
    return page


def patch_goal_page(path: Path) -> None:
    page = path.read_text(encoding="utf-8")
    page = patch_route(page, path)
    page = patch_markers(page, path)
    path.write_text(page, encoding="utf-8")

    rendered = path.read_text(encoding="utf-8")
    required = [
        'id="phase-trail"',
        TRAIL_D,
        'data-progress="0.28"',
        'data-progress="0.97"',
        "getPointAtLength",
        SCRIPT_MARKER,
    ]
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError(f"Målbild: stig/plupp-validering misslyckades i {path}: {missing!r}")
    if rendered.count('class="mountain-phase-point') != 5:
        raise RuntimeError(f"Målbild: förväntade exakt fem fasmarkörer i {path}")


def main():
    if not SOURCE.exists():
        raise RuntimeError("Cache-bypass: målbildssidan saknas")

    # First finalize the canonical goal page, then publish exactly that page on
    # the cache-bypass route so both URLs contain identical mountain geometry.
    patch_goal_page(SOURCE)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, TARGET)
    patch_goal_page(TARGET)

    page = INDEX.read_text(encoding="utf-8")
    page = page.replace('href="/träning/malbild/"', 'href="/träning/malbild-2027/"')
    INDEX.write_text(page, encoding="utf-8")

    rendered = TARGET.read_text(encoding="utf-8")
    required = ["mountain-phase-point", 'href="#fas-2"', "Målbild 2027", 'id="phase-trail"']
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError("Cache-bypass: målbilden saknar interaktiva markörer: " + repr(missing))
    if 'href="/träning/malbild-2027/"' not in INDEX.read_text(encoding="utf-8"):
        raise RuntimeError("Cache-bypass: huvudsidan länkar inte till nya målbildsvägen")
    print("Målbild OK: kurvad bergsstig och fem fasmarkörer bundna direkt till SVG-pathen.")


if __name__ == "__main__":
    main()
