#!/usr/bin/env python3
"""Turn the current-week day list into a flat, sticky reading timeline.

The training model and day content remain untouched. This finalizer only adds a
week wrapper, a sticky reading-context row and the visual rules needed to keep
orientation while scrolling without reintroducing cards.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"

WRAP_START = "<!-- training-timeline-v1:start -->"
WRAP_END = "<!-- training-timeline-v1:end -->"
CSS_START = "/* training-timeline-v1:start */"
CSS_END = "/* training-timeline-v1:end */"
JS_START = "/* training-timeline-js-v1:start */"
JS_END = "/* training-timeline-js-v1:end */"

CSS_BLOCK_RE = re.compile(re.escape(CSS_START) + r".*?" + re.escape(CSS_END), re.S)
JS_BLOCK_RE = re.compile(re.escape(JS_START) + r".*?" + re.escape(JS_END), re.S)
DAY_OPEN_RE = re.compile(r'<div class="[^"]*\bday\b[^"]*"\s+id="dag-\d{4}-\d{2}-\d{2}">')
DIV_TAG_RE = re.compile(r"<div\b[^>]*>|</div>", re.I)
CURRENT_HEADING_RE = re.compile(r'<h2 class="section"(?:\s+id="aktuell-vecka")?>Aktuell vecka</h2>')

CSS = r'''
/* Flat week journal: a reading axis replaces card boundaries. */
body.quiet-performance.qp-current .week-timeline{
  position:relative;
  margin:5px 0 30px;
}
body.quiet-performance.qp-current .timeline-scroll-context{
  position:sticky;
  top:0;
  z-index:30;
  display:grid;
  grid-template-columns:92px minmax(0,1fr);
  gap:20px;
  align-items:center;
  min-height:42px;
  margin:0;
  padding:9px 0 8px;
  border-bottom:1px solid var(--qp-line);
  background:rgba(246,247,245,.94);
  -webkit-backdrop-filter:blur(10px);
  backdrop-filter:blur(10px);
}
body.quiet-performance.qp-current .timeline-context-day{
  color:var(--qp-secondary);
  font-size:.66rem;
  font-weight:700;
  letter-spacing:.065em;
  text-transform:uppercase;
  white-space:nowrap;
}
body.quiet-performance.qp-current .timeline-context-session{
  min-width:0;
  overflow:hidden;
  color:var(--qp-text);
  font-size:.78rem;
  font-weight:600;
  text-overflow:ellipsis;
  white-space:nowrap;
}

body.quiet-performance.qp-current .week-timeline>.day,
body.quiet-performance.qp-current .week-timeline>.day.workout-card-v2,
body.quiet-performance.qp-current .week-timeline>.day.workout-card-v2.past-completed,
body.quiet-performance.qp-current .week-timeline>.day.workout-card-v2.future-compact,
body.quiet-performance.qp-current .week-timeline>.day.workout-card-v2.card-v2-today{
  position:relative;
  display:grid;
  grid-template-columns:92px minmax(0,1fr);
  column-gap:20px;
  align-items:start;
  margin:0!important;
  padding:23px 0 27px!important;
  border:0!important;
  border-radius:0!important;
  background:transparent!important;
  box-shadow:none!important;
  scroll-margin-top:54px;
}
body.quiet-performance.qp-current .week-timeline>.day+.day{
  border-top:1px solid var(--qp-line-soft)!important;
}
body.quiet-performance.qp-current .week-timeline>.day::before{
  content:"";
  position:absolute;
  top:0;
  bottom:0;
  left:82px;
  width:1px;
  background:var(--qp-line-soft);
  pointer-events:none;
}
body.quiet-performance.qp-current .week-timeline>.day:first-of-type::before{top:29px}
body.quiet-performance.qp-current .week-timeline>.day:last-of-type::before{bottom:calc(100% - 30px)}

body.quiet-performance.qp-current .week-timeline>.day>.daytop{
  position:sticky;
  top:50px;
  z-index:3;
  grid-column:1;
  grid-row:1;
  display:block!important;
  align-self:start;
  min-width:0;
  margin:0!important;
  padding:0 20px 0 0;
  background:var(--qp-canvas);
}
body.quiet-performance.qp-current .week-timeline>.day>.daytop::after{
  content:"";
  position:absolute;
  top:6px;
  right:5px;
  width:7px;
  height:7px;
  border:1px solid var(--qp-tertiary);
  border-radius:50%;
  background:var(--qp-canvas);
  box-shadow:0 0 0 4px var(--qp-canvas);
}
body.quiet-performance.qp-current .week-timeline>.day.timeline-active>.daytop::after{
  border-color:var(--qp-text);
  background:var(--qp-text);
}
body.quiet-performance.qp-current .week-timeline>.day.card-v2-today>.daytop::after{
  border-color:var(--qp-accent);
  background:var(--qp-accent);
}
body.quiet-performance.qp-current .week-timeline>.day>.daytop .dow{
  margin:0;
  color:var(--qp-tertiary);
  font-size:.7rem;
  font-weight:700;
  line-height:1.25;
  letter-spacing:.055em;
}
body.quiet-performance.qp-current .week-timeline>.day.timeline-active>.daytop .dow{color:var(--qp-text)}
body.quiet-performance.qp-current .week-timeline>.day.card-v2-today>.daytop .dow{color:var(--qp-accent)}
body.quiet-performance.qp-current .week-timeline>.day>.daytop .date{
  margin-top:3px;
  color:var(--qp-tertiary);
  font-size:.67rem;
  line-height:1.25;
  font-variant-numeric:tabular-nums;
}
body.quiet-performance.qp-current .week-timeline>.day>.daytop .badge{
  display:block;
  width:max-content;
  max-width:72px;
  margin-top:9px;
  padding:0!important;
  border:0!important;
  border-radius:0!important;
  background:transparent!important;
  color:var(--qp-tertiary)!important;
  font-size:.56rem;
  font-weight:650;
  line-height:1.25;
  white-space:normal;
}
body.quiet-performance.qp-current .week-timeline>.day.card-v2-today>.daytop .badge{color:var(--qp-accent)!important}
body.quiet-performance.qp-current .week-timeline>.day>:not(.daytop){grid-column:2;min-width:0}

body.quiet-performance.qp-current .week-timeline>.day>.session{
  margin:0 0 3px!important;
  color:var(--qp-text);
  font-size:1.04rem;
  font-weight:650;
  line-height:1.38;
  letter-spacing:-.014em;
}
body.quiet-performance.qp-current .week-timeline>.day>.reason{margin-top:3px;color:var(--qp-secondary)}
body.quiet-performance.qp-current .week-timeline>.day .workout-prescription{margin-top:12px}
body.quiet-performance.qp-current .week-timeline>.day .card-v2-footer{margin-top:12px}

/* No nested card language inside the week timeline either. */
body.quiet-performance.qp-current .week-timeline .swim-workout,
body.quiet-performance.qp-current .week-timeline .workout-history,
body.quiet-performance.qp-current .week-timeline .coach,
body.quiet-performance.qp-current .week-timeline .coach.yoda-v2,
body.quiet-performance.qp-current .week-timeline .decision,
body.quiet-performance.qp-current .week-timeline .feedback-loop,
body.quiet-performance.qp-current .week-timeline .week-activity-insight{
  margin-left:0;
  margin-right:0;
  padding-left:0;
  padding-right:0;
  border-left:0;
  border-right:0;
  border-radius:0;
  background:transparent;
  box-shadow:none;
}
body.quiet-performance.qp-current .week-timeline .swim-workout,
body.quiet-performance.qp-current .week-timeline .workout-history,
body.quiet-performance.qp-current .week-timeline .coach,
body.quiet-performance.qp-current .week-timeline .coach.yoda-v2,
body.quiet-performance.qp-current .week-timeline .decision,
body.quiet-performance.qp-current .week-timeline .feedback-loop{
  border-top:1px solid var(--qp-line-soft);
  border-bottom:0;
}

@media(max-width:620px){
  body.quiet-performance.qp-current .timeline-scroll-context{
    grid-template-columns:72px minmax(0,1fr);
    gap:12px;
    min-height:40px;
    padding:8px 0 7px;
  }
  body.quiet-performance.qp-current .week-timeline>.day,
  body.quiet-performance.qp-current .week-timeline>.day.workout-card-v2,
  body.quiet-performance.qp-current .week-timeline>.day.workout-card-v2.past-completed,
  body.quiet-performance.qp-current .week-timeline>.day.workout-card-v2.future-compact,
  body.quiet-performance.qp-current .week-timeline>.day.workout-card-v2.card-v2-today{
    grid-template-columns:72px minmax(0,1fr);
    column-gap:12px;
    padding:20px 0 24px!important;
    scroll-margin-top:50px;
  }
  body.quiet-performance.qp-current .week-timeline>.day::before{left:64px}
  body.quiet-performance.qp-current .week-timeline>.day>.daytop{top:47px;padding-right:15px}
  body.quiet-performance.qp-current .week-timeline>.day>.daytop::after{right:4px}
  body.quiet-performance.qp-current .week-timeline>.day>.daytop .dow{font-size:.64rem}
  body.quiet-performance.qp-current .week-timeline>.day>.daytop .date{font-size:.61rem}
  body.quiet-performance.qp-current .week-timeline>.day>.daytop .badge{max-width:56px;font-size:.51rem}
  body.quiet-performance.qp-current .timeline-context-day{font-size:.6rem}
  body.quiet-performance.qp-current .timeline-context-session{font-size:.73rem}
  body.quiet-performance.qp-current .week-timeline>.day>.session{font-size:.98rem}
}
'''.strip()

JS = r'''
(function(){
  const timeline=document.querySelector('.week-timeline');
  if(!timeline) return;
  const context=timeline.querySelector('.timeline-scroll-context');
  if(!context) return;
  const dayLabel=context.querySelector('.timeline-context-day');
  const sessionLabel=context.querySelector('.timeline-context-session');
  const days=Array.from(timeline.children).filter((node)=>node.classList&&node.classList.contains('day'));
  if(!days.length) return;

  let active=null;
  let scheduled=false;
  const clean=(value)=>(value||'').replace(/\s+/g,' ').trim();
  const compactDate=(value)=>{
    const match=clean(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if(!match) return clean(value);
    const months=['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec'];
    return Number(match[3])+' '+months[Number(match[2])-1];
  };
  const setActive=(day)=>{
    if(!day||day===active) return;
    if(active) active.classList.remove('timeline-active');
    active=day;
    active.classList.add('timeline-active');
    const dow=clean(active.querySelector('.dow')?.textContent);
    const date=compactDate(active.querySelector('.date')?.textContent);
    const session=clean(active.querySelector('.session')?.textContent);
    dayLabel.textContent=clean(dow+' '+date);
    sessionLabel.textContent=session||'Planerad träningsdag';
  };
  const update=()=>{
    scheduled=false;
    const threshold=context.getBoundingClientRect().bottom+18;
    let candidate=days[0];
    for(const day of days){
      if(day.getBoundingClientRect().top<=threshold) candidate=day;
      else break;
    }
    setActive(candidate);
  };
  const schedule=()=>{
    if(scheduled) return;
    scheduled=true;
    requestAnimationFrame(update);
  };
  setActive(days[0]);
  update();
  addEventListener('scroll',schedule,{passive:true});
  addEventListener('resize',schedule,{passive:true});
})();
'''.strip()


def balanced_div_end(text: str, start: int) -> int:
    depth = 0
    for match in DIV_TAG_RE.finditer(text, start):
        if match.group(0).lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    raise RuntimeError("Training timeline: obalanserad div-struktur")


def current_day_span(page: str) -> tuple[int, int]:
    heading = CURRENT_HEADING_RE.search(page)
    if not heading:
        raise RuntimeError("Training timeline: rubriken Aktuell vecka saknas")
    first = DAY_OPEN_RE.search(page, heading.end())
    if not first:
        raise RuntimeError("Training timeline: första dagraden saknas")

    start = first.start()
    end = balanced_div_end(page, start)
    cursor = end
    while True:
        nxt = DAY_OPEN_RE.search(page, cursor)
        if not nxt:
            break
        between = page[cursor:nxt.start()]
        if between.strip():
            break
        end = balanced_div_end(page, nxt.start())
        cursor = end
    return start, end


def wrap_current_week(page: str) -> str:
    has_start = WRAP_START in page
    has_end = WRAP_END in page
    if has_start != has_end:
        raise RuntimeError("Training timeline: ofullständig timeline-wrapper")
    if has_start:
        return page
    start, end = current_day_span(page)
    context = (
        '<section class="week-timeline" aria-label="Aktuell veckas pass">'
        '<div class="timeline-scroll-context" aria-hidden="true">'
        '<span class="timeline-context-day">Aktuell vecka</span>'
        '<span class="timeline-context-session">Träningsplan</span>'
        '</div>'
    )
    return page[:start] + WRAP_START + "\n" + context + "\n" + page[start:end] + "\n</section>\n" + WRAP_END + page[end:]


def add_css(page: str) -> str:
    block = f"{CSS_START}\n{CSS}\n{CSS_END}"
    has_start = CSS_START in page
    has_end = CSS_END in page
    if has_start != has_end:
        raise RuntimeError("Training timeline: ofullständigt CSS-block")
    if has_start:
        match = CSS_BLOCK_RE.search(page)
        if not match:
            raise RuntimeError("Training timeline: CSS-block kunde inte avgränsas")
        return page[:match.start()] + block + page[match.end():]
    if "</style>" not in page:
        raise RuntimeError("Training timeline: </style> saknas")
    return page.replace("</style>", block + "\n</style>", 1)


def add_js(page: str) -> str:
    block = f"<script>\n{JS_START}\n{JS}\n{JS_END}\n</script>"
    has_start = JS_START in page
    has_end = JS_END in page
    if has_start != has_end:
        raise RuntimeError("Training timeline: ofullständigt JS-block")
    if has_start:
        match = JS_BLOCK_RE.search(page)
        if not match:
            raise RuntimeError("Training timeline: JS-block kunde inte avgränsas")
        script_start = page.rfind("<script>", 0, match.start())
        script_end = page.find("</script>", match.end())
        if script_start < 0 or script_end < 0:
            raise RuntimeError("Training timeline: script-wrapper kunde inte avgränsas")
        script_end += len("</script>")
        return page[:script_start] + block + page[script_end:]
    if "</body>" not in page:
        raise RuntimeError("Training timeline: </body> saknas")
    return page.replace("</body>", block + "\n</body>", 1)


def apply_timeline(page: str) -> str:
    if "quiet-performance qp-current" not in page and "qp-current quiet-performance" not in page:
        if "qp-current" not in page or "quiet-performance" not in page:
            raise RuntimeError("Training timeline: Quiet Performance current-page-klasser saknas")
    page = wrap_current_week(page)
    page = add_css(page)
    return add_js(page)


def validate_page(page: str) -> None:
    required = [
        WRAP_START,
        WRAP_END,
        CSS_START,
        CSS_END,
        JS_START,
        JS_END,
        'class="week-timeline"',
        'class="timeline-scroll-context"',
        "position:sticky;",
        "grid-template-columns:92px minmax(0,1fr)",
        "background:transparent!important;",
        "border-radius:0!important;",
        "box-shadow:none!important;",
        "timeline-active",
    ]
    missing = [value for value in required if value not in page]
    if missing:
        raise RuntimeError(f"Training timeline: saknar {missing!r}")
    for start, end in ((WRAP_START, WRAP_END), (CSS_START, CSS_END), (JS_START, JS_END)):
        if page.count(start) != 1 or page.count(end) != 1:
            raise RuntimeError(f"Training timeline: duplicerad marker {start}")
    wrapper_start = page.find(WRAP_START)
    wrapper_end = page.find(WRAP_END, wrapper_start)
    if wrapper_end < 0 or not DAY_OPEN_RE.search(page, wrapper_start, wrapper_end):
        raise RuntimeError("Training timeline: wrappern innehåller inga dagrader")


def main() -> int:
    if not INDEX_FILE.exists():
        raise RuntimeError("Training timeline: index.html saknas")
    rendered = apply_timeline(INDEX_FILE.read_text(encoding="utf-8"))
    validate_page(rendered)
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    print("Training timeline UI OK: aktuell vecka har sticky dagaxel och läskontext utan kort.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
