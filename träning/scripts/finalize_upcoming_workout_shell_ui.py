#!/usr/bin/env python3
"""Render future training days through one shared action-first workout shell.

The canonical plan remains unchanged. This finalizer only normalizes presentation
so sport-specific prescriptions sit inside one consistent visual hierarchy.
Completed days are handled by finalize_completed_day_summary_ui.py.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finalize_day_session_icons import SPORT_ICON_KEYS, icon

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ICON_FILE = ROOT / "data" / "sport_icons.json"
INDEX_FILE = ROOT / "index.html"
WEEK_DIR = ROOT / "vecka"

CSS_MARKER = "/* future-workout-shell-v1 */"
DAY_RE = re.compile(
    r'<div class="day(?P<classes>[^"]*)" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">'
)
DIV_RE = re.compile(r"<div\b[^>]*>|</div>", re.I)

CSS = r"""
/* future-workout-shell-v1 */
.day.future-workout-applied>.session,
.day.future-workout-applied>.swim-workout,
.day.future-workout-applied>.workout-prescription,
.day.future-workout-applied>.development-focus,
.day.future-workout-applied>.next-weather,
.day.future-workout-applied>.swim-equipment-line,
.day.future-workout-applied>.card-v2-footer{display:none!important}
.future-workout-shell{color:var(--qp-text,#111827)}
.future-workout-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.future-workout-title{display:flex;align-items:center;gap:8px;min-width:0;color:var(--qp-text,#111827);font-size:1.07rem;font-weight:820;line-height:1.3;letter-spacing:-.016em}
.future-workout-title .sport-icon{width:20px;height:20px;flex:0 0 auto;color:var(--qp-secondary,#59636f)}
.future-workout-title .icon-swim,.future-workout-title .icon-bike,.future-workout-title .icon-enduro,.future-workout-title .icon-strength{width:22px}
.future-workout-title-text{min-width:0}
.future-workout-meta{margin-top:3px;color:var(--qp-secondary,#64748b);font-size:.8rem;line-height:1.38}
.future-workout-weather{display:flex;align-items:center;gap:5px;margin-top:9px;color:var(--qp-secondary,#59636f);font-size:.76rem;line-height:1.4}
.future-workout-weather .weather-label{color:var(--qp-tertiary,#64748b)}
.future-workout-weather .weather-icon{width:16px!important;height:16px!important;margin-right:1px!important}
.future-workout-panel{margin-top:12px;border:1px solid var(--qp-line,#e2e8f0);border-radius:15px;background:rgba(255,255,255,.7);overflow:hidden}
.future-workout-section{padding:12px 13px}
.future-workout-section+.future-workout-section{border-top:1px solid var(--qp-line-soft,#eef2f4)}
.future-workout-label{display:block;margin-bottom:5px;color:var(--qp-tertiary,#64748b);font-size:.63rem;font-weight:850;letter-spacing:.065em;text-transform:uppercase}
.future-workout-panel .workout-prescription{display:grid!important;grid-template-columns:max-content minmax(0,1fr)!important;margin:0!important;padding:0!important;border:0!important;background:transparent!important}
.future-workout-panel .workout-prescription-head{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
.future-workout-panel .workout-prescription-row{display:contents!important}
.future-workout-panel .workout-prescription-dose{padding:5px 12px 5px 0!important;color:var(--qp-text,#111827)!important;font-size:.9rem!important;font-weight:800!important;line-height:1.35!important;text-align:right!important;white-space:nowrap!important;font-variant-numeric:tabular-nums}
.future-workout-panel .workout-prescription-text{min-width:0;padding:5px 0 5px 12px!important;border-left:1px solid var(--qp-line,#e2e8f0)!important;color:var(--qp-secondary,#475569)!important;font-size:.82rem!important;line-height:1.42!important}
.future-workout-simple{margin:0;color:var(--qp-secondary,#475569);font-size:.82rem;line-height:1.45}
.future-workout-focus{margin:0;color:var(--qp-secondary,#475569);font-size:.82rem;line-height:1.45}
.future-workout-details{margin-top:11px;border:1px solid var(--qp-line,#e2e8f0);border-radius:15px;background:rgba(255,255,255,.5)}
.future-workout-details>summary{position:relative;cursor:pointer;list-style:none;padding:11px 38px 11px 13px}
.future-workout-details>summary::-webkit-details-marker{display:none}
.future-workout-details>summary:after{content:"⌄";position:absolute;right:14px;top:50%;transform:translateY(-53%);color:var(--qp-tertiary,#64748b);font-size:1rem}
.future-workout-details[open]>summary:after{content:"⌃"}
.future-workout-details-title{display:block;color:var(--qp-text,#111827);font-size:.83rem;font-weight:800}
.future-workout-details-subtitle{display:block;margin-top:2px;color:var(--qp-tertiary,#64748b);font-size:.71rem}
.future-workout-details-body{padding:0 13px 12px;border-top:1px solid var(--qp-line-soft,#eef2f4)}
.future-workout-detail{padding-top:10px}
.future-workout-detail+.future-workout-detail{margin-top:9px;border-top:1px solid var(--qp-line-soft,#eef2f4)}
.future-workout-detail-label{display:block;margin-bottom:4px;color:var(--qp-tertiary,#64748b);font-size:.63rem;font-weight:850;letter-spacing:.06em;text-transform:uppercase}
.future-workout-detail p{margin:0;color:var(--qp-secondary,#475569);font-size:.78rem;line-height:1.46}
.future-workout-sync{display:inline-flex;align-items:center;gap:5px;color:var(--qp-tertiary,#64748b);font-size:.72rem;font-weight:650}
.future-workout-sync svg{width:13px;height:13px}
@media(max-width:620px){
  .future-workout-panel,.future-workout-details{border-radius:13px}
  .future-workout-section{padding:11px 12px}
  .future-workout-panel .workout-prescription-dose{padding-right:9px!important;font-size:.86rem!important}
  .future-workout-panel .workout-prescription-text{padding-left:9px!important;font-size:.79rem!important}
}
""".strip()


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def balanced_div_end(text: str, start: int) -> int:
    depth = 0
    for match in DIV_RE.finditer(text, start):
        if match.group(0).lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    raise RuntimeError("Future workout shell: obalanserad div-struktur.")


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or ""))).strip()


def compact_reason(value: str, max_chars: int = 220) -> str:
    plain = strip_tags(value)
    if not plain:
        return ""
    for marker in (
        " Valet utgår från",
        " Veckobeslut:",
        " materialiserad relation:",
        " Katalogen innehåller",
    ):
        if marker in plain:
            plain = plain.split(marker, 1)[0].strip()
    sentences = re.split(r"(?<=[.!?])\s+", plain)
    selected = " ".join(sentences[:2]).strip()
    if len(selected) <= max_chars:
        return selected
    clipped = selected[: max_chars - 1].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(".,;:") + "…"


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", strip_tags(value)).strip().lower()


def split_session(day: dict) -> tuple[str, str]:
    session = str(day.get("session") or "").strip()
    if not session:
        return "Planerat pass", ""
    parts = [part.strip() for part in session.split(" · ") if part.strip()]
    sport = str(day.get("sport") or "").strip().lower()
    if len(parts) == 1:
        return parts[0], ""
    if sport == "swim" and len(parts) >= 2:
        return " · ".join(parts[:2]), " · ".join(parts[2:])
    if sport in {"run", "running", "trail", "bike", "cycling", "mtb", "xc"} and len(parts) >= 2:
        return " · ".join(parts[:2]), " · ".join(parts[2:])
    if sport in {"enduro", "strength"}:
        return parts[0], " · ".join(parts[1:])
    return " · ".join(parts[:2]), " · ".join(parts[2:])


def first_div(block: str, class_name: str) -> str:
    match = re.search(rf'<div class="[^"]*\b{re.escape(class_name)}\b[^"]*"', block)
    if not match:
        return ""
    end = balanced_div_end(block, match.start())
    return block[match.start():end]


def inner_text_from_class(block: str, class_name: str) -> str:
    match = re.search(
        rf'<[^>]+class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>(.*?)</[^>]+>',
        block,
        re.S | re.I,
    )
    return strip_tags(match.group(1)) if match else ""


def reason_from_block(block: str, fallback: str) -> str:
    match = re.search(r'<div class="reason">(.*?)</div>', block, re.S | re.I)
    return compact_reason(match.group(1) if match else fallback)


def focus_from_block(block: str, fallback: str) -> str:
    match = re.search(
        r'<div class="development-focus">.*?<span>(.*?)</span>\s*</div>',
        block,
        re.S | re.I,
    )
    return strip_tags(match.group(1)) if match else strip_tags(fallback)


def prescription_from_block(block: str) -> str:
    return first_div(block, "workout-prescription")


def weather_from_block(block: str) -> str:
    raw = first_div(block, "next-weather")
    if not raw:
        return ""
    raw = re.sub(
        r'class="next-weather"',
        'class="future-workout-weather"',
        raw,
        count=1,
    )
    raw = re.sub(r'\sstyle="[^"]*"', "", raw, count=1)
    return raw


def sync_from_block(block: str) -> str:
    match = re.search(
        r'<div class="device-sync-state [^"]+"[^>]*>(.*?)</div>',
        block,
        re.S | re.I,
    )
    if not match:
        return ""
    inner = match.group(1).strip()
    return f'<span class="future-workout-sync">{inner}</span>'


def icon_html(day: dict, registry: dict) -> str:
    sport = str(day.get("sport") or "").strip().lower()
    key = SPORT_ICON_KEYS.get(sport)
    if not key:
        return ""
    return icon(key, registry)


def prescription_text(prescription: str) -> str:
    return normalize(" ".join(re.findall(
        r'class="workout-prescription-text">(.*?)</span>',
        prescription,
        re.S | re.I,
    )))


def render_shell(day: dict, block: str, registry: dict) -> str:
    title, meta = split_session(day)
    prescription = prescription_from_block(block)
    focus = focus_from_block(block, str(day.get("development_focus") or ""))
    reason = reason_from_block(block, str(day.get("reason") or ""))
    weather = weather_from_block(block)
    sync = sync_from_block(block)

    if focus and prescription and normalize(focus) in prescription_text(prescription):
        focus = ""

    sections = []
    if prescription:
        sections.append(
            '<div class="future-workout-section">'
            '<span class="future-workout-label">Pass</span>'
            + prescription
            + '</div>'
        )
    elif focus:
        sections.append(
            '<div class="future-workout-section">'
            '<span class="future-workout-label">Pass</span>'
            f'<p class="future-workout-simple">{html.escape(focus)}</p>'
            '</div>'
        )
        focus = ""

    if focus:
        sections.append(
            '<div class="future-workout-section">'
            '<span class="future-workout-label">Fokus</span>'
            f'<p class="future-workout-focus">{html.escape(focus)}</p>'
            '</div>'
        )

    details = []
    if reason:
        details.append(
            '<div class="future-workout-detail">'
            '<span class="future-workout-detail-label">Varför nu</span>'
            f'<p>{html.escape(reason)}</p>'
            '</div>'
        )
    if sync:
        details.append(
            '<div class="future-workout-detail">'
            '<span class="future-workout-detail-label">Klocka</span>'
            + sync
            + '</div>'
        )

    details_html = ""
    if details:
        details_html = (
            '<details class="future-workout-details">'
            '<summary><span class="future-workout-details-title">Plan och motivering</span>'
            '<span class="future-workout-details-subtitle">Varför passet ligger här och praktisk status</span></summary>'
            '<div class="future-workout-details-body">'
            + "".join(details)
            + '</div></details>'
        )

    meta_html = f'<div class="future-workout-meta">{html.escape(meta)}</div>' if meta else ""
    panel_html = '<div class="future-workout-panel">' + "".join(sections) + '</div>' if sections else ""

    return (
        f'<div class="future-workout-shell" data-future-workout-shell="{html.escape(str(day.get("date") or ""))}">'
        '<div class="future-workout-head"><div>'
        f'<div class="future-workout-title">{icon_html(day, registry)}'
        f'<span class="future-workout-title-text">{html.escape(title)}</span></div>'
        + meta_html
        + '</div></div>'
        + weather
        + panel_html
        + details_html
        + '</div>'
    )


def should_transform(day: dict, day_date: str, today: str, activity_dates: set[str]) -> bool:
    if day_date < today:
        return False
    if day_date in activity_dates:
        return False
    status = str(day.get("status") or "").strip().lower()
    if status == "completed":
        return False
    sport = str(day.get("sport") or "").strip().lower()
    session = str(day.get("session") or "").strip().lower()
    if sport in {"open", "rest"} or session in {"ingen planerad träning", "vilodag"}:
        return False
    return True


def apply_shell(
    page: str,
    plan: dict,
    *,
    today: str,
    activity_dates: set[str],
    registry: dict,
) -> tuple[str, int]:
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError("Future workout shell: </style> saknas.")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    plan_map = {
        str(day.get("date")): day
        for day in plan.get("days") or []
        if day.get("date")
    }

    changed = 0
    matches = list(DAY_RE.finditer(page))
    for match in reversed(matches):
        day_date = match.group("date")
        day = plan_map.get(day_date)
        if not day or not should_transform(day, day_date, today, activity_dates):
            continue

        start = match.start()
        end = balanced_div_end(page, start)
        block = page[start:end]
        if 'data-future-workout-shell="' in block:
            continue

        opening_end = block.find(">") + 1
        opening = block[:opening_end]
        classes = [token for token in (match.group("classes") or "").split() if token]
        if "future-workout-applied" not in classes:
            classes.append("future-workout-applied")
        opening = f'<div class="day {" ".join(classes)}" id="dag-{day_date}">'

        daytop = first_div(block, "daytop")
        if not daytop:
            raise RuntimeError(f"Future workout shell: daytop saknas för {day_date}")

        shell = render_shell(day, block, registry)
        new_block = opening + block[opening_end:]
        daytop_pos = new_block.find(daytop, len(opening))
        if daytop_pos < 0:
            raise RuntimeError(f"Future workout shell: daytop kunde inte placeras för {day_date}")
        insert_at = daytop_pos + len(daytop)
        new_block = new_block[:insert_at] + shell + new_block[insert_at:]

        page = page[:start] + new_block + page[end:]
        changed += 1

    return page, changed


def validate_page(page: str, plan: dict, *, today: str, activity_dates: set[str]) -> None:
    if CSS_MARKER not in page:
        raise RuntimeError("Future workout shell: CSS-marker saknas.")
    for day in plan.get("days") or []:
        day_date = str(day.get("date") or "")
        if not day_date or not should_transform(day, day_date, today, activity_dates):
            continue
        marker = f'id="dag-{day_date}"'
        pos = page.find(marker)
        if pos < 0:
            continue
        start = page.rfind('<div class="day', 0, pos)
        end = balanced_div_end(page, start)
        block = page[start:end]
        if f'data-future-workout-shell="{day_date}"' not in block:
            raise RuntimeError(f"Future workout shell: shell saknas för {day_date}")
        if "future-workout-applied" not in block[: block.find(">")]:
            raise RuntimeError(f"Future workout shell: dagklass saknas för {day_date}")
        if 'class="future-workout-title"' not in block:
            raise RuntimeError(f"Future workout shell: titel saknas för {day_date}")
        if 'class="workout-prescription"' in block and 'class="future-workout-panel"' not in block:
            raise RuntimeError(f"Future workout shell: passpanel saknas för {day_date}")


def page_paths(upcoming: dict) -> list[Path]:
    paths = [INDEX_FILE]
    week_key = str(upcoming.get("week_key") or "").strip()
    if week_key:
        candidate = WEEK_DIR / week_key / "index.html"
        if candidate.exists():
            paths.append(candidate)
    return paths


def main() -> int:
    plan = load_json(PLAN_FILE, {"days": []})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    upcoming = load_json(UPCOMING_FILE, {})
    registry = load_json(ICON_FILE, {"icons": {}}).get("icons") or {}
    timezone = str((plan.get("meta") or {}).get("timezone") or "Europe/Stockholm")
    today = datetime.now(ZoneInfo(timezone)).date().isoformat()
    activity_dates = {
        str(activity.get("start_date_local") or activity.get("start_date") or "")[:10]
        for activity in activities.get("activities") or []
        if len(str(activity.get("start_date_local") or activity.get("start_date") or "")) >= 10
    }

    total = 0
    for path in page_paths(upcoming):
        if not path.exists():
            continue
        rendered, changed = apply_shell(
            path.read_text(encoding="utf-8"),
            plan,
            today=today,
            activity_dates=activity_dates,
            registry=registry,
        )
        validate_page(rendered, plan, today=today, activity_dates=activity_dates)
        path.write_text(rendered, encoding="utf-8")
        total += changed

    print(f"Future workout shell OK: {total} kommande träningspass använder gemensam action-first-layout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
