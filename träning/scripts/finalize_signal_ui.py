#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"

CSS_MARKER = "/* signal-first-ui-v1 */"

CSS = r'''
/* signal-first-ui-v1 */
body{line-height:1.42}.wrap{width:min(100%,720px)}
.day{padding:16px 17px}.session{line-height:1.28}.reason{font-size:.9rem;line-height:1.48}
.day-why{margin-top:8px}.day-why>summary,.brain-why-details>summary,.brain-block-why>summary{cursor:pointer;color:#64748b;font-size:.78rem;font-weight:800;list-style:none}.day-why>summary::-webkit-details-marker,.brain-why-details>summary::-webkit-details-marker,.brain-block-why>summary::-webkit-details-marker{display:none}.day-why>summary:after,.brain-why-details>summary:after,.brain-block-why>summary:after{content:" +"}.day-why[open]>summary:after,.brain-why-details[open]>summary:after,.brain-block-why[open]>summary:after{content:" −"}.day-why .reason{margin-top:7px;color:#475569}
.development-focus{margin-top:10px}.development-focus strong{font-size:.7rem}.development-focus span{line-height:1.42}
.yoda-v2 .coach-summary,.yoda-v2 .coach-apply{display:none}.coach.yoda-v2{margin-top:12px}.coach-next{line-height:1.4}.coach-why{margin-top:7px}
.brain-why-details{margin-top:8px}.brain-why-details .brain-why{margin-top:6px}.brain-block-why{margin-top:6px}.brain-block-why .brain-hypothesis{margin-top:6px}.brain-meta{margin-top:6px}.brain-priority{margin-top:8px}
.reference-tools{display:flex;justify-content:flex-start;margin:22px 0 8px}.reference-chip{appearance:none;border:1px solid #cbd5e1;background:#fff;color:#334155;border-radius:999px;padding:9px 13px;font:inherit;font-size:.82rem;font-weight:800;cursor:pointer;box-shadow:0 3px 10px rgba(15,23,42,.04)}
.strength-window{position:fixed;inset:auto;width:min(520px,calc(100vw - 32px));max-height:calc(100vh - 32px);left:50%;top:50%;transform:translate(-50%,-50%);margin:0;border:1px solid #e2e8f0;border-radius:18px;padding:0;background:#fff;color:#0f172a;box-shadow:0 24px 70px rgba(15,23,42,.28);overflow:auto}.strength-window::backdrop{background:rgba(15,23,42,.38)}.sheet-inner{padding:0 18px 18px}.sheet-head{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0 -18px 8px;padding:14px 18px 10px;background:#fff;border-bottom:1px solid #f1f5f9;cursor:move;touch-action:none;user-select:none}.sheet-head h2{font-size:1.1rem;margin:0}.sheet-close{appearance:none;border:0;background:#f1f5f9;color:#334155;border-radius:999px;padding:7px 10px;font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}.sheet-note{margin:0 0 10px;color:#64748b;font-size:.8rem}.strength-list{margin:0;padding:0;list-style:none;display:grid;gap:0}.strength-list li{padding:10px 0;border-top:1px solid #e2e8f0;font-size:.9rem;line-height:1.38}.strength-list li:first-child{border-top:0}
@media (max-width:620px){.wrap{padding-left:13px;padding-right:13px}.day{border-radius:17px;padding:15px}.brain-today,.brain-card,.dashboard-card{border-radius:16px}.reference-tools{margin-top:18px}.strength-window{width:min(100% - 16px,720px);max-height:min(78vh,680px);left:50%!important;top:auto!important;bottom:0;transform:translateX(-50%)!important;border:0;border-radius:22px 22px 0 0}.sheet-inner{padding:0 18px calc(20px + env(safe-area-inset-bottom))}.sheet-head{cursor:default;touch-action:auto}}
'''


