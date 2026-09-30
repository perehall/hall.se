"""Pure renderer for the multi-week training overview."""

from __future__ import annotations

import html
from datetime import date

from training_core.presentation.overview import TrainingOverviewReadModel
from training_core.repositories.icons import SportIconRegistry


WEEKDAY_SHORT = ("Mån", "Tis", "Ons", "Tor", "Fre", "Lör", "Sön")
MONTH_SHORT = (
    "jan", "feb", "mar", "apr", "maj", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
)


def _e(value: object) -> str:
    return html.escape(str(value or ""))


def _fmt_date(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return f"{parsed.day} {MONTH_SHORT[parsed.month - 1]} {parsed.year}"


def _week_url(week_start: date, current_week_start: date) -> str:
    if week_start == current_week_start:
        return "/träning/"
    year, week, _ = week_start.isocalendar()
    return f"/träning/vecka/{year}-W{week:02d}/"


def _icon(registry: SportIconRegistry | None, key: str) -> str:
    if registry is None:
        return ""
    icon = registry.require(key)
    key_escaped = _e(icon.key)
    if icon.solid:
        return (
            f'<svg class="overview-icon icon-{key_escaped}" aria-hidden="true" '
            f'viewBox="{_e(icon.view_box)}" fill="currentColor" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{_e(icon.path)}"/></svg>'
        )
    return (
        f'<svg class="overview-icon icon-{key_escaped}" aria-hidden="true" '
        f'viewBox="{_e(icon.view_box)}" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{_e(icon.path)}"/></svg>'
    )


def _icon_group(registry: SportIconRegistry | None, keys: tuple[str, ...]) -> str:
    if not keys:
        return ""
    return '<span class="overview-icons">' + "".join(_icon(registry, key) for key in keys) + "</span>"


def _context_html(model: TrainingOverviewReadModel) -> str:
    context = model.context
    if context is None:
        return (
            '<section class="overview-context unavailable">'
            '<div><span>Utvecklingsblock</span><strong>Kontext saknas</strong></div>'
            '<p>Mål- och blockkopplingen kunde inte byggas från nuvarande planeringsdata.</p>'
            '</section>'
        )

    block = context.active_block
    block_html = ""
    if block is not None:
        primary = " · ".join(block.primary_capabilities) or "Ej specificerat"
        dates = " – ".join(
            value for value in (_fmt_date(block.start_date), _fmt_date(block.end_date)) if value
        )
        checkpoint = _fmt_date(block.evaluation_date)
        block_html = (
            '<div class="overview-context-block">'
            '<span>Aktuellt utvecklingsblock</span>'
            f'<strong>{_e(block.title or "Aktivt block")}</strong>'
            f'<small>{_e(dates)}</small>'
            f'<p><b>Primärt nu:</b> {_e(primary)}</p>'
            + (f'<p><b>Nästa checkpoint:</b> {_e(checkpoint)}</p>' if checkpoint else "")
            + '</div>'
        )

    goals = []
    for goal in context.goals[:3]:
        meta = " · ".join(value for value in (goal.target, _fmt_date(goal.target_date)) if value)
        goals.append(
            '<article class="overview-goal">'
            f'<strong>{_e(goal.label)}</strong>'
            + (f'<span>{_e(meta)}</span>' if meta else "")
            + '</article>'
        )
    goals_html = "".join(goals) or '<p class="overview-empty">Inga kanoniska mål publicerade.</p>'

    return (
        '<section class="overview-context">'
        f'{block_html}'
        '<div class="overview-context-goals"><span>Mot mål</span>'
        f'<div>{goals_html}</div></div>'
        '</section>'
    )


def _planned_item(workout, registry: SportIconRegistry | None) -> str:
    focus = (
        f'<span class="overview-focus">{_e(workout.development_focus)}</span>'
        if workout.development_focus else ""
    )
    return (
        f'<div class="overview-workout planned state-{_e(workout.state)}" '
        f'data-workout-key="{_e(workout.workout_key)}">'
        f'{_icon_group(registry, workout.icon_keys)}'
        f'<span class="overview-workout-copy"><strong>{_e(workout.session)}</strong>{focus}</span>'
        '</div>'
    )


def _actual_item(activity, registry: SportIconRegistry | None) -> str:
    facts = []
    if activity.distance_m > 0:
        facts.append(activity.distance)
    if activity.duration_s > 0:
        facts.append(activity.duration)
    detail = " · ".join(facts)
    return (
        '<div class="overview-workout actual">'
        f'{_icon(registry, activity.icon_key)}'
        f'<span class="overview-workout-copy"><strong>{_e(activity.label)}</strong>'
        + (f'<span class="overview-facts">{_e(detail)}</span>' if detail else "")
        + '</span></div>'
    )


def _day_html(day, *, current_date: date, registry: SportIconRegistry | None) -> str:
    classes = ["overview-day", f"state-{day.state}"]
    if day.local_date == current_date:
        classes.append("today")
    actual = "".join(_actual_item(item, registry) for item in day.actual_activities)
    planned = "".join(_planned_item(item, registry) for item in day.planned_workouts)

    if actual and planned:
        body = (
            f'<div class="overview-layer actual-layer">{actual}</div>'
            '<div class="overview-plan-label">Plan</div>'
            f'<div class="overview-layer planned-layer">{planned}</div>'
        )
    elif actual:
        body = f'<div class="overview-layer actual-layer">{actual}</div>'
    elif planned:
        body = f'<div class="overview-layer planned-layer">{planned}</div>'
    else:
        body = '<span class="overview-rest">Vila</span>'

    return (
        f'<div class="{" ".join(classes)}" data-date="{day.local_date.isoformat()}">'
        '<div class="overview-day-head">'
        f'<span>{WEEKDAY_SHORT[day.local_date.weekday()]}</span>'
        f'<b>{day.local_date.day}</b>'
        '</div>'
        f'<div class="overview-day-body">{body}</div>'
        '</div>'
    )


def _week_html(
    week,
    *,
    current_date: date,
    current_week_start: date,
    registry: SportIconRegistry | None,
) -> str:
    relation = (
        "current" if week.start == current_week_start
        else "past" if week.end < current_date
        else "future"
    )
    rest_days = max(0, 7 - week.planned_training_days)
    metrics = [
        f"Plan {week.planned_count} pass",
        f"Utfört {week.completed_count}",
    ]
    if week.completed_count:
        metrics.append(week.actual_duration)
        if week.actual_distance_m > 0:
            metrics.append(week.actual_distance)
    if relation != "past":
        metrics.append(f"{rest_days} planerade vilodagar")
    metric_text = " · ".join(metrics)
    days = "".join(
        _day_html(day, current_date=current_date, registry=registry)
        for day in week.days
    )
    return (
        f'<section class="overview-week relation-{relation}" data-week="{_e(week.iso_key)}">'
        '<header class="overview-week-summary">'
        f'<a href="{_week_url(week.start, current_week_start)}">'
        f'<strong>V{week.week_number}</strong>'
        f'<span>{week.start.day} {MONTH_SHORT[week.start.month - 1]} – '
        f'{week.end.day} {MONTH_SHORT[week.end.month - 1]}</span></a>'
        f'<p>{_e(metric_text)}</p>'
        '</header>'
        f'<div class="overview-week-days">{days}</div>'
        '</section>'
    )


def _review_html(model: TrainingOverviewReadModel) -> str:
    future_weeks = [week for week in model.weeks if week.start > model.current_week_start]
    future_with_plan = [week for week in future_weeks if week.planned_count > 0]
    missing = [week for week in future_weeks if week.planned_count == 0]
    multipass_days = [
        day
        for week in model.weeks
        for day in week.days
        if day.planned_count > 1
    ]
    fixed_count = sum(week.fixed_count for week in model.weeks)

    rows = [
        (
            "Planeringshorisont",
            f"{len(future_with_plan)} av {len(future_weeks)} synliga framtidsveckor har planerade pass.",
            "attention" if missing else "ok",
        ),
        (
            "Multipass",
            f"{len(multipass_days)} dagar innehåller fler än ett självständigt planerat pass.",
            "neutral",
        ),
        (
            "Fasta pass",
            f"{fixed_count} pass är markerade som fasta i den synliga perioden.",
            "neutral",
        ),
    ]
    if missing:
        labels = ", ".join(f"V{week.week_number}" for week in missing)
        rows.append(
            (
                "Ej materialiserad plan",
                f"{labels} saknar planerade träningspass i den kanoniska databasen. Översikten fyller inte ut dem med antaganden.",
                "attention",
            )
        )

    content = "".join(
        f'<article class="overview-review-item {state}"><span>{_e(label)}</span>'
        f'<p>{_e(copy)}</p></article>'
        for label, copy, state in rows
    )
    return (
        '<details class="overview-review">'
        '<summary>Granska plan</summary>'
        '<div class="overview-review-copy">'
        '<p>Strukturkontrollen visar endast sådant som kan härledas direkt ur planens kanoniska data. '
        'Den klassar ännu inte belastning som bra eller dålig utan strukturerade dos-/intensitetsmått.</p>'
        f'<div class="overview-review-grid">{content}</div></div></details>'
    )


OVERVIEW_CSS = r"""
:root{
  color-scheme:light;
  --bg:#F6F7F5;--card:#FCFCFB;--elevated:#FFFFFF;
  --text:#171918;--secondary:#5E6661;--muted:#737A75;
  --line:#E2E6E1;--line-soft:#ECEFEB;--accent:#5964E8;
  --accent-soft:#F1F2FD;--green:#287A54;--green-soft:#EDF7F1;
  --amber:#8A6418;--amber-soft:#FBF6E7;
  font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif
}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);line-height:1.4}
a{color:inherit}.overview-shell{width:min(1500px,100%);margin:auto;padding:24px 18px 72px}
.overview-topnav{display:flex;justify-content:flex-end;gap:18px;margin-bottom:38px;font-size:.78rem}
.overview-topnav a{color:var(--muted);text-decoration:none}.overview-topnav a.active{color:var(--text);font-weight:720}
.overview-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin:0 0 22px}
.overview-kicker{font-size:.67rem;text-transform:uppercase;letter-spacing:.08em;font-weight:800;color:var(--muted)}
.overview-hero h1{font-size:clamp(2rem,4vw,3.4rem);letter-spacing:-.05em;line-height:1;margin:7px 0 8px}
.overview-hero p{margin:0;color:var(--secondary);max-width:760px}.overview-range{color:var(--muted);font-size:.76rem;white-space:nowrap}
.overview-context{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:12px;margin-bottom:18px}
.overview-context>div{border:1px solid var(--line);background:var(--card);border-radius:16px;padding:15px 17px}
.overview-context span{display:block;color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;font-weight:760}
.overview-context strong{display:block;margin-top:5px;font-size:.98rem}.overview-context small{display:block;color:var(--muted);font-size:.72rem;margin-top:3px}
.overview-context p{margin:9px 0 0;color:var(--secondary);font-size:.78rem}
.overview-context p+p{margin-top:4px}.overview-context-goals>div{display:grid;gap:7px;margin-top:8px}
.overview-goal{padding:8px 0;border-top:1px solid var(--line-soft)}.overview-goal:first-child{border-top:0;padding-top:0}
.overview-goal strong{font-size:.82rem;margin:0}.overview-goal span{font-size:.7rem;text-transform:none;letter-spacing:0;margin-top:2px}
.overview-calendar{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:var(--card)}
.overview-week{display:grid;grid-template-columns:165px minmax(0,1fr);border-top:1px solid var(--line)}
.overview-week:first-child{border-top:0}.overview-week.relation-current{background:#FAFAFF;box-shadow:inset 3px 0 0 var(--accent)}
.overview-week-summary{padding:14px 14px;border-right:1px solid var(--line);background:rgba(255,255,255,.46)}
.overview-week-summary a{text-decoration:none}.overview-week-summary strong{display:block;font-size:1.05rem}.overview-week-summary span{display:block;margin-top:2px;color:var(--muted);font-size:.68rem}
.overview-week-summary p{margin:10px 0 0;color:var(--secondary);font-size:.7rem;line-height:1.5}
.overview-week-days{display:grid;grid-template-columns:repeat(7,minmax(125px,1fr));min-width:875px}
.overview-day{min-height:126px;padding:10px 9px;border-left:1px solid var(--line-soft);position:relative}
.overview-day:first-child{border-left:0}.overview-day.today{box-shadow:inset 0 0 0 2px var(--accent);z-index:1}
.overview-day-head{display:flex;align-items:baseline;justify-content:space-between;gap:6px;margin-bottom:9px}
.overview-day-head span{font-size:.62rem;color:var(--muted);font-weight:760;text-transform:uppercase;letter-spacing:.04em}
.overview-day-head b{font-size:.7rem;color:var(--secondary)}.overview-day-body{display:grid;gap:7px}
.overview-layer{display:grid;gap:6px}.overview-plan-label{color:var(--muted);font-size:.58rem;font-weight:760;text-transform:uppercase;letter-spacing:.05em;margin-top:2px}
.overview-workout{display:flex;gap:6px;align-items:flex-start;min-width:0;padding:7px;border-radius:9px}
.overview-workout.planned{background:#F2F4F8}.overview-workout.planned.state-fixed{background:var(--accent-soft)}
.overview-workout.actual{background:var(--green-soft)}.overview-workout-copy{min-width:0;display:block}
.overview-workout strong{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;font-size:.7rem;line-height:1.32}
.overview-focus,.overview-facts{display:block;margin-top:3px;color:var(--muted);font-size:.61rem;line-height:1.28}
.overview-icon{width:13px;height:13px;flex:0 0 13px;color:var(--secondary);margin-top:1px}.overview-icons{display:flex;gap:2px}
.overview-rest{display:block;color:#9AA09C;font-size:.67rem;padding-top:4px}.overview-empty{color:var(--muted);font-size:.76rem}
.overview-review{margin-top:18px;border:1px solid var(--line);border-radius:16px;background:var(--card);overflow:hidden}
.overview-review>summary{cursor:pointer;list-style:none;padding:14px 16px;font-size:.8rem;font-weight:760}
.overview-review>summary::-webkit-details-marker{display:none}.overview-review>summary:after{content:" +";color:var(--muted)}
.overview-review[open]>summary:after{content:" −"}.overview-review-copy{padding:0 16px 16px}
.overview-review-copy>p{margin:0 0 12px;color:var(--muted);font-size:.72rem;max-width:900px}
.overview-review-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.overview-review-item{padding:10px 11px;border:1px solid var(--line-soft);border-radius:12px;background:var(--elevated)}
.overview-review-item.attention{background:var(--amber-soft);border-color:#EFE3BF}
.overview-review-item span{font-size:.63rem;color:var(--muted);font-weight:800;text-transform:uppercase;letter-spacing:.04em}
.overview-review-item p{margin:5px 0 0;font-size:.73rem;color:var(--secondary)}
@media(max-width:900px){
  .overview-shell{padding:20px 12px 56px}.overview-topnav{justify-content:flex-start;overflow:auto;white-space:nowrap}
  .overview-hero{display:block}.overview-range{display:block;margin-top:9px}
  .overview-context{grid-template-columns:1fr}.overview-calendar{overflow-x:auto}
  .overview-week{grid-template-columns:135px minmax(875px,1fr)}
  .overview-review-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:620px){
  .overview-review-grid{grid-template-columns:1fr}
}
"""


def render_overview_document(
    model: TrainingOverviewReadModel,
    *,
    current_date: date,
    sport_icons: SportIconRegistry | None = None,
) -> str:
    weeks = "".join(
        _week_html(
            week,
            current_date=current_date,
            current_week_start=model.current_week_start,
            registry=sport_icons,
        )
        for week in model.weeks
    )
    start_label = f"{model.start.day} {MONTH_SHORT[model.start.month - 1]}"
    end_label = f"{model.end.day} {MONTH_SHORT[model.end.month - 1]} {model.end.year}"
    return (
        '<!doctype html><html lang="sv"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Översikt · Träning</title>'
        f'<style>{OVERVIEW_CSS}</style></head><body><div class="overview-shell">'
        '<nav class="overview-topnav">'
        '<a href="/träning/">Aktuell vecka</a>'
        '<a class="active" href="/träning/oversikt/">Översikt</a>'
        '<a href="/träning/utveckling/">Mål &amp; utveckling</a>'
        '<a href="/träning/onboarding/">Träningsprofil</a>'
        '</nav>'
        '<header class="overview-hero"><div>'
        '<div class="overview-kicker">Coachens planeringsyta</div>'
        '<h1>Översikt</h1>'
        '<p>Åtta veckor i samma vy. Plan och utfall visas sida vid sida så att rytm, '
        'multipass, vilodagar, planeringshorisont och koppling till utvecklingsblocket går att granska utan att lämna kalendern.</p>'
        '</div>'
        f'<span class="overview-range">{_e(start_label)} – {_e(end_label)}</span></header>'
        f'{_context_html(model)}'
        f'<main class="overview-calendar" aria-label="Åtta veckors träningsöversikt">{weeks}</main>'
        f'{_review_html(model)}'
        '</div></body></html>'
    )
