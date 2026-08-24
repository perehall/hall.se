#!/usr/bin/env python3
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"

page = INDEX_FILE.read_text(encoding="utf-8")


def compact_summary(text, max_chars=160):
    plain = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(plain) <= max_chars:
        return plain

    sentences = re.split(r"(?<=[.!?])\s+", plain)
    if sentences and len(sentences[0]) <= max_chars:
        return sentences[0]

    clipped = plain[: max_chars - 1].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(".,;:") + "…"


coach_pattern = re.compile(
    r'<div class="coach">\n'
    r'  <div class="coach-title">Tränings-Yoda \(AI\)</div>\n'
    r'  <div class="coach-summary">(?P<summary>.*?)</div>\n'
    r'  <div class="coach-load">(?P<load>.*?)</div>\n'
    r'  <details class="coach-details"><summary>Underlag · fakta, tolkning och osäkerhet</summary>\n'
    r'(?P<details>.*?)'
    r'  </details>\n'
    r'  <div class="coach-action"><strong>(?P<action>.*?)</strong> · (?P<target>.*?)<br>'
    r'(?P<reason>.*?)<br><span>(?P<recommendation>.*?)</span><br><small>(?P<apply>.*?)</small></div>\n'
    r'</div>',
    re.DOTALL,
)


def render_coach(match):
    summary_full = match.group("summary").strip()
    summary_short = html.escape(compact_summary(summary_full))
    load = match.group("load").strip()
    details = match.group("details")
    action = match.group("action").strip()
    target = match.group("target").strip()
    reason = match.group("reason").strip()
    recommendation = match.group("recommendation").strip()
    apply_text = match.group("apply").strip()

    target_html = f'<span class="coach-target">{target}</span>' if target else ""

    return f'''<div class="coach yoda-v2">
  <div class="coach-title">Tränings-Yoda (AI)</div>
  <div class="coach-decision"><span>Beslut</span><strong>{action}</strong>{target_html}</div>
  <div class="coach-summary">{summary_short}</div>
  <div class="coach-next"><span class="coach-next-label">Nästa steg</span><div>{recommendation}</div></div>
  <details class="coach-why"><summary>Varför?</summary>
    <div class="coach-why-body">
      <div class="coach-full-summary"><strong>Bedömning</strong><span>{summary_full}</span></div>
      <div class="coach-load">{load}</div>
      <div class="coach-reason"><strong>Motivering</strong><span>{reason}</span></div>
      <details class="coach-details"><summary>Fakta, tolkning och osäkerhet</summary>
{details}      </details>
    </div>
  </details>
  <div class="coach-apply"><small>{apply_text}</small></div>
</div>'''


page, replacements = coach_pattern.subn(render_coach, page)
has_v2 = 'class="coach yoda-v2"' in page
has_unformatted_coach = 'class="coach"' in page

if replacements == 0 and not has_v2:
    if has_unformatted_coach:
        raise RuntimeError("Tränings-Yoda UX: coachblock finns men matchar inte UI-kontraktet")
    # A new active week can legitimately have no activity/coach analysis yet.
    # Do not invent a coach block merely to satisfy the renderer.
    INDEX_FILE.write_text(page, encoding="utf-8")
    print("Tränings-Yoda UX OK: 0 coachblock; ingen coachanalys finns för den aktiva veckan ännu.")
    raise SystemExit(0)

css_marker = "/* training-yoda-v2 */"
if css_marker not in page:
    css = r'''
/* training-yoda-v2 */
.coach.yoda-v2{padding:15px;background:#f8f5ff}.yoda-v2 .coach-title{margin-bottom:8px}.coach-decision{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap;margin-bottom:7px}.coach-decision>span:first-child{font-size:.66rem;font-weight:900;text-transform:uppercase;letter-spacing:.07em;color:#7c3aed}.coach-decision strong{font-size:.98rem;color:#3b0764}.coach-target{font-size:.76rem;color:#7c3aed}.yoda-v2 .coach-summary{margin:0 0 10px;padding:0;border:0;background:transparent;font-size:.91rem;font-weight:500;line-height:1.48;color:#334155}.coach-next{padding:10px 12px;border:1px solid #c4b5fd;border-radius:12px;background:#fff;font-size:.92rem;line-height:1.45;color:#312e81}.coach-next-label{display:block;margin-bottom:3px;font-size:.67rem;font-weight:900;text-transform:uppercase;letter-spacing:.07em;color:#6d28d9}.coach-why{margin-top:9px;border:1px solid #e9d5ff;border-radius:11px;background:#fff}.coach-why>summary{cursor:pointer;padding:9px 11px;font-size:.83rem;font-weight:800;color:#5b21b6}.coach-why-body{padding:0 11px 11px;display:grid;gap:9px}.coach-full-summary,.coach-reason{display:grid;gap:3px;font-size:.86rem;line-height:1.45;color:#475569}.coach-full-summary strong,.coach-reason strong{font-size:.67rem;text-transform:uppercase;letter-spacing:.06em;color:#6d28d9}.yoda-v2 .coach-load{margin:0;padding:9px 10px;background:#faf5ff;border-radius:10px;font-size:.84rem;line-height:1.45}.yoda-v2 .coach-load:before{content:"Närbelastning"}.yoda-v2 .coach-details{margin:0;padding:8px 10px;border-radius:10px;background:#fafafa}.yoda-v2 .coach-details summary{font-size:.8rem}.coach-apply{margin-top:7px;color:#7c3aed;font-size:.76rem}.coach-apply small{font-size:inherit}.yoda-v2 .coach-action{display:none}
@media (max-width:620px){.coach.yoda-v2{padding:13px}.coach-next{padding:9px 10px}.coach-why-body{padding:0 9px 9px}}
'''
    if "</style>" not in page:
        raise RuntimeError("Tränings-Yoda UX: kunde inte hitta </style>")
    page = page.replace("</style>", css + "\n</style>", 1)

INDEX_FILE.write_text(page, encoding="utf-8")

rendered = INDEX_FILE.read_text(encoding="utf-8")
required = [
    'class="coach yoda-v2"',
    '<span>Beslut</span>',
    'class="coach-next-label">Nästa steg</span>',
    '<summary>Varför?</summary>',
    css_marker,
    'font-weight:500',
]
missing = [snippet for snippet in required if snippet not in rendered]
if missing:
    raise RuntimeError("Tränings-Yoda UX-validering misslyckades: " + repr(missing))

print(f"Tränings-Yoda UX OK: {replacements} coachblock omformaterade.")
