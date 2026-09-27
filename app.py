"""LeadScout AI - web interface.

Run with:  streamlit run app.py   (or double-click run_app.bat)

If the LEADSCOUT_PASSWORD environment variable is set (e.g. as a secret on a
hosted copy), visitors must enter it before using the app. Locally it is
normally unset, so no login is needed.

Styling and HTML components live in modules/ui.py.
"""

import hmac
import ipaddress
import os
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

import config
from main import setup_logging
from modules import ui
from modules.excel_export import COLUMN_HEADERS, table_rows
from modules.nlp_parser import parse_filter_text, parse_user_request
from modules.pipeline import run_pipeline

try:
    _PAGE_ICON = Image.open(ui.ASSETS / "icon.png")
except OSError:
    _PAGE_ICON = "🔎"
st.set_page_config(page_title="LeadScout AI", page_icon=_PAGE_ICON, layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(ui.CSS, unsafe_allow_html=True)

FILTER_LABELS = {
    "no_website": "Needs website",
    "no_social_media": "Needs social media",
    "no_phone": "Needs phone number",
    "no_email": "No email",
    "has_phone": "Has phone number",
    "broken_website": "Website is broken",
    "low_rating": "Low rating",
}
CATEGORY_CHOICES = ["From my request", "All Categories"] + [
    c.replace("_", " ").title() for c in config.DEFAULT_CATEGORIES
]
EXAMPLES = [
    "restaurants in Lahore that need a website",
    "salons in Karachi without social media",
    "gyms in Islamabad that need a website and have a phone number",
    "cafes in Islamabad without social media",
]
LINK_COLUMNS = ["Website", "Facebook", "Instagram", "LinkedIn", "Listing Link"]
RED_WHEN_EMPTY = ["Contact Number", "Website"]
ORANGE_WHEN_EMPTY = ["Email", "Facebook", "Instagram", "LinkedIn", "Address/Location"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@st.cache_resource
def _logging_ready() -> Path | None:
    """Set up the daily log file once per app process."""
    return setup_logging()


LOG_PATH = _logging_ready()
st.session_state.setdefault("history", [])
st.session_state.setdefault("current", None)


def _setting(name: str, default: str = "") -> str:
    """Read a setting from the environment, or from Streamlit secrets
    (.streamlit/secrets.toml locally; the "Secrets" box on Streamlit Community Cloud)."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        return str(st.secrets.get(name, default))
    except Exception:  # noqa: BLE001 - no secrets file: that's fine
        return default


APP_PASSWORD = _setting("LEADSCOUT_PASSWORD")
GOOGLE_MAPS_DEFAULT = _setting("LEADSCOUT_GOOGLE_MAPS", "1" if config.GOOGLE_MAPS_ENABLED else "0") != "0"
# Hosted copies (Hugging Face sets SPACE_ID; Streamlit Cloud serves from /mount/src)
# show a note that files are temporary and Google Maps is often blocked.
HOSTED = bool(os.environ.get("SPACE_ID")) or str(Path(__file__).resolve()).startswith("/mount/src")


# --- Password gate -----------------------------------------------------------

def _is_local_visitor() -> bool:
    """True when the page is opened on the computer running the app."""
    ip = st.context.ip_address  # None when opened via localhost
    if ip is None:
        return True
    try:
        return ipaddress.ip_address(str(ip)).is_loopback
    except ValueError:
        return False


def _require_password() -> None:
    """Show a login form and stop the page until the right password is entered.

    Without a password the app is meant for this computer only, so visitors
    from other devices are turned away.
    """
    password = APP_PASSWORD
    if not password:
        if not _is_local_visitor():
            st.markdown(ui.login_header("This copy of LeadScout AI is private."),
                        unsafe_allow_html=True)
            st.error("This copy of LeadScout AI has no password set, so it only works on the "
                     "computer it runs on. To allow access from other devices, set the "
                     "LEADSCOUT_PASSWORD secret.")
            st.stop()
        return
    if st.session_state.get("authenticated"):
        return

    st.markdown(ui.login_header("This copy of LeadScout AI is private. Please enter the password."),
                unsafe_allow_html=True)
    _, middle, _ = st.columns([1, 1.1, 1])
    with middle:
        failures = st.session_state.get("login_failures", 0)
        locked_until = st.session_state.get("locked_until", 0.0)
        if time.time() < locked_until:
            st.error(f"Too many wrong attempts. Try again in {int(locked_until - time.time())} seconds.")
            st.stop()

        with st.form("login"):
            attempt = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
        if submitted:
            if hmac.compare_digest(attempt.encode("utf-8"), password.encode("utf-8")):
                st.session_state.authenticated = True
                st.session_state.login_failures = 0
                st.rerun()
            time.sleep(1.5)  # slow down guessing
            failures += 1
            st.session_state.login_failures = failures
            if failures >= 5:
                st.session_state.locked_until = time.time() + 60
                st.session_state.login_failures = 0
            st.error("Wrong password.")
    st.stop()


_require_password()


# --- Helpers -----------------------------------------------------------------

def describe_filters(filters: list) -> str:
    parts = []
    for rule in filters:
        if isinstance(rule, tuple):
            parts.append(f"{FILTER_LABELS.get(rule[0], rule[0])} (< {rule[1]})")
        else:
            parts.append(FILTER_LABELS.get(rule, rule))
    return ", ".join(parts) or "no filter (all businesses)"


def describe_category(parsed: dict) -> str:
    if parsed["category"] == "all":
        return f"All categories ({len(parsed['categories'])} types)"
    return ", ".join(c.replace("_", " ") for c in parsed["categories"])


def build_request(text: str, category_choice: str, location: str, manual_filters: list) -> dict:
    """Combine the natural-language request with any Advanced Options overrides."""
    parsed = parse_user_request(text) if text.strip() else {
        "category": "all", "categories": list(config.DEFAULT_CATEGORIES),
        "location": None, "filters": [],
    }
    if category_choice == "All Categories":
        parsed["category"], parsed["categories"] = "all", list(config.DEFAULT_CATEGORIES)
    elif category_choice != "From my request":
        key = config.DEFAULT_CATEGORIES[CATEGORY_CHOICES.index(category_choice) - 2]
        parsed["category"], parsed["categories"] = key, [key]
    if location.strip():
        parsed["location"] = location.strip()
    if manual_filters:
        parsed["filters"] = manual_filters
    return parsed


def style_missing(df: pd.DataFrame):
    """Colour empty cells like the Excel file: red for key gaps, orange for others."""
    def colour(value, fill):
        empty = value is None or value == "" or (isinstance(value, float) and pd.isna(value))
        return f"background-color: {fill}" if empty else ""

    def website_gap(row):
        # A social page used as the website counts as missing (red); a broken site is orange.
        missing = [m.strip() for m in str(row.get("Missing Fields") or "").split(",")]
        styles = [""] * len(row)
        if "Website" in row.index and row["Website"]:
            fill = "#FFC7CE" if "website" in missing else "#FCE4D6" if "website (broken)" in missing else ""
            if fill:
                styles[list(row.index).index("Website")] = f"background-color: {fill}"
        return styles

    styler = df.style
    red = [c for c in RED_WHEN_EMPTY if c in df.columns]
    orange = [c for c in ORANGE_WHEN_EMPTY if c in df.columns]
    if red:
        styler = styler.map(lambda v: colour(v, "#FFC7CE"), subset=red)
    if orange:
        styler = styler.map(lambda v: colour(v, "#FCE4D6"), subset=orange)
    styler = styler.apply(website_gap, axis=1)
    return styler.format({"Rating": lambda v: "" if pd.isna(v) else f"{v:.1f}"})


def save_to_history(text: str, parsed: dict, result) -> dict:
    output = result.output_path
    entry = {
        "id": len(st.session_state.history) + 1,
        "request": text.strip() or f"{describe_category(parsed)} in {parsed['location']}",
        "time": datetime.now().strftime("%H:%M"),
        "parsed": parsed,
        # Nothing matched: show every business found (the Excel file has them all too).
        "rows": table_rows(result.matched or result.leads),
        "total": len(result.leads),
        "matched": len(result.matched),
        "filters_applied": result.filters_applied,
        "average_score": result.average_score,
        "errors": list(result.errors),
        "seconds": result.seconds,
        "file_name": output.name if output else None,
        "file_bytes": output.read_bytes() if output and output.exists() else None,
        "file_is_excel": bool(output and output.suffix == ".xlsx"),
        "file_path": str(output) if output else None,
    }
    st.session_state.history.append(entry)
    st.session_state.current = entry["id"]
    return entry


def _use_example() -> None:
    """Clicking an example chip fills the request box."""
    choice = st.session_state.get("example_pick")
    if choice:
        st.session_state.request_text = choice
    st.session_state.example_pick = None


# --- Sidebar -----------------------------------------------------------------

st.logo(str(ui.ASSETS / "icon.png"), size="large")
with st.sidebar:
    st.markdown(ui.sidebar_intro(HOSTED), unsafe_allow_html=True)
    st.markdown('<div class="ls-section" style="margin-top:18px">🕘 Search history</div>',
                unsafe_allow_html=True)
    if not st.session_state.history:
        st.caption("Your searches in this session will appear here.")
    for entry in reversed(st.session_state.history):
        label = f"{entry['request'][:38]}  \n{entry['matched']} leads · {entry['time']}"
        if st.button(label, key=f"history_{entry['id']}", width="stretch",
                     type="primary" if entry["id"] == st.session_state.current else "secondary"):
            st.session_state.current = entry["id"]
    if st.session_state.history and st.button("Clear history", width="stretch"):
        st.session_state.history, st.session_state.current = [], None
        st.rerun()
    if APP_PASSWORD and st.session_state.get("authenticated"):
        st.divider()
        if st.button("Log out", width="stretch"):
            st.session_state.clear()
            st.rerun()


# --- Search form -------------------------------------------------------------

st.markdown(ui.hero(HOSTED), unsafe_allow_html=True)

text = st.text_input(
    "🔍 What leads are you looking for?",
    placeholder="e.g. restaurants in Lahore that need a website",
    key="request_text",
)
st.pills("Try an example", EXAMPLES, key="example_pick", on_change=_use_example,
         label_visibility="collapsed")

with st.expander("⚙️ Advanced Options"):
    col1, col2 = st.columns(2)
    category_choice = col1.selectbox("Category", CATEGORY_CHOICES)
    location_override = col2.text_input("Location", placeholder="From my request, e.g. Karachi")

    filter_text = st.text_input(
        "What should the leads be missing?",
        placeholder="e.g. no website, no social media, rating below 4",
        help="Separate items with commas or 'and'. Understood: website, social media, phone "
             "number, email, broken website, low rating / rating below 4, has a phone number. "
             "Anything typed here replaces the filters in your request above.")
    manual_filters, unknown_filters = parse_filter_text(filter_text)
    if unknown_filters:
        st.warning("Not understood, so ignored: " + ", ".join(f"\"{u}\"" for u in unknown_filters)
                   + ". Try words like website, social media, phone number, email, rating below 4.")
    elif manual_filters:
        st.caption(f"**Filters:** {describe_filters(manual_filters)}")

    max_results = st.slider("Max results per source", 10, 200, 50, 10)
    st.caption(
        f"OpenStreetMap returns up to {max_results} businesses per category. Google Maps is "
        f"capped at {config.MAPS_MAX_RESULTS_CAP} per category "
        f"({config.ALL_CATEGORIES_MAPS_MAX} when searching all categories) to keep browsing light."
    )

request = build_request(text, category_choice, location_override, manual_filters)
if text.strip() or location_override.strip() or filter_text.strip():
    st.markdown(ui.understood(describe_category(request), request["location"],
                              describe_filters(request["filters"])), unsafe_allow_html=True)

find = st.button("🚀  Find Leads", type="primary")


# --- Run the pipeline --------------------------------------------------------

_COUNT_RE = re.compile(r"^(\d+) found on ")
_UNIQUE_RE = re.compile(r"^(\d+) unique businesses")
_MATCH_RE = re.compile(r"^(\d+) of \d+ match")
_ITEM_RE = re.compile(r"^\[(\d+)/(\d+)\]")

if find:
    if not request["location"]:
        st.error('Please include a location, e.g. "salons in **Karachi**", or set one in '
                 "Advanced Options.")
    else:
        many = len(request["categories"]) > 1
        maps_cap = config.ALL_CATEGORIES_MAPS_MAX if many else config.MAPS_MAX_RESULTS_CAP
        started = time.monotonic()

        left, right = st.columns([1, 1.25], gap="medium")
        left.markdown(ui.radar(), unsafe_allow_html=True)  # rendered once: animation never restarts
        live = right.empty()
        progress = {"stage": "collect", "fraction": 0.0, "unique": 0, "pending": 0,
                    "websites": "–", "matched": "–", "now": "Starting up…", "notes": [],
                    "span": (0.0, 0.0)}

        def render() -> None:
            live.markdown(ui.live_panel(
                progress["stage"], progress["fraction"], int(time.monotonic() - started),
                progress["unique"] + progress["pending"], progress["websites"],
                progress["matched"], progress["now"], progress["notes"], GOOGLE_MAPS_DEFAULT),
                unsafe_allow_html=True)

        def on_progress(stage: str, message: str, fraction: float | None) -> None:
            if stage == "detail":
                progress["now"] = message
                if m := _COUNT_RE.match(message):
                    progress["pending"] += int(m.group(1))
                elif m := _UNIQUE_RE.match(message):
                    progress["unique"] += int(m.group(1))
                    progress["pending"] = 0
                elif m := _MATCH_RE.match(message):
                    progress["matched"] = m.group(1)
                elif m := _ITEM_RE.match(message):
                    done_items, total_items = int(m.group(1)), int(m.group(2))
                    if progress["stage"] == "enrich":
                        progress["websites"] = f"{done_items}/{total_items}"
                    # Move the bar within the current long step (Google Maps listings,
                    # website checks) instead of leaving it still for minutes.
                    start, end = progress["span"]
                    if total_items:
                        progress["fraction"] = start + (end - start) * done_items / total_items
            elif stage == "warning":
                progress["notes"].append(message)
            elif stage != "done":
                progress["stage"], progress["now"] = stage, message
            if fraction is not None:
                progress["fraction"] = fraction
                # Range the bar may fill during this step (see modules.pipeline fractions).
                share = 0.70 / len(request["categories"])
                progress["span"] = {"maps": (fraction, fraction + share * 0.8),
                                    "enrich": (fraction, 0.90)}.get(stage, (fraction, fraction))
            render()

        render()
        try:
            result = run_pipeline(request, osm_max=max_results,
                                  maps_max=min(max_results, maps_cap),
                                  use_google_maps=GOOGLE_MAPS_DEFAULT, on_progress=on_progress)
        except Exception as exc:  # noqa: BLE001 - never show a raw crash to the user
            import logging
            logging.getLogger("leadscout.app").exception("Pipeline crashed")
            live.empty()
            st.error(f"The search stopped unexpectedly: {exc}. Details are in the log file"
                     f"{f' ({LOG_PATH})' if LOG_PATH else ''}.")
        else:
            if result.leads:
                live.markdown(ui.done_panel(len(result.matched), len(result.leads), result.seconds),
                              unsafe_allow_html=True)
                save_to_history(text, request, result)
                st.session_state.celebrate = len(result.matched)
                time.sleep(1.2)  # let the success animation play
                st.rerun()  # redraw so the sidebar history includes this search
            else:
                live.empty()
                st.warning("No businesses were found. Try a different area or business type.")
                for error in result.errors:
                    st.error(error)


# --- Results -----------------------------------------------------------------

if (celebrate := st.session_state.pop("celebrate", None)) is not None:
    if celebrate:
        st.toast(f"{celebrate} leads ready - scroll down to see them!", icon="🎉")
    else:
        st.toast("Search finished - no business matched your filters.", icon="🔎")

entry = next((e for e in st.session_state.history if e["id"] == st.session_state.current), None)
if entry:
    st.markdown(ui.results_header(
        f"Results: {entry['request']}",
        f"{describe_category(entry['parsed'])} · {entry['parsed']['location']} · "
        f"{describe_filters(entry['parsed']['filters'])}"), unsafe_allow_html=True)

    secs = int(entry["seconds"] or 0)
    st.markdown(ui.metrics([
        ("🏢", entry["total"], "Total leads found"),
        ("🎯", entry["matched"] if entry["filters_applied"] else "n/a", "Leads matching filters"),
        ("🔥", f"{entry['average_score']:.0f}" if entry["average_score"] is not None else "–",
         "Average lead score"),
        ("⏱️", f"{secs // 60}m {secs % 60:02d}s", "Search time"),
    ]), unsafe_allow_html=True)

    if entry["errors"]:
        st.warning(
            "Some steps had problems, so these results may be incomplete:\n\n"
            + "\n".join(f"- {e}" for e in entry["errors"])
            + (f"\n\nDetails: `{LOG_PATH}`" if LOG_PATH else "")
        )
    if not entry["filters_applied"]:
        st.warning("The filters could not be applied, so all businesses are shown.")
    if entry["matched"] == 0:
        st.info("No business matched your filters, so all businesses found are shown below "
                "(the Excel file contains them too). Try fewer or different filters.")

    if entry["file_bytes"]:
        if entry["file_is_excel"]:
            st.download_button("⬇️  Download Excel File", entry["file_bytes"],
                               file_name=entry["file_name"], mime=XLSX_MIME, type="primary")
        else:
            st.warning("The Excel file couldn't be created, so the results were saved as JSON.")
            st.download_button("⬇️  Download results (JSON)", entry["file_bytes"],
                               file_name=entry["file_name"], mime="application/json")

    if entry["rows"]:
        if entry["matched"]:
            st.markdown('<div class="ls-section" style="margin-top:14px">🔥 Top opportunities</div>',
                        unsafe_allow_html=True)
            st.markdown(ui.top_opportunities(entry["rows"]), unsafe_allow_html=True)

        st.markdown(f'<div class="ls-section">📋 {"All leads" if entry["matched"] else "All businesses found"}'
                    '</div>', unsafe_allow_html=True)
        df = pd.DataFrame(entry["rows"], columns=COLUMN_HEADERS)
        search = st.text_input("Search results", placeholder="🔎 Type to filter by any column...",
                               key=f"search_{entry['id']}", label_visibility="collapsed")
        if search:
            mask = df.astype(str).apply(
                lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
            df = df[mask]
        st.markdown(ui.legend(), unsafe_allow_html=True)
        st.caption(f"Showing {len(df)} of {len(entry['rows'])} leads")
        st.dataframe(
            style_missing(df),
            width="stretch",
            hide_index=True,
            height=min(600, 38 + 35 * max(len(df), 1)),
            column_config={
                **{c: st.column_config.LinkColumn(c) for c in LINK_COLUMNS},
                "Lead Score": st.column_config.ProgressColumn(
                    "Lead Score", min_value=0, max_value=100, format="%d"),
            },
        )


# --- Footer ------------------------------------------------------------------

st.markdown(ui.footer(HOSTED), unsafe_allow_html=True)
