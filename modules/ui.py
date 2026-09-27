"""Look and feel of the LeadScout AI web app: brand theme, HTML components and
the animated search screen. Pure presentation - no business logic here.

Streamlit renders these with st.markdown(..., unsafe_allow_html=True). All
content inserted into HTML goes through esc() first.
"""

import base64
import html
import math
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGO_PATH = ASSETS / "logo_small.png"
ICON_PATH = ASSETS / "icon_small.png"

# Brand colours taken from the logo.
NAVY = "#00163F"
BLUE = "#0263E6"
SKY = "#0D91FD"


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


@lru_cache(maxsize=None)
def data_uri(path: Path) -> str:
    try:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""


# --- Global stylesheet -------------------------------------------------------

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {{
  --navy: {NAVY}; --blue: {BLUE}; --sky: {SKY};
  --ink: #0F1B3D; --muted: #5B6B8C; --line: #E3EAF6; --card: #FFFFFF;
  --soft: #F4F8FF; --red: #FFE1E5; --amber: #FFF1E0; --green: #E3F8EE;
  --radius: 18px; --shadow: 0 10px 30px rgba(2, 38, 110, .08);
}}

html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select {{
  font-family: 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif !important;
}}
.stApp {{
  background:
    radial-gradient(1200px 500px at 90% -10%, rgba(13,145,253,.10), transparent 60%),
    radial-gradient(900px 400px at -10% 10%, rgba(2,99,230,.07), transparent 60%),
    #F7FAFF;
}}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}
h1, h2, h3, h4 {{ color: var(--ink); letter-spacing: -.02em; }}

/* Sidebar */
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #FFFFFF 0%, #F3F7FF 100%);
  border-right: 1px solid var(--line);
}}
section[data-testid="stSidebar"][aria-expanded="true"] {{
  width: 320px !important; min-width: 320px !important; max-width: 320px !important;
}}
section[data-testid="stSidebar"] .block-container {{ padding-top: 1rem; }}

/* Inputs */
div[data-testid="stTextInput"] input, div[data-baseweb="select"] > div {{
  border-radius: 14px !important; border: 1.5px solid var(--line) !important;
  background: #FFFFFF !important; min-height: 48px; font-size: 15px;
  box-shadow: 0 2px 6px rgba(2,38,110,.04);
  transition: border-color .2s, box-shadow .2s;
}}
div[data-testid="stTextInput"] input:focus {{
  border-color: var(--sky) !important;
  box-shadow: 0 0 0 4px rgba(13,145,253,.15) !important;
}}
div[data-testid="stTextInput"] > div {{ border: none !important; background: transparent !important; }}
label p {{ font-weight: 600 !important; color: var(--ink) !important; }}

/* Buttons */
button[kind="primary"], button[data-testid="stBaseButton-primary"],
div[data-testid="stDownloadButton"] button {{
  background: linear-gradient(135deg, var(--blue) 0%, var(--sky) 100%) !important;
  color: #fff !important; border: none !important; border-radius: 14px !important;
  padding: .65rem 1.6rem !important; font-weight: 700 !important; letter-spacing: .01em;
  box-shadow: 0 8px 22px rgba(2,99,230,.30) !important;
  transition: transform .15s ease, box-shadow .15s ease, filter .15s ease !important;
}}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover,
div[data-testid="stDownloadButton"] button:hover {{
  transform: translateY(-2px); filter: brightness(1.05);
  box-shadow: 0 12px 28px rgba(2,99,230,.38) !important;
}}
button[kind="secondary"], button[data-testid="stBaseButton-secondary"] {{
  border-radius: 12px !important; border: 1.5px solid var(--line) !important;
  background: #fff !important; color: var(--ink) !important; font-weight: 600 !important;
  transition: border-color .15s, transform .15s !important;
}}
button[kind="secondary"]:hover, button[data-testid="stBaseButton-secondary"]:hover {{
  border-color: var(--sky) !important; color: var(--blue) !important;
}}