def compact_text(value, max_chars):
    plain = html.unescape(re.sub(r"\s+", " ", value or "")).strip()
    if len(plain) <= max_chars:
        return plain
    sentences = re.split(r"(?<=[.!?])\s+", plain)
    if sentences and len(sentences[0]) <= max_chars:
        return sentences[0]
    clipped = plain[: max_chars - 1].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(".,;:") + "…"


def collapse_day_reasons(page):
    if 'class="day-why"' in page:
        return page
    return re.sub(
        r'<div class="reason">(.*?)</div>',
        r'<details class="day-why"><summary>Varför?</summary><div class="reason">\1</div></details>',
        page,
        flags=re.S,
    )


def simplify_training_brain(page):
    if 'class="brain-why-details"' not in page:
        page = re.sub(
            r'<div class="brain-why"><strong>Varför:</strong>\s*(.*?)</div>',
            r'<details class="brain-why-details"><summary>Varför?</summary><div class="brain-why">\1</div></details>',
            page,
            flags=re.S,
        )
    if 'class="brain-block-why"' not in page:
        page = re.sub(
            r'<div class="brain-hypothesis">(.*?)</div>',
            r'<details class="brain-block-why"><summary>Blockidé</summary><div class="brain-hypothesis">\1</div></details>',
            page,
            flags=re.S,
        )
    page = re.sub(
        r'(<div class="brain-meta">Utvärdering: .*?)\s*·\s*skyddade stimuli:.*?(</div>)',
        r'\1\2',
        page,
        flags=re.S,
    )
    return page


def compact_visible_text(page):
    def replace_next(match):
        text = compact_text(match.group(2), 150)
        return match.group(1) + html.escape(text) + match.group(3)

    page = re.sub(
        r'(<div class="coach-next"><span class="coach-next-label">Nästa steg</span><div>)(.*?)(</div></div>)',
        replace_next,
        page,
        flags=re.S,
    )

    def replace_brain_note(match):
        return match.group(1) + html.escape(compact_text(match.group(2), 150)) + match.group(3)

    page = re.sub(
        r'(<div class="brain-note">)(.*?)(</div>)',
        replace_brain_note,
        page,
        flags=re.S,
    )

    def replace_focus(match):
        return match.group(1) + html.escape(compact_text(match.group(2), 155)) + match.group(3)

    page = re.sub(
        r'(<div class="development-focus"><strong>Fokus</strong><span>)(.*?)(</span></div>)',
        replace_focus,
        page,
        flags=re.S,
    )
    return page


