#!/usr/bin/env python3
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
WEEK_DIR = ROOT / "vecka"

CSS_MARKER = "/* week-shell-v1 */"
SYSTEM_DIALOG_ID = "trainingSystemSheet"

CSS = r'''
/* week-shell-v1 */
html{scrollbar-gutter:stable}
body{font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;font-size:16px;line-height:1.42}
.wrap{width:min(100%,720px)!important;max-width:720px;margin:0 auto;padding:20px 16px 56px}
header{padding:8px 2px 18px}
.eyebrow{font-size:.76rem;line-height:1.2}
h1{font-size:clamp(2rem,8vw,3.2rem);line-height:1;margin:0 0 8px;letter-spacing:-.04em}
.sub{font-size:.96rem;line-height:1.4}
.hero{border-radius:20px;padding:18px 20px;margin:8px 0 18px}
.hero h2{font-size:1.08rem;line-height:1.35}
.section{font-size:1.22rem;line-height:1.3;margin:28px 0 12px}
.day{border-radius:20px;padding:16px 17px;margin:12px 0}
.daytop{margin-bottom:10px}
.dow{font-size:.82rem;line-height:1.25}
.date{font-size:.85rem;line-height:1.3}
.session{font-size:1.2rem;line-height:1.28;margin:4px 0 6px}
.reason{font-size:.9rem;line-height:1.48}
.week-nav{grid-template-columns:1fr auto 1fr;gap:10px;margin:-4px 0 16px;padding:9px 10px;border-radius:14px}
.week-nav a{font-size:.82rem;line-height:1.25}
.week-nav-center strong{font-size:.86rem;line-height:1.15}
.week-nav-center span{font-size:.59rem;line-height:1.15}
.reference-tools{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-start;margin:12px 0 8px}
.reference-chip{appearance:none;border:1px solid #cbd5e1;background:#fff;color:#334155;border-radius:999px;padding:9px 13px;font:inherit;font-size:.82rem;font-weight:800;line-height:1.2;cursor:pointer;box-shadow:0 3px 10px rgba(15,23,42,.04)}
.system-window{position:fixed;inset:auto;width:min(520px,calc(100vw - 32px));max-height:calc(100vh - 32px);left:50%;top:50%;transform:translate(-50%,-50%);margin:0;border:1px solid #e2e8f0;border-radius:18px;padding:0;background:#fff;color:#0f172a;box-shadow:0 24px 70px rgba(15,23,42,.28);overflow:auto}
.system-window::backdrop{background:rgba(15,23,42,.38)}
.system-inner{padding:0 18px 18px}
.system-head{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0 -18px 8px;padding:14px 18px 10px;background:#fff;border-bottom:1px solid #f1f5f9}
.system-head h2{font-size:1.1rem;line-height:1.25;margin:0}
.system-close{appearance:none;border:0;background:#f1f5f9;color:#334155;border-radius:999px;padding:7px 10px;font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}
.system-lead{margin:10px 0 8px;color:#334155;font-size:.92rem;line-height:1.45}
.system-list{margin:0;padding:0;list-style:none}
.system-list li{padding:9px 0;border-top:1px solid #e2e8f0;color:#475569;font-size:.86rem;line-height:1.42}
.system-list li:first-child{border-top:0}
.system-list strong{color:#0f172a}
@media (max-width:620px){
  .wrap{width:100%!important;max-width:720px;padding:20px 13px 56px}
  .day{border-radius:17px;padding:15px}
  .week-nav{padding:8px}
  .week-nav a{font-size:.75rem}
  .week-nav-center strong{font-size:.8rem}
  .system-window{width:min(100% - 16px,720px);max-height:min(78vh,680px);left:50%!important;top:auto!important;bottom:0;transform:translateX(-50%)!important;border:0;border-radius:22px 22px 0 0}
  .system-inner{padding:0 18px calc(20px + env(safe-area-inset-bottom))}
}
'''

SYSTEM_DIALOG = f'''
<dialog id="{SYSTEM_DIALOG_ID}" class="system-window" aria-labelledby="trainingSystemTitle">
  <div class="system-inner">
    <div class="system-head">
      <h2 id="trainingSystemTitle">Om träningssystemet</h2>
      <button class="system-close" type="button" onclick="document.getElementById('{SYSTEM_DIALOG_ID}').close()">Stäng</button>
    </div>
    <p class="system-lead">En adaptiv veckoplan som kopplar planerad träning till faktiskt utfall och återhämtning.</p>
    <ul class="system-list">
      <li><strong>Plan:</strong> aktuell vecka är tydligast, nästa vecka preliminär och avslutade veckor sparas som historik.</li>
      <li><strong>Data:</strong> Strava används för genomförd träning, Garmin via Intervals.icu som privat återhämtningskontext och SMHI för väder.</li>
      <li><strong>Anpassning:</strong> efter pass och regelbunden synk vägs närbelastningen in. AI-coachen kan konservativt behålla, minska eller ersätta belastning.</li>
      <li><strong>Princip:</strong> kontinuitet, absorberbar belastning och långsiktig progression går före maximal träningsmängd.</li>
    </ul>
  </div>
</dialog>
<script>
function openTrainingSystemInfo() {{
  document.getElementById('{SYSTEM_DIALOG_ID}').showModal();
}}
</script>
'''


