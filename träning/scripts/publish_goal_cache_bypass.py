#!/usr/bin/env python3
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SOURCE = ROOT / "malbild" / "index.html"
TARGET_DIR = ROOT / "malbild-2027"
TARGET = TARGET_DIR / "index.html"

# This script is the only post-build owner of mountain geometry/interactions.
# Layout/link finalizers must never rewrite the SVG.
TRAIL_D = (
    "M104 250 "
    "C146 247 179 239 211 226 "
    "C240 214 260 198 279 181 "
    "C299 163 319 153 339 155 "
    "C360 157 373 169 393 158 "
    "C414 147 422 132 439 125 "
    "C456 118 469 119 482 113"
)

PHASE_MARKERS = {
    1: (0.03, 20.0, 82.0),
    2: (0.28, 39.0, 72.0),
    3: (0.52, 57.0, 55.0),
    4: (0.76, 72.0, 49.0),
    5: (0.97, 85.0, 38.0),
}

SCRIPT_MARKER = "<!-- phase-trail-sync-v2 -->"
TOOLTIP_STACKING_MARKER = "/* goal-tooltip-stacking-v1 */"


def patch_route(page: str) -> str:
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
            f"Målbild: kunde inte identifiera exakt ett par stiglager (vit={n_white}, lila={n_purple})"
        )

    flag = (
        '<circle cx="482" cy="113" r="17" fill="#eeecff" opacity=".72"/>'
        '<line x1="482" y1="83" x2="482" y2="114" stroke="#4938ee" stroke-width="3"/>'
        '<path d="M482 83 L507 92 L482 101Z" fill="#4938ee"/>'
    )
    flag_pattern = (
        r'<circle cx="[^"]+" cy="[^"]+" r="[^"]+" fill="#[0-9a-fA-F]{6}" opacity="[^"]+"/>'
        r'<line x1="[^"]+" y1="[^"]+" x2="[^"]+" y2="[^"]+" '
        r'stroke="#4938ee" stroke-width="3"/>'
        r'<path d="M[^"]+Z" fill="#4938ee"/>'
    )
    page, n_flag = re.subn(flag_pattern, flag, page, count=1)
    if n_flag != 1:
        raise RuntimeError("Målbild: kunde inte identifiera exakt en flaggmarkering")
    return page


def patch_markers(page: str) -> str:
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
            raise RuntimeError(f"Målbild: fasmarkör {phase} kunde inte bindas till stigen")

    # Remove any older trail-sync block before inserting the current one.
    page = re.sub(
        r'<!-- phase-trail-sync-v\d+ -->.*?<!-- phase-trail-sync-v\d+ -->',
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
        raise RuntimeError("Målbild: </body> saknas")
    return page.replace("</body>", sync_script + "\n</body>", 1)


def patch_tooltip_stacking(page: str) -> str:
    # Each phase marker is its own stacking context. Raising only the tooltip cannot
    # escape that parent context, so later sibling markers can otherwise paint over it.
    # Raise the entire active marker while hovering/focusing instead.
    page = re.sub(
        r'<style>\s*/\* goal-tooltip-stacking-v\d+ \*/.*?'
        r'/\* goal-tooltip-stacking-v\d+ \*/\s*</style>\s*',
        '',
        page,
        flags=re.S,
    )
    css = f'''<style>
{TOOLTIP_STACKING_MARKER}
.mountain-phase-point:hover,.mountain-phase-point:focus-visible{{z-index:40}}
.mountain-tooltip{{z-index:2}}
{TOOLTIP_STACKING_MARKER}
</style>'''
    if "</head>" not in page:
        raise RuntimeError("Målbild: </head> saknas")
    return page.replace("</head>", css + "\n</head>", 1)


def validate_goal(page: str, label: str) -> None:
    required = [
        'id="phase-trail"',
        'id="phase-trail-underlay"',
        TRAIL_D,
        'data-progress="0.03"',
        'data-progress="0.28"',
        'data-progress="0.52"',
        'data-progress="0.76"',
        'data-progress="0.97"',
        "getPointAtLength",
        SCRIPT_MARKER,
        TOOLTIP_STACKING_MARKER,
        '.mountain-phase-point:hover,.mountain-phase-point:focus-visible{z-index:40}',
        'href="#fas-2"',
        "Målbild 2027",
    ]
    missing = [item for item in required if item not in page]
    if missing:
        raise RuntimeError(f"Målbild: {label} saknar kontrakt: {missing!r}")
    if page.count('class="mountain-phase-point') != 5:
        raise RuntimeError(f"Målbild: {label} ska innehålla exakt fem fasmarkörer")
    if page.count('id="phase-trail"') != 1 or page.count('id="phase-trail-underlay"') != 1:
        raise RuntimeError(f"Målbild: {label} ska innehålla exakt ett stigpar")
    if page.count(SCRIPT_MARKER) != 2:
        raise RuntimeError(f"Målbild: {label} ska innehålla exakt ett trail-sync-block")
    if page.count(TOOLTIP_STACKING_MARKER) != 2:
        raise RuntimeError(f"Målbild: {label} ska innehålla exakt ett tooltip-stacking-block")


def main() -> None:
    if not SOURCE.exists():
        raise RuntimeError("Målbild: canonical sida saknas")

    # Transform canonical once. The cache-bypass route is a byte-identical mirror.
    canonical = SOURCE.read_text(encoding="utf-8")
    canonical = patch_route(canonical)
    canonical = patch_markers(canonical)
    canonical = patch_tooltip_stacking(canonical)
    validate_goal(canonical, "canonical")
    SOURCE.write_text(canonical, encoding="utf-8")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, TARGET)
    mirrored = TARGET.read_text(encoding="utf-8")
    validate_goal(mirrored, "cache-bypass")
    if mirrored != canonical:
        raise RuntimeError("Målbild: cache-bypass-sidan är inte identisk med canonical")

    index = INDEX.read_text(encoding="utf-8")
    if 'href="/träning/malbild-2027/"' not in index:
        raise RuntimeError("Målbild: huvudsidan länkar inte till publicerad målbildsväg")

    print("Målbild OK: canonical transformeras en gång; /malbild-2027/ är en identisk spegling.")


if __name__ == "__main__":
    main()