def strength_sheet(strength_template):
    items = "".join(f"<li>{html.escape(item)}</li>" for item in strength_template)
    return f'''<div class="reference-tools">
  <button class="reference-chip" type="button" onclick="openStrengthWindow()">Styrkemall</button>
</div>
<dialog id="strengthSheet" class="strength-window" aria-labelledby="strengthWindowTitle">
  <div class="sheet-inner">
    <div class="sheet-head" id="strengthDragHandle"><h2 id="strengthWindowTitle">Styrkemall</h2><button class="sheet-close" type="button" onclick="document.getElementById('strengthSheet').close()">Stäng</button></div>
    <p class="sheet-note">Referens. Aktuellt styrkebeslut styrs av veckoplanen.</p>
    <ul class="strength-list">{items}</ul>
  </div>
</dialog>
<script>
function openStrengthWindow() {{
  const dialog = document.getElementById('strengthSheet');
  dialog.style.left = '50%';
  dialog.style.top = '50%';
  dialog.style.transform = 'translate(-50%,-50%)';
  dialog.showModal();
}}
(function() {{
  const dialog = document.getElementById('strengthSheet');
  const handle = document.getElementById('strengthDragHandle');
  let dragging = false;
  let offsetX = 0;
  let offsetY = 0;

  function desktop() {{ return window.matchMedia('(min-width: 621px)').matches; }}
  function clamp(value, min, max) {{ return Math.min(Math.max(value, min), max); }}

  handle.addEventListener('pointerdown', (event) => {{
    if (!desktop() || event.target.closest('button')) return;
    const rect = dialog.getBoundingClientRect();
    dialog.style.transform = 'none';
    dialog.style.left = rect.left + 'px';
    dialog.style.top = rect.top + 'px';
    offsetX = event.clientX - rect.left;
    offsetY = event.clientY - rect.top;
    dragging = true;
    handle.setPointerCapture(event.pointerId);
  }});

  handle.addEventListener('pointermove', (event) => {{
    if (!dragging || !desktop()) return;
    const rect = dialog.getBoundingClientRect();
    const margin = 8;
    const maxLeft = Math.max(margin, window.innerWidth - rect.width - margin);
    const maxTop = Math.max(margin, window.innerHeight - rect.height - margin);
    dialog.style.left = clamp(event.clientX - offsetX, margin, maxLeft) + 'px';
    dialog.style.top = clamp(event.clientY - offsetY, margin, maxTop) + 'px';
  }});

  function stopDrag(event) {{
    if (!dragging) return;
    dragging = false;
    if (event.pointerId !== undefined && handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
  }}
  handle.addEventListener('pointerup', stopDrag);
  handle.addEventListener('pointercancel', stopDrag);

  window.addEventListener('resize', () => {{
    if (!dialog.open || !desktop()) return;
    const rect = dialog.getBoundingClientRect();
    const margin = 8;
    dialog.style.transform = 'none';
    dialog.style.left = clamp(rect.left, margin, Math.max(margin, window.innerWidth - rect.width - margin)) + 'px';
    dialog.style.top = clamp(rect.top, margin, Math.max(margin, window.innerHeight - rect.height - margin)) + 'px';
  }});
}})();
</script>
'''


def replace_strength_section(page, strength_template):
    pattern = re.compile(
        r'<h2 class="section">Styrkemall framåt</h2><div class="principles">.*?</div>\s*(?=<footer>)',
        re.S,
    )
    page, count = pattern.subn(strength_sheet(strength_template), page, count=1)
    if count != 1:
        raise RuntimeError("Signal-UI: kunde inte ersätta styrkemallen")
    return page


def apply_signal_ui(page, strength_template):
    page = page.replace("<strong>Utvecklingsfokus</strong>", "<strong>Fokus</strong>")
    page = collapse_day_reasons(page)
    page = simplify_training_brain(page)
    page = compact_visible_text(page)
    page = replace_strength_section(page, strength_template)
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Signal-UI: index.html saknar </style>")
        page = page.replace("</style>", CSS + "\n</style>", 1)
    return page


def main():
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    page = INDEX_FILE.read_text(encoding="utf-8")
    rendered = apply_signal_ui(page, plan.get("strength_template") or [])
    INDEX_FILE.write_text(rendered, encoding="utf-8")

    verify = INDEX_FILE.read_text(encoding="utf-8")
    required = [
        CSS_MARKER,
        'class="reference-chip"',
        'id="strengthSheet"',
        'class="strength-window"',
        'id="strengthDragHandle"',
        'function openStrengthWindow()',
        'class="day-why"',
        'class="brain-why-details"',
        'class="brain-block-why"',
        '<strong>Fokus</strong>',
        '.yoda-v2 .coach-summary,.yoda-v2 .coach-apply{display:none}',
    ]
    missing = [marker for marker in required if marker not in verify]
    if missing:
        raise RuntimeError("Signal-UI: renderad sida saknar " + repr(missing))
    if "Styrkemall framåt" in verify:
        raise RuntimeError("Signal-UI: gamla styrkemallssektionen finns kvar")
    if "skyddade stimuli:" in verify:
        raise RuntimeError("Signal-UI: interna stimulusnycklar läcker till huvudvyn")
    print("Signal-UI OK: styrkemallen är ett centrerat flyttbart fönster på desktop och bottom sheet på mobil.")


if __name__ == "__main__":
    main()