def strength_reference(items):
    lis = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f'''<div class="reference-tools">
  <button class="reference-chip" type="button" onclick="openStrengthWindow()">Styrkemall</button>
</div>
<dialog id="strengthSheet" class="system-window strength-window" aria-labelledby="strengthWindowTitle">
  <div class="system-inner sheet-inner">
    <div class="system-head sheet-head"><h2 id="strengthWindowTitle">Styrkemall</h2><button class="system-close sheet-close" type="button" onclick="document.getElementById('strengthSheet').close()">Stäng</button></div>
    <p class="system-lead sheet-note">Referens. Aktuellt styrkebeslut styrs av veckoplanen.</p>
    <ul class="system-list strength-list">{lis}</ul>
  </div>
</dialog>
<script>
function openStrengthWindow() {{
  document.getElementById('strengthSheet').showModal();
}}
</script>
'''


def normalize_legacy_strength(page):
    if 'id="strengthSheet"' in page:
        return page
    pattern = re.compile(
        r'<h2 class="section">Styrkemall framåt</h2><div class="principles">(?P<body>.*?)</div>\s*(?=<footer>)',
        re.S,
    )
    match = pattern.search(page)
    if not match:
        return page
    items = [
        re.sub(r"<[^>]+>", "", value).strip()
        for value in re.findall(r'<div class="principle">(.*?)</div>', match.group("body"), re.S)
    ]
    items = [item for item in items if item]
    return page[: match.start()] + strength_reference(items) + page[match.end() :]


def add_system_info(page):
    if f'id="{SYSTEM_DIALOG_ID}"' in page:
        return page

    button = '<button class="reference-chip" type="button" onclick="openTrainingSystemInfo()">Om systemet</button>'
    toolbar = re.search(r'<div class="reference-tools">(?P<body>.*?)</div>', page, re.S)
    if toolbar:
        body = toolbar.group("body").rstrip()
        replacement = '<div class="reference-tools">' + body + "\n  " + button + "\n</div>"
        page = page[: toolbar.start()] + replacement + page[toolbar.end() :]
    else:
        if "<footer>" not in page:
            raise RuntimeError("Veckoskal: footer saknas för systeminfo")
        page = page.replace("<footer>", f'<div class="reference-tools">{button}</div>\n<footer>', 1)

    if "<footer>" not in page:
        raise RuntimeError("Veckoskal: footer saknas efter systemknapp")
    return page.replace("<footer>", SYSTEM_DIALOG + "\n<footer>", 1)


def add_shell_css(page):
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Veckoskal: sidan saknar </style>")
    return page.replace("</style>", CSS + "\n</style>", 1)


def apply_week_shell(page):
    page = normalize_legacy_strength(page)
    page = add_system_info(page)
    page = add_shell_css(page)
    return page


def page_paths():
    paths = [INDEX_FILE]
    if WEEK_DIR.exists():
        paths.extend(sorted(WEEK_DIR.glob("*/index.html")))
    return [path for path in paths if path.exists()]


def main():
    paths = page_paths()
    if not paths:
        raise RuntimeError("Veckoskal: inga träningssidor hittades")

    for path in paths:
        rendered = apply_week_shell(path.read_text(encoding="utf-8"))
        path.write_text(rendered, encoding="utf-8")
        verify = path.read_text(encoding="utf-8")
        required = [
            CSS_MARKER,
            "scrollbar-gutter:stable",
            "width:min(100%,720px)!important",
            'onclick="openTrainingSystemInfo()"',
            f'id="{SYSTEM_DIALOG_ID}"',
            "En adaptiv veckoplan",
        ]
        missing = [marker for marker in required if marker not in verify]
        if missing:
            raise RuntimeError(f"Veckoskal {path}: saknar {missing!r}")
        if "Styrkemall framåt" in verify:
            raise RuntimeError(f"Veckoskal {path}: öppen styrkemall finns kvar")

    print(f"Veckoskal OK: {len(paths)} sidor delar bredd, typografi och systeminfo.")


if __name__ == "__main__":
    main()
