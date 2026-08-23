#!/usr/bin/env python3
import html

REVIEW_CSS_MARKER = "/* weekly-review-v1 */"
REVIEW_CSS = r'''
/* weekly-review-v1 */
.week-review{margin:18px 0 24px}.week-review-card{background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:16px;box-shadow:0 8px 24px rgba(15,23,42,.05)}.week-review-title{font-size:.76rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em;color:#5b21b6;margin-bottom:9px}.week-review-summary{font-size:1rem;font-weight:750;line-height:1.48;color:#1e293b}.week-review-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:13px 0}.week-review-metric{padding:9px 10px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc}.week-review-metric strong{display:block;font-size:.96rem}.week-review-metric span{display:block;margin-top:2px;color:#64748b;font-size:.66rem}.week-review-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.week-review-block{padding:11px 12px;border:1px solid #e2e8f0;border-radius:13px;background:#fafafa}.week-review-block strong{display:block;margin-bottom:5px;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:#475569}.week-review-block ul{margin:0;padding-left:18px;color:#334155;font-size:.86rem;line-height:1.45}.week-review-block li+li{margin-top:4px}.week-review-copy{color:#334155;font-size:.88rem;line-height:1.48}.week-review-next{margin-top:10px;padding:11px 12px;border:1px solid #ddd6fe;border-radius:13px;background:#faf5ff;color:#3b0764;font-size:.9rem;line-height:1.48}.week-review-next strong{display:block;margin-bottom:4px;font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;color:#6d28d9}.week-review details{margin-top:9px;color:#64748b;font-size:.82rem}.week-review details summary{cursor:pointer;font-weight:750;color:#475569}
@media (max-width:620px){.week-review-metrics{grid-template-columns:repeat(2,1fr)}.week-review-grid{grid-template-columns:1fr}.week-review-card{padding:14px}}
'''


def fmt_duration(seconds):
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _list(items):
    return "".join(f"<li>{html.escape(item)}</li>" for item in items or [])


def add_review_css(page):
    if REVIEW_CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Veckoutvärdering UI: kunde inte hitta </style>")
    return page.replace("</style>", REVIEW_CSS + "\n</style>", 1)


def render_review_html(review):
    facts = review.get("facts") or {}
    assessment = review.get("assessment") or {}
    uncertainties = assessment.get("uncertainties") or []
    uncertainties_html = ""
    if uncertainties:
        uncertainties_html = (
            '<details><summary>Osäkerheter</summary><ul>'
            + _list(uncertainties)
            + "</ul></details>"
        )
    return f'''<section class="week-review" data-week-review="{html.escape(str(review.get("week_key") or ""))}">
  <div class="week-review-card">
    <div class="week-review-title">Veckoutvärdering</div>
    <div class="week-review-summary">{html.escape(assessment.get("summary") or "")}</div>
    <div class="week-review-metrics">
      <div class="week-review-metric"><strong>{int(facts.get("activity_count") or 0)}</strong><span>aktiviteter</span></div>
      <div class="week-review-metric"><strong>{int(facts.get("active_days") or 0)}</strong><span>aktiva dagar</span></div>
      <div class="week-review-metric"><strong>{fmt_duration(facts.get("total_activity_time_s"))}</strong><span>total aktivitetstid</span></div>
      <div class="week-review-metric"><strong>{int(facts.get("recreation_activity_count") or 0)}</strong><span>rekreation</span></div>
    </div>
    <div class="week-review-grid">
      <div class="week-review-block"><strong>Det som fungerade</strong><ul>{_list(assessment.get("worked"))}</ul></div>
      <div class="week-review-block"><strong>Inte enligt plan</strong><ul>{_list(assessment.get("not_as_planned"))}</ul></div>
      <div class="week-review-block"><strong>Belastning & kontinuitet</strong><div class="week-review-copy">{html.escape(assessment.get("load_continuity") or "")}</div></div>
      <div class="week-review-block"><strong>Viktigaste lärdomen</strong><div class="week-review-copy">{html.escape(assessment.get("key_lesson") or "")}</div></div>
    </div>
    <div class="week-review-next"><strong>Till nästa veckas planering</strong>{html.escape(assessment.get("next_week_implication") or "")}</div>
    {uncertainties_html}
  </div>
</section>'''


def insert_review_after_dashboard(page, review):
    marker = f'data-week-review="{review.get("week_key")}"'
    if marker in page:
        return page
    page = add_review_css(page)
    dashboard_end = page.find("</section>")
    if dashboard_end < 0:
        raise RuntimeError("Veckoutvärdering UI: dashboardens </section> saknas")
    dashboard_end += len("</section>")
    return page[:dashboard_end] + "\n" + render_review_html(review) + page[dashboard_end:]
