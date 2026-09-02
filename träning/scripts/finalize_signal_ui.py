#!/usr/bin/env python3
import html
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from training_brain import day_fulfilled

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"

CSS_MARKER = "/* signal-first-ui-v3 */"

CSS = r'''
/* signal-first-ui-v3 */
body{line-height:1.42}.wrap{width:min(100%,720px)}
.day{padding:16px 17px}.reason{font-size:.9rem;line-height:1.48}
.daytop{align-items:center;margin-bottom:9px}.day-date-line{display:flex;align-items:baseline;gap:6px;min-width:0}.dow{font-size:.86rem;font-weight:700;color:#334155;text-transform:none;letter-spacing:0}.date{font-size:.8rem;color:#94a3b8}
.badge{padding:4px 8px;font-size:.68rem;font-weight:700;letter-spacing:0;text-transform:none}
.session{margin:2px 0 4px;font-size:1rem;font-weight:700;line-height:1.28}.session-with-icon{align-items:flex-start}.session-with-icon .sport-icon{margin-top:2px;flex:0 0 auto}.session-text{display:flex;min-width:0;flex-direction:column;gap:2px}.session-title{font-size:1.08rem;font-weight:700;line-height:1.28;letter-spacing:-.01em;color:#0f172a}.session-meta{font-size:.82rem;font-weight:500;line-height:1.4;color:#64748b}
.day .next-weather{margin-top:7px!important;color:#64748b!important;font-size:.78rem!important;line-height:1.4}.day .next-weather .weather-label{color:#475569;font-weight:600}.day .next-weather .weather-icon{margin-right:4px!important}
.day-why{margin-top:8px}.day-why>summary,.brain-why-details>summary{cursor:pointer;color:#64748b;font-size:.78rem;font-weight:600;list-style:none}.day-why>summary::-webkit-details-marker,.brain-why-details>summary::-webkit-details-marker{display:none}.day-why>summary:after,.brain-why-details>summary:after{content:" +"}.day-why[open]>summary:after,.brain-why-details[open]>summary:after{content:" −"}.day-why .reason{margin-top:7px;color:#475569}
.development-focus{margin-top:10px;padding:10px 12px;border-color:#e2e8f0;background:#f8fafc}.development-focus strong{color:#475569;font-size:.72rem;font-weight:700;text-transform:none;letter-spacing:0}.development-focus span{color:#334155;font-size:.86rem;line-height:1.42}
.yoda-v2 .coach-summary,.yoda-v2 .coach-apply{display:none}.coach.yoda-v2{margin-top:12px}.coach-next{line-height:1.4}.coach-why{margin-top:7px}
.brain-why-details{margin-top:8px}.brain-why-details .brain-why{margin-top:6px}.brain-note{line-height:1.4}
.day.past-completed,.day.future-compact{padding:12px 14px;box-shadow:0 3px 10px rgba(15,23,42,.035)}.past-completed .daytop,.future-compact .daytop{margin-bottom:5px;align-items:center}.past-completed .session,.future-compact .session{font-size:1rem;margin:2px 0}.past-completed .session-title,.future-compact .session-title{font-size:.96rem}.past-completed .session-meta,.future-compact .session-meta{display:none}.past-completed .day-why,.past-completed .development-focus,.past-completed .decision,.future-compact .day-why,.future-compact .development-focus,.future-compact .decision,.future-compact .coach{display:none}.past-completed .pass{margin-top:6px;padding-top:6px;gap:2px;font-size:.78rem;color:#64748b}.past-completed .pass-title{display:none}.future-compact .swim-set-list{display:none}.future-compact .swim-workout{margin:5px 0 0;padding:8px 10px;background:#fff}.future-compact .swim-session-head strong{font-size:.95rem}.past-exception{border-color:#f59e0b}
.week-state{margin:20px 0 8px;border-top:1px solid #e2e8f0;padding-top:12px}.week-state>summary{cursor:pointer;list-style:none;color:#475569;font-size:.82rem;font-weight:850}.week-state>summary::-webkit-details-marker{display:none}.week-state>summary:after{content:" +"}.week-state[open]>summary:after{content:" −"}.week-state .dashboard{margin:12px 0 0}.week-state .dashboard>.dashboard-card:last-child{display:none}.week-state .dashboard-grid{grid-template-columns:1fr 1fr}.week-state .dashboard-card{box-shadow:none}.week-state .metrics{margin-bottom:0}
.reference-tools{display:flex;justify-content:flex-start;margin:12px 0 8px}.reference-chip{appearance:none;border:1px solid #cbd5e1;background:#fff;color:#334155;border-radius:999px;padding:9px 13px;font:inherit;font-size:.82rem;font-weight:800;cursor:pointer;box-shadow:0 3px 10px rgba(15,23,42,.04)}
.strength-window{position:fixed;inset:auto;width:min(520px,calc(100vw - 32px));max-height:calc(100vh - 32px);left:50%;top:50%;transform:translate(-50%,-50%);margin:0;border:1px solid #e2e8f0;border-radius:18px;padding:0;background:#fff;color:#0f172a;box-shadow:0 24px 70px rgba(15,23,42,.28);overflow:auto}.strength-window::backdrop{background:rgba(15,23,42,.38)}.sheet-inner{padding:0 18px 18px}.sheet-head{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0 -18px 8px;padding:14px 18px 10px;background:#fff;border-bottom:1px solid #f1f5f9;cursor:move;touch-action:none;user-select:none}.sheet-head h2{font-size:1.1rem;margin:0}.sheet-close{appearance:none;border:0;background:#f1f5f9;color:#334155;border-radius:999px;padding:7px 10px;font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}.sheet-note{margin:0 0 10px;color:#64748b;font-size:.8rem}.strength-list{margin:0;padding:0;list-style:none;display:grid;gap:0}.strength-list li{padding:10px 0;border-top:1px solid #e2e8f0;font-size:.9rem;line-height:1.38}.strength-list li:first-child{border-top:0}
@media (max-width:620px){.wrap{padding-left:13px;padding-right:13px}.day{border-radius:17px;padding:15px}.day.past-completed,.day.future-compact{padding:11px 12px}.session-title{font-size:1.02rem}.session-meta{font-size:.8rem}.brain-today,.dashboard-card{border-radius:16px}.week-state .dashboard-grid{grid-template-columns:1fr}.reference-tools{margin-top:10px}.strength-window{width:min(100% - 16px,720px);max-height:min(78vh,680px);left:50%!important;top:auto!important;bottom:0;transform:translateX(-50%)!important;border:0;border-radius:22px 22px 0 0}.sheet-inner{padding:0 18px calc(20px + env(safe-area-inset-bottom))}.sheet-head{cursor:default;touch-action:auto}}
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


MONTH_SHORT = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "maj", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec",
}


def short_day_date(day):
    try:
        parsed = date.fromisoformat(str(day.get("date") or ""))
    except ValueError:
        return str(day.get("label") or ""), str(day.get("date") or "")
    return str(day.get("label") or ""), f"{parsed.day} {MONTH_SHORT[parsed.month]}"


def status_copy(day, rendered_status):
    if day.get("alternative_sports"):
        return "Alternativ finns"
    labels = {
        "completed": "Genomfört",
        "planned": "Planerat",
        "preliminary": "Preliminärt",
        "conditional": "Villkorat",
        "open": "Öppet",
    }
    status = str(day.get("status") or "").strip()
    return labels.get(status, rendered_status.strip().capitalize())


def _distance_token(tokens):
    return next((token for token in tokens if re.fullmatch(r"\d[\d ]*\s*m", token)), "")


def _duration_token(tokens):
    return next((token for token in tokens if re.search(r"\b(?:ca\s*)?\d+\s*min\b", token)), "")


def session_display_parts(day):
    """Create a calm visual title without changing the canonical session prescription."""
    session = str(day.get("session") or "").strip()
    tokens = [token.strip() for token in session.split(" · ") if token.strip()]
    if not tokens:
        return session, ""
    first = tokens[0]
    sport = str(day.get("sport") or "").strip().lower()

    if first.lower().startswith("simning") and any("styrka/core" in token.lower() for token in tokens):
        distance = _distance_token(tokens)
        quality = next(
            (
                token.split(" + ", 1)[0].strip()
                for token in tokens
                if "styrka/core" in token.lower() and " + " in token
            ),
            "aerob/teknik",
        )
        duration = _duration_token(tokens[2:])
        meta = " ".join(x for x in (distance, quality) if x)
        if duration:
            meta += (" · " if meta else "") + f"styrka {duration}"
        if any(token.lower() == "styrkemall" for token in tokens):
            meta += (" · " if meta else "") + "styrkemall"
        return "Simning + styrka/core", meta

    if sport == "swim" or first.lower().startswith("simning"):
        distance = _distance_token(tokens)
        quality = next(
            (
                token for token in tokens[1:]
                if any(word in token.lower() for word in ("aerob", "teknik", "tröskel"))
                and not token.lower().startswith("alternativ:")
            ),
            "",
        )
        duration = _duration_token(tokens)
        title = " ".join(x for x in ("Simning", distance, quality) if x)
        alt_index = next(
            (index for index, token in enumerate(tokens) if token.lower().startswith("alternativ:")),
            None,
        )
        meta_parts = [duration] if duration else []
        if alt_index is not None:
            alt_tokens = tokens[alt_index:]
            first_alt = alt_tokens[0].split(":", 1)[1].strip() if ":" in alt_tokens[0] else alt_tokens[0]
            rest_alt = " ".join(alt_tokens[1:]).strip()
            alt_text = f"alternativ: {first_alt}"
            if rest_alt:
                alt_text += f", {rest_alt}"
            meta_parts.append(alt_text)
        return title or first, " · ".join(meta_parts)

    if sport == "bike" or first.lower().startswith(("mtb", "cykel")):
        duration = _duration_token(tokens)
        title = " ".join(x for x in (first, duration) if x)
        remaining = [token for token in tokens[1:] if token != duration]
        return title, " · ".join(remaining)

    if sport == "strength" or first.lower().startswith("styrka"):
        duration = _duration_token(tokens)
        title = " ".join(x for x in (first, duration) if x)
        remaining = [token for token in tokens[1:] if token != duration]
        return title, " · ".join(remaining)

    if sport == "run" or first.lower().startswith(("löpning", "trail")):
        if len(tokens) >= 2:
            return f"{first} · {tokens[1]}", " · ".join(tokens[2:])
        return first, ""

    if len(tokens) >= 2:
        return first, " · ".join(tokens[1:])
    return first, ""


def day_card_ranges(page):
    pattern = re.compile(r'<div class="day[^"]*" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">')
    matches = list(pattern.finditer(page))
    return [
        (
            match.start(),
            matches[index + 1].start() if index + 1 < len(matches) else len(page),
            match.group("date"),
        )
        for index, match in enumerate(matches)
    ]


def calm_day_card_hierarchy(page, plan):
    days_by_date = {str(day.get("date") or ""): day for day in (plan or {}).get("days") or []}
    for start, end, day_text in reversed(day_card_ranges(page)):
        day = days_by_date.get(day_text)
        if not day:
            continue
        block = page[start:end]

        day_label, short_date = short_day_date(day)
        top_pattern = re.compile(
            r'<div class="daytop">\s*<div><div class="dow">.*?</div><div class="date">.*?</div></div>\s*'
            r'<div class="badge (?P<class>[^"]+)">(?P<label>[^<]*)</div>\s*</div>',
            re.S,
        )
        top_match = top_pattern.search(block)
        if top_match:
            badge_label = status_copy(day, top_match.group("label"))
            replacement = (
                '<div class="daytop"><div class="day-date-line">'
                f'<span class="dow">{html.escape(day_label)}</span>'
                f'<span class="date">{html.escape(short_date)}</span></div>'
                f'<div class="badge {html.escape(top_match.group("class"))}">{html.escape(badge_label)}</div></div>'
            )
            block = block[:top_match.start()] + replacement + block[top_match.end():]

        raw_session = html.escape(str(day.get("session") or ""))
        title, meta = session_display_parts(day)
        session_copy = (
            f'<span class="session-text"><strong class="session-title">{html.escape(title)}</strong>'
            + (f'<span class="session-meta">{html.escape(meta)}</span>' if meta else "")
            + '</span>'
        )
        decorated = f"<span>{raw_session}</span>"
        if decorated in block:
            block = block.replace(decorated, session_copy, 1)
        else:
            plain = f'<div class="session">{raw_session}</div>'
            if plain in block:
                block = block.replace(plain, f'<div class="session">{session_copy}</div>', 1)

        block = re.sub(
            r'<strong>Väder · ([^<]+)</strong>\s*·\s*',
            r'<span class="weather-label">Väder i \1:</span> ',
            block,
        )
        block = block.replace("<summary>Varför?</summary>", "<summary>Motivering</summary>")
        block = block.replace("<strong>Fokus</strong>", "<strong>Passfokus</strong>")
        block = block.replace("<strong>Utvecklingsfokus</strong>", "<strong>Passfokus</strong>")
        page = page[:start] + block + page[end:]
    return page


def collapse_day_reasons(page):
    if 'class="day-why"' in page:
        return page
    return re.sub(
        r'<div class="reason">(.*?)</div>',
        r'<details class="day-why"><summary>Motivering</summary><div class="reason">\1</div></details>',
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
    return page


def compact_visible_text(page):
    def replace_next(match):
        text = compact_text(match.group(2), 145)
        return match.group(1) + html.escape(text) + match.group(3)

    page = re.sub(
        r'(<div class="coach-next"><span class="coach-next-label">Nästa steg</span><div>)(.*?)(</div></div>)',
        replace_next,
        page,
        flags=re.S,
    )

    def replace_brain_note(match):
        return match.group(1) + html.escape(compact_text(match.group(2), 145)) + match.group(3)

    page = re.sub(r'(<div class="brain-note">)(.*?)(</div>)', replace_brain_note, page, flags=re.S)

    def replace_focus(match):
        return match.group(1) + html.escape(compact_text(match.group(2), 150)) + match.group(3)

    page = re.sub(
        r'(<div class="development-focus"><strong>Passfokus</strong><span>)(.*?)(</span></div>)',
        replace_focus,
        page,
        flags=re.S,
    )
    return page


def annotate_week_days(page, plan, activities, today):
    if not plan:
        return page
    horizon_end = today + timedelta(days=3)
    for day in plan.get("days") or []:
        day_text = day.get("date") or ""
        try:
            day_date = date.fromisoformat(day_text)
        except ValueError:
            continue
        if day_date < today:
            state_class = "past-completed" if day_fulfilled(day, activities or []) else "past-exception"
        elif day_date <= horizon_end:
            state_class = "decision-horizon"
        else:
            state_class = "future-compact"
        pattern = re.compile(rf'<div class="day(?P<extra>[^"]*)" id="dag-{re.escape(day_text)}">')
        match = pattern.search(page)
        if not match:
            raise RuntimeError(f"Signal-UI: dagkort saknas för {day_text}")
        extras = match.group("extra") or ""
        if state_class not in extras.split():
            replacement = f'<div class="day{extras} {state_class}" id="dag-{day_text}">'
            page = page[:match.start()] + replacement + page[match.end():]
    return page


def balanced_div_end(text, start):
    tag_re = re.compile(r'<div\b[^>]*>|</div>')
    depth = 0
    for match in tag_re.finditer(text, start):
        token = match.group(0)
        if token.startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.end()
    return None


def wrap_historical_coaches(page, plan, activities, today):
    if not plan:
        return page
    completed_dates = []
    for day in plan.get("days") or []:
        try:
            day_date = date.fromisoformat(day.get("date") or "")
        except ValueError:
            continue
        if day_date < today and day_fulfilled(day, activities or []):
            completed_dates.append(day.get("date"))

    for day_text in completed_dates:
        marker = f'<div class="day past-completed" id="dag-{day_text}">'
        start = page.find(marker)
        if start < 0:
            continue
        candidates = [
            pos for pos in (
                page.find('<div class="day', start + len(marker)),
                page.find('<h2 class="section">Styrkemall framåt</h2>', start + len(marker)),
                page.find('<footer>', start + len(marker)),
            ) if pos >= 0
        ]
        end = min(candidates) if candidates else len(page)
        block = page[start:end]
        coach_start = block.find('<div class="coach yoda-v2">')
        if coach_start < 0 or 'class="historical-coach"' in block:
            continue
        coach_end = balanced_div_end(block, coach_start)
        if coach_end is None:
            raise RuntimeError(f"Signal-UI: kunde inte avgränsa historisk coach för {day_text}")
        coach = block[coach_start:coach_end]
        wrapped = f'<details class="historical-coach"><summary>AI-analys · historik</summary>{coach}</details>'
        block = block[:coach_start] + wrapped + block[coach_end:]
        page = page[:start] + block + page[end:]
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


def move_dashboard_to_week_state(page):
    if 'class="week-state"' in page:
        return page
    pattern = re.compile(r'<section class="dashboard" aria-label="Veckoöversikt">.*?</section>', re.S)
    match = pattern.search(page)
    if not match:
        raise RuntimeError("Signal-UI: dashboard saknas")
    dashboard = match.group(0)
    page = page[:match.start()] + page[match.end():]
    anchor = '<div class="reference-tools">'
    if anchor not in page:
        raise RuntimeError("Signal-UI: referensverktyg saknas efter styrkemallsflytt")
    week_state = f'<details class="week-state"><summary>Veckoläge</summary>{dashboard}</details>\n'
    return page.replace(anchor, week_state + anchor, 1)


def apply_signal_ui(page, strength_template, *, plan=None, activities=None, today=None):
    page = page.replace("<strong>Utvecklingsfokus</strong>", "<strong>Passfokus</strong>")
    page = collapse_day_reasons(page)
    page = simplify_training_brain(page)
    page = compact_visible_text(page)
    if plan is not None and today is not None:
        page = annotate_week_days(page, plan, activities or [], today)
        page = calm_day_card_hierarchy(page, plan)
    page = replace_strength_section(page, strength_template)
    page = move_dashboard_to_week_state(page)
    page = re.sub(r'/\* signal-first-ui-v[12] \*/.*?(?=(?:/\*|</style>))', '', page, flags=re.S)
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Signal-UI: index.html saknar </style>")
        page = page.replace("</style>", CSS + "\n</style>", 1)
    return page


def main():
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    activities_state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today = datetime.now(ZoneInfo(timezone_name)).date()
    page = INDEX_FILE.read_text(encoding="utf-8")
    rendered = apply_signal_ui(
        page,
        plan.get("strength_template") or [],
        plan=plan,
        activities=activities_state.get("activities") or [],
        today=today,
    )
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
        '<strong>Passfokus</strong>',
        'class="week-state"',
        '<summary>Veckoläge</summary>',
    ]
    missing = [marker for marker in required if marker not in verify]
    if missing:
        raise RuntimeError("Signal-UI: renderad sida saknar " + repr(missing))
    if "Styrkemall framåt" in verify:
        raise RuntimeError("Signal-UI: gamla styrkemallssektionen finns kvar")
    if '<div class="dashboard-title">Nästa dagar</div>' in verify and '.week-state .dashboard>.dashboard-card:last-child{display:none}' not in verify:
        raise RuntimeError("Signal-UI: Kommande dagar exponeras fortfarande i normalvyn")
    if verify.find('class="week-state"') < verify.find('<h2 class="section">Aktuell vecka</h2>'):
        raise RuntimeError("Signal-UI: Veckoläge ligger fortfarande före veckoplanen")
    print("Signal-UI OK: beslut först, adaptiv vecka och statistik bakom Veckoläge.")


if __name__ == "__main__":
    main()