/* Expander, dataframe, alerts */
div[data-testid="stExpander"] details {{
  border-radius: var(--radius) !important; border: 1px solid var(--line) !important;
  background: rgba(255,255,255,.85); box-shadow: var(--shadow);
}}
div[data-testid="stExpander"] summary p {{ font-weight: 700; color: var(--ink); }}
div[data-testid="stDataFrame"] {{
  border-radius: var(--radius); overflow: hidden; border: 1px solid var(--line);
  box-shadow: var(--shadow); background: #fff;
}}
div[data-testid="stAlert"] {{ border-radius: 14px; }}
div[data-testid="stPills"] button {{ border-radius: 999px !important; }}

/* ---------- Components ---------- */
.ls-hero {{
  position: relative; overflow: hidden; border-radius: 26px; padding: 34px 38px;
  background: linear-gradient(125deg, var(--navy) 0%, #062D7A 45%, var(--blue) 100%);
  color: #fff; box-shadow: 0 20px 50px rgba(0,22,63,.28); margin-bottom: 22px;
}}
.ls-hero .orb {{ position: absolute; border-radius: 50%; filter: blur(8px); opacity: .55;
  animation: ls-float 9s ease-in-out infinite; }}
.ls-hero .orb.a {{ width: 260px; height: 260px; right: -60px; top: -90px;
  background: radial-gradient(circle, rgba(13,145,253,.9), transparent 70%); }}
.ls-hero .orb.b {{ width: 180px; height: 180px; right: 180px; bottom: -110px;
  background: radial-gradient(circle, rgba(120,190,255,.6), transparent 70%); animation-delay: -3s; }}
.ls-hero .row {{ position: relative; display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }}
.ls-hero .tile {{ width: 86px; height: 86px; border-radius: 22px; background: #fff;
  display: grid; place-items: center; box-shadow: 0 10px 25px rgba(0,0,0,.25); flex: none; }}
.ls-hero .tile img {{ width: 70px; }}
.ls-hero h1 {{ color: #fff; margin: 0; font-size: 2.3rem; font-weight: 800; line-height: 1.1; }}
.ls-hero h1 span {{ background: linear-gradient(90deg, #8FD0FF, #fff); -webkit-background-clip: text;
  background-clip: text; color: transparent; }}
.ls-hero .tag {{ display: inline-block; margin-top: 6px; font-size: .78rem; font-weight: 700;
  letter-spacing: .18em; text-transform: uppercase; color: #9FD2FF; }}
.ls-hero p {{ color: rgba(255,255,255,.85); margin: 12px 0 0; max-width: 760px; font-size: 1rem; }}
.ls-chips {{ position: relative; display: flex; gap: 10px; flex-wrap: wrap; margin-top: 20px; }}
.ls-chip {{ display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 999px;
  font-size: .82rem; font-weight: 600; background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.22); color: #fff; backdrop-filter: blur(6px); }}

.ls-section {{ font-weight: 800; font-size: 1.05rem; color: var(--ink); margin: 6px 0 8px; }}
.ls-understood {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 4px 0 12px; }}
.ls-understood .lbl {{ font-size: .8rem; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .08em; margin-right: 4px; }}
.ls-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 999px;
  background: #fff; border: 1.5px solid var(--line); font-size: .86rem; font-weight: 600; color: var(--ink); }}
.ls-pill.warn {{ border-color: #FFC58A; background: var(--amber); }}

.ls-metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin: 10px 0 18px; }}
@media (max-width: 900px) {{ .ls-metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.ls-metric {{ background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 18px 20px; box-shadow: var(--shadow); position: relative; overflow: hidden;
  animation: ls-rise .5s ease both; }}
.ls-metric::after {{ content: ""; position: absolute; inset: auto -30px -40px auto; width: 120px; height: 120px;
  border-radius: 50%; background: radial-gradient(circle, rgba(13,145,253,.14), transparent 70%); }}
.ls-metric .ico {{ width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center;
  font-size: 18px; background: var(--soft); margin-bottom: 10px; }}
.ls-metric .val {{ font-size: 2rem; font-weight: 800; color: var(--ink); line-height: 1; }}
.ls-metric .cap {{ font-size: .82rem; color: var(--muted); font-weight: 600; margin-top: 6px; }}

.ls-results-head {{ display: flex; justify-content: space-between; align-items: flex-end;
  gap: 12px; flex-wrap: wrap; margin-top: 8px; }}
.ls-results-head h2 {{ margin: 0; font-size: 1.6rem; font-weight: 800; }}
.ls-results-head .sub {{ color: var(--muted); font-size: .9rem; margin-top: 4px; }}

.ls-tops {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 6px 0 18px; }}
@media (max-width: 900px) {{ .ls-tops {{ grid-template-columns: 1fr; }} }}
.ls-top {{ background: #fff; border: 1px solid var(--line); border-radius: var(--radius); padding: 16px 18px;
  box-shadow: var(--shadow); animation: ls-rise .5s ease both; }}
.ls-top .name {{ font-weight: 800; color: var(--ink); font-size: 1rem; }}
.ls-top .meta {{ color: var(--muted); font-size: .82rem; margin: 4px 0 10px; }}
.ls-top .score {{ float: right; font-weight: 800; color: #fff; font-size: .8rem; padding: 4px 10px;
  border-radius: 999px; background: linear-gradient(135deg, #FF6B6B, #FF9F43); }}
.ls-gap {{ display: inline-block; font-size: .72rem; font-weight: 700; padding: 3px 9px; border-radius: 999px;
  margin: 0 5px 5px 0; background: var(--red); color: #B4233B; }}
.ls-gap.soft {{ background: var(--amber); color: #A15A00; }}

.ls-legend {{ display: flex; gap: 16px; flex-wrap: wrap; color: var(--muted); font-size: .82rem; margin: 2px 0 8px; }}
.ls-legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 4px; margin-right: 6px;
  vertical-align: -1px; }}

.ls-side-logo {{ text-align: center; margin: -8px 0 6px; }}
.ls-side-logo img {{ width: 150px; }}
.ls-steps {{ list-style: none; padding: 0; margin: 6px 0 0; }}
.ls-steps li {{ display: flex; gap: 10px; align-items: flex-start; margin: 0 0 12px; font-size: .86rem; color: var(--muted); }}
.ls-steps .n {{ flex: none; width: 26px; height: 26px; border-radius: 9px; display: grid; place-items: center;
  font-weight: 800; font-size: .78rem; color: #fff; background: linear-gradient(135deg, var(--blue), var(--sky)); }}
.ls-steps b {{ color: var(--ink); }}
.ls-side-note {{ background: var(--soft); border: 1px solid var(--line); border-radius: 14px; padding: 10px 12px;
  font-size: .8rem; color: var(--muted); }}

.ls-login {{ max-width: 440px; margin: 7vh auto 18px; text-align: center; }}
.ls-login img {{ width: 200px; }}
.ls-login h2 {{ margin: 10px 0 4px; font-weight: 800; }}
.ls-login p {{ color: var(--muted); }}

.ls-footer {{ text-align: center; color: var(--muted); font-size: .8rem; margin-top: 30px; }}
.ls-footer img {{ width: 26px; vertical-align: middle; margin-right: 6px; }}
.ls-footer a {{ color: var(--blue); }}

/* ---------- Search animation ---------- */
.ls-loader {{ background: linear-gradient(135deg, var(--navy) 0%, #07307F 60%, #0A4FC4 100%);
  border-radius: 26px; padding: 28px 24px 22px; color: #fff; position: relative; overflow: hidden;
  box-shadow: 0 20px 50px rgba(0,22,63,.30); min-height: 430px; }}
.ls-loader .grid {{ position: absolute; inset: 0; opacity: .12;
  background-image: linear-gradient(rgba(255,255,255,.5) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.5) 1px, transparent 1px);
  background-size: 34px 34px; animation: ls-pan 18s linear infinite; }}
.ls-radar {{ position: relative; width: 250px; height: 250px; margin: 6px auto 12px; }}
.ls-radar .ring {{ position: absolute; inset: 0; border-radius: 50%; border: 1.5px solid rgba(143,208,255,.35); }}
.ls-radar .ring.r2 {{ inset: 30px; }} .ls-radar .ring.r3 {{ inset: 60px; }}
.ls-radar .sweep {{ position: absolute; inset: 0; border-radius: 50%;
  background: conic-gradient(from 0deg, rgba(13,145,253,0) 0deg, rgba(13,145,253,0) 280deg,
             rgba(13,145,253,.55) 350deg, rgba(160,220,255,.9) 360deg);
  animation: ls-spin 2.6s linear infinite; }}
.ls-radar .pulse {{ position: absolute; left: 50%; top: 50%; width: 90px; height: 90px; margin: -45px;
  border-radius: 50%; border: 2px solid rgba(143,208,255,.8); animation: ls-pulse 2.2s ease-out infinite; }}
.ls-radar .pulse.p2 {{ animation-delay: 1.1s; }}
.ls-radar .core {{ position: absolute; left: 50%; top: 50%; width: 92px; height: 92px; margin: -46px;
  border-radius: 28px; background: #fff; display: grid; place-items: center;
  box-shadow: 0 0 0 6px rgba(255,255,255,.12), 0 12px 30px rgba(0,0,0,.35);
  animation: ls-bob 2.4s ease-in-out infinite; }}
.ls-radar .core img {{ width: 74px; }}
.ls-radar .blip {{ position: absolute; width: 14px; height: 14px; margin: -7px; border-radius: 50% 50% 50% 0;
  transform: rotate(-45deg) scale(0); background: #FF5C7A; box-shadow: 0 0 12px rgba(255,92,122,.9);
  animation: ls-blip 2.6s ease-out infinite; }}
.ls-radar .blip.g {{ background: #3DDC97; box-shadow: 0 0 12px rgba(61,220,151,.9); }}
.ls-radar .blip.y {{ background: #FFC93C; box-shadow: 0 0 12px rgba(255,201,60,.9); }}
.ls-orbit {{ position: absolute; inset: -18px; animation: ls-spin 14s linear infinite; }}
.ls-orbit span {{ position: absolute; width: 34px; height: 34px; margin: -17px; border-radius: 12px;
  background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); display: grid; place-items: center;
  font-size: 17px; animation: ls-spin 14s linear infinite reverse; }}
.ls-tips {{ position: relative; height: 44px; text-align: center; margin-top: 6px; }}
.ls-tips div {{ position: absolute; inset: 0; opacity: 0; font-size: .88rem; color: rgba(255,255,255,.85);
  animation: ls-tip 30s infinite; padding: 0 10px; }}
.ls-tips b {{ color: #9FD2FF; }}

.ls-live {{ background: #fff; border-radius: 26px; padding: 24px 26px; border: 1px solid var(--line);
  box-shadow: var(--shadow); min-height: 430px; }}
.ls-live h3 {{ margin: 0 0 4px; font-size: 1.25rem; font-weight: 800; }}
.ls-live .sub {{ color: var(--muted); font-size: .86rem; margin-bottom: 14px; }}
.ls-bar {{ height: 12px; border-radius: 999px; background: #E8EEF9; overflow: hidden; margin: 6px 0 4px; }}
.ls-bar > div {{ height: 100%; border-radius: 999px; transition: width .6s ease;
  background: linear-gradient(90deg, var(--blue), var(--sky), var(--blue)); background-size: 200% 100%;
  animation: ls-shimmer 1.6s linear infinite; }}
.ls-barinfo {{ display: flex; justify-content: space-between; font-size: .8rem; color: var(--muted); font-weight: 600; }}
.ls-counters {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 16px 0; }}
.ls-counter {{ background: var(--soft); border: 1px solid var(--line); border-radius: 14px; padding: 10px 12px; }}
.ls-counter .v {{ font-size: 1.45rem; font-weight: 800; color: var(--ink); }}
.ls-counter .l {{ font-size: .74rem; color: var(--muted); font-weight: 600; }}
.ls-stepper {{ list-style: none; padding: 0; margin: 0; }}
.ls-stepper li {{ display: flex; align-items: center; gap: 12px; padding: 7px 0; font-size: .9rem;
  color: #9AA7C2; font-weight: 600; }}
.ls-stepper .dot {{ flex: none; width: 30px; height: 30px; border-radius: 10px; display: grid; place-items: center;
  font-size: 15px; background: #EEF2FA; transition: all .3s; }}
.ls-stepper li.done {{ color: var(--ink); }}
.ls-stepper li.done .dot {{ background: var(--green); }}
.ls-stepper li.active {{ color: var(--blue); }}
.ls-stepper li.active .dot {{ background: linear-gradient(135deg, var(--blue), var(--sky)); color: #fff;
  box-shadow: 0 0 0 0 rgba(13,145,253,.6); animation: ls-ring 1.4s ease-out infinite; }}
.ls-now {{ margin-top: 12px; padding: 10px 12px; border-radius: 12px; background: var(--soft);
  font-size: .82rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.ls-now b {{ color: var(--ink); }}
.ls-note {{ margin-top: 8px; padding: 8px 12px; border-radius: 12px; background: var(--amber);
  color: #8A4B00; font-size: .8rem; }}
.ls-done {{ text-align: center; padding: 40px 20px; }}
.ls-done .check {{ width: 84px; height: 84px; border-radius: 50%; margin: 0 auto 14px; display: grid; place-items: center;
  font-size: 40px; color: #fff; background: linear-gradient(135deg, #22C55E, #3DDC97);
  animation: ls-pop .5s cubic-bezier(.2,1.6,.4,1) both; box-shadow: 0 12px 30px rgba(34,197,94,.35); }}

@keyframes ls-spin {{ to {{ transform: rotate(360deg); }} }}
@keyframes ls-pulse {{ 0% {{ transform: scale(.6); opacity: .9; }} 100% {{ transform: scale(2.6); opacity: 0; }} }}
@keyframes ls-bob {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-6px); }} }}
@keyframes ls-blip {{ 0%,55% {{ transform: rotate(-45deg) scale(0); opacity: 0; }}
  62% {{ transform: rotate(-45deg) scale(1.3); opacity: 1; }} 85% {{ transform: rotate(-45deg) scale(1); opacity: 1; }}
  100% {{ transform: rotate(-45deg) scale(0); opacity: 0; }} }}
@keyframes ls-tip {{ 0% {{ opacity: 0; transform: translateY(8px); }} 2%,18% {{ opacity: 1; transform: none; }}
  20%,100% {{ opacity: 0; transform: translateY(-8px); }} }}
@keyframes ls-pan {{ to {{ background-position: 340px 340px; }} }}
@keyframes ls-shimmer {{ to {{ background-position: -200% 0; }} }}
@keyframes ls-ring {{ 0% {{ box-shadow: 0 0 0 0 rgba(13,145,253,.55); }} 100% {{ box-shadow: 0 0 0 12px rgba(13,145,253,0); }} }}
@keyframes ls-float {{ 0%,100% {{ transform: translate(0,0); }} 50% {{ transform: translate(-20px, 16px); }} }}
@keyframes ls-rise {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes ls-pop {{ from {{ transform: scale(0); }} to {{ transform: scale(1); }} }}
</style>
"""


# --- Components --------------------------------------------------------------

def hero(hosted: bool) -> str:
    chips = [("🌍", "OpenStreetMap"), ("🗺️", "Google Maps" if not hosted else "Cloud demo"),
             ("🔗", "Social & email finder"), ("📊", "Excel export"), ("🔒", "Free · No API keys")]
    chip_html = "".join(f'<span class="ls-chip">{i} {esc(t)}</span>' for i, t in chips)
    return f"""
<div class="ls-hero">
  <div class="orb a"></div><div class="orb b"></div>
  <div class="row">
    <div class="tile"><img src="{data_uri(ICON_PATH)}" alt="LeadScout AI"></div>
    <div>
      <h1>LeadScout <span>AI</span></h1>
      <div class="tag">Lead Generation Tool</div>
      <p>Find local businesses that need your services. Describe what you want in plain words -
         LeadScout collects businesses, checks their websites and social media, and ranks them by
         how much they could use your help.</p>
    </div>
  </div>
  <div class="ls-chips">{chip_html}</div>
</div>"""


def understood(category: str, location: str | None, filters: str) -> str:
    loc = (f'<span class="ls-pill">📍 {esc(location)}</span>' if location
           else '<span class="ls-pill warn">📍 add a location</span>')
    return (f'<div class="ls-understood"><span class="lbl">Understood as</span>'
            f'<span class="ls-pill">🏷️ {esc(category)}</span>{loc}'
            f'<span class="ls-pill">🎯 {esc(filters)}</span></div>')


def sidebar_intro(hosted: bool) -> str:
    steps = [("Describe", "the leads you want in plain language."),
             ("Collect", "businesses from OpenStreetMap and Google Maps."),
             ("Merge", "both sources and remove duplicates."),
             ("Enrich", "with social media links and emails from websites."),
             ("Score", "leads - more gaps means more to sell."),
             ("Download", "a polished Excel file.")]
    items = "".join(f'<li><span class="n">{i}</span><span><b>{esc(t)}</b> {esc(d)}</span></li>'
                    for i, (t, d) in enumerate(steps, 1))
    note = ("Free and legal data sources. No paid API keys." if hosted
            else "Runs on your computer. Free and legal data sources, no paid API keys.")
    return (f'<div class="ls-side-logo"><img src="{data_uri(LOGO_PATH)}" alt="LeadScout AI"></div>'
            f'<div class="ls-section">How it works</div><ul class="ls-steps">{items}</ul>'
            f'<div class="ls-side-note">🔒 {esc(note)}</div>')


def login_header(message: str) -> str:
    return (f'<div class="ls-login"><img src="{data_uri(LOGO_PATH)}" alt="LeadScout AI">'
            f'<h2>Welcome back</h2><p>{esc(message)}</p></div>')


def metrics(cards: list[tuple[str, str, str]]) -> str:
    items = "".join(
        f'<div class="ls-metric" style="animation-delay:{i * 80}ms"><div class="ico">{icon}</div>'
        f'<div class="val">{esc(value)}</div><div class="cap">{esc(caption)}</div></div>'
        for i, (icon, value, caption) in enumerate(cards))
    return f'<div class="ls-metrics">{items}</div>'


def results_header(title: str, subtitle: str) -> str:
    return (f'<div class="ls-results-head"><div><h2>{esc(title)}</h2>'
            f'<div class="sub">{esc(subtitle)}</div></div></div>')


GAP_LABELS = {"website": "no website", "website (broken)": "broken website",
              "social_media": "no social media", "phone": "no phone", "email": "no email",
              "address": "no address"}


def top_opportunities(rows: list[dict]) -> str:
    """Spotlight cards for the best leads: highest score among those you can call first."""
    ranked = sorted(rows, key=lambda r: (bool(r.get("Contact Number")), r.get("Lead Score") or 0),
                    reverse=True)
    cards = []
    for i, row in enumerate(ranked[:3]):
        gaps = [g.strip() for g in str(row.get("Missing Fields") or "").split(",") if g.strip()]
        gap_html = "".join(
            f'<span class="ls-gap{"" if g.startswith(("website", "phone")) else " soft"}">'
            f'{esc(GAP_LABELS.get(g, "no " + g.replace("_", " ")))}</span>' for g in gaps)
        meta = " · ".join(esc(v) for v in (row.get("Category"), row.get("Contact Number")
                                           or "no phone listed") if v)
        cards.append(
            f'<div class="ls-top" style="animation-delay:{i * 90}ms">'
            f'<span class="score">{esc(row.get("Lead Score"))}</span>'
            f'<div class="name">{esc(row.get("Business Name"))}</div>'
            f'<div class="meta">{meta}</div>{gap_html}</div>')
    return f'<div class="ls-tops">{"".join(cards)}</div>' if cards else ""


def legend() -> str:
    return ('<div class="ls-legend"><span><i style="background:#FFC7CE"></i>Key gap (no phone / website)'
            '</span><span><i style="background:#FCE4D6"></i>Other missing info</span>'
            '<span>Click a column header to sort</span></div>')


def footer(hosted: bool) -> str:
    extra = (" · Online demo: download your files, they are not kept on the server."
             if hosted else "")
    return (f'<div class="ls-footer"><img src="{data_uri(ICON_PATH)}" alt="">'
            f'LeadScout AI uses only free and legal data sources (OpenStreetMap + limited Google Maps '
            f'browsing). No paid API keys required.{esc(extra)}<br>Map data © '
            f'<a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap '
            f'contributors</a> (ODbL).</div>')


# --- Search animation --------------------------------------------------------

TIPS = [
    "<b>Good to know:</b> every lead gets a phone number - we look missing ones up for you.",
    "<b>Did you know?</b> Businesses without a website are often the easiest to sell a site to.",
    "<b>Tip:</b> the Excel file has an About sheet with sources and a colour legend.",
    "<b>Did you know?</b> Every website is checked for Facebook, Instagram, LinkedIn and email.",
    "<b>Tip:</b> sort by Lead Score - higher score means more services you can offer.",
]

STEPS = [("collect", "🧭", "Understanding the area"), ("osm", "🌍", "Scanning OpenStreetMap"),
         ("maps", "🗺️", "Browsing Google Maps"), ("merge", "🧩", "Merging duplicates"),
         ("phones", "📞", "Finding phone numbers"),
         ("enrich", "🔗", "Checking websites & socials"), ("score", "🎯", "Scoring leads"),
         ("export", "📊", "Building your Excel file")]


def radar() -> str:
    """Static animated panel: rendered once so the CSS animation never restarts."""
    blips = [(22, 30, ""), (70, 24, "g"), (78, 64, "y"), (30, 72, ""), (55, 82, "g"), (15, 55, "y"),
             (62, 40, ""), (42, 16, "g")]
    blip_html = "".join(
        f'<span class="blip {c}" style="left:{x}%;top:{y}%;animation-delay:{i * 0.33:.2f}s"></span>'
        for i, (x, y, c) in enumerate(blips))
    icons = ["🍽️", "💇", "☕", "🏋️", "🏨", "🦷"]
    orbit = "".join(
        f'<span style="left:{50 + 50 * math.cos(i * 6.283 / len(icons)):.1f}%;'
        f'top:{50 + 50 * math.sin(i * 6.283 / len(icons)):.1f}%">{e}</span>'
        for i, e in enumerate(icons))
    tips = "".join(f'<div style="animation-delay:{i * 6}s">{t}</div>' for i, t in enumerate(TIPS))
    return f"""
<div class="ls-loader"><div class="grid"></div>
  <div class="ls-radar">
    <div class="ls-orbit">{orbit}</div>
    <div class="ring"></div><div class="ring r2"></div><div class="ring r3"></div>
    <div class="sweep"></div>{blip_html}
    <div class="pulse"></div><div class="pulse p2"></div>
    <div class="core"><img src="{data_uri(ICON_PATH)}" alt=""></div>
  </div>
  <div class="ls-tips">{tips}</div>
</div>"""


def live_panel(stage: str, fraction: float, elapsed: int, found: int, phones: int, websites: str,
               matched: str, now: str, notes: list[str], google_maps: bool) -> str:
    """The changing half of the search screen (re-rendered on every progress event)."""
    order = [s for s in STEPS if google_maps or s[0] not in ("maps", "phones")]
    keys = [s[0] for s in order]
    active = keys.index(stage) if stage in keys else (len(keys) if stage == "done" else 0)
    items = []
    for i, (_, icon, label) in enumerate(order):
        state = "done" if i < active else "active" if i == active else ""
        items.append(f'<li class="{state}"><span class="dot">{"✓" if state == "done" else icon}</span>'
                     f'{esc(label)}</li>')
    pct = int(max(0.0, min(fraction, 1.0)) * 100)
    mins, secs = divmod(elapsed, 60)
    note_html = "".join(f'<div class="ls-note">⚠️ {esc(n)}</div>' for n in notes[-2:])
    return f"""
<div class="ls-live">
  <h3>Hunting for leads…</h3>
  <div class="sub">Keep this tab open - the radar keeps spinning while we work.</div>
  <div class="ls-bar"><div style="width:{max(pct, 3)}%"></div></div>
  <div class="ls-barinfo"><span>{pct}% complete</span><span>⏱ {mins}:{secs:02d}</span></div>
  <div class="ls-counters">
    <div class="ls-counter"><div class="v">{esc(found)}</div><div class="l">Businesses found</div></div>
    <div class="ls-counter"><div class="v">{esc(phones)}</div><div class="l">Phone numbers</div></div>
    <div class="ls-counter"><div class="v">{esc(websites)}</div><div class="l">Websites checked</div></div>
    <div class="ls-counter"><div class="v">{esc(matched)}</div><div class="l">Matching leads</div></div>
  </div>
  <ul class="ls-stepper">{"".join(items)}</ul>
  <div class="ls-now">⚡ <b>Now:</b> {esc(now)}</div>{note_html}
</div>"""


def done_panel(matched: int, total: int, seconds: float) -> str:
    title = f"{matched} leads ready!" if matched else "Search complete"
    detail = (f"Out of {total} businesses found" if matched
              else f"{total} businesses found, none matched your filters")
    return (f'<div class="ls-live ls-done"><div class="check">✓</div>'
            f'<h3>{esc(title)}</h3><div class="sub">{esc(detail)} in '
            f'{int(seconds // 60)}m {int(seconds % 60)}s. Loading your results…</div></div>')
