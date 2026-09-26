"""LeadScout AI - web interface.

Run with:  streamlit run app.py

If the LEADSCOUT_PASSWORD environment variable is set (e.g. as a secret on a
hosted copy), visitors must enter it before using the app. Locally it is
normally unset, so no login is needed.
"""

import hmac
import ipaddress
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import config
from main import setup_logging
from modules.excel_export import COLUMN_HEADERS, table_rows
from modules.nlp_parser import parse_user_request
from modules.pipeline import run_pipeline

st.set_page_config(page_title="LeadScout AI", page_icon="🔎", layout="wide")

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
            st.title("LeadScout AI")
            st.error("This copy of LeadScout AI has no password set, so it only works on the "
                     "computer it runs on. To allow access from other devices, set the "
                     "LEADSCOUT_PASSWORD secret.")
            st.stop()
        return
    if st.session_state.get("authenticated"):
        return

    st.title("LeadScout AI")
    st.caption("This copy of LeadScout AI is private. Please enter the password.")
    failures = st.session_state.get("login_failures", 0)
    locked_until = st.session_state.get("locked_until", 0.0)
    if time.time() < locked_until:
        st.error(f"Too many wrong attempts. Try again in {int(locked_until - time.time())} seconds.")
        st.stop()

    with st.form("login"):
        attempt = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
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
        "rows": table_rows(result.matched),
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


# --- Sidebar -----------------------------------------------------------------

with st.sidebar:
    st.header("How it works")
    st.markdown(
        "1. **Describe** the leads you want in plain language.\n"
        "2. **Collect** businesses from **OpenStreetMap** (free, open data) and a "
        "**limited Google Maps** browse.\n"
        "3. **Merge** both sources and remove duplicates.\n"
        "4. **Enrich** each business website with social media links and email.\n"
        "5. **Filter & score** - businesses with more gaps (no website, no social "
        "media...) score higher: more services to sell.\n"
        "6. **Download** everything as an Excel file.\n\n"
        + ("No paid services or API keys." if HOSTED
           else "Everything runs on your computer. No paid services or API keys.")
    )
    st.divider()
    st.header("Search history")
    if not st.session_state.history:
        st.caption("Your searches in this session will appear here.")
    for entry in reversed(st.session_state.history):
        label = f"{entry['request'][:40]}  \n{entry['matched']} leads · {entry['time']}"
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

st.title("LeadScout AI — Lead Generation Tool")
st.markdown(
    "Find local businesses that need your services. Describe what you're looking for, "
    "and LeadScout collects businesses, checks their websites and social media, and ranks "
    "them by how much they could use your help."
)

text = st.text_input(
    "What leads are you looking for?",
    placeholder="e.g. restaurants in Lahore that need a website",
)

with st.expander("Advanced Options (override the request manually)"):
    col1, col2 = st.columns(2)
    category_choice = col1.selectbox("Category", CATEGORY_CHOICES)
    location_override = col2.text_input("Location", placeholder="From my request, e.g. Karachi")

    st.markdown("**Filters** - if you tick any, they replace the filters in your request.")
    f1, f2, f3, f4 = st.columns(4)
    manual_filters = []
    if f1.checkbox("Needs Website"):
        manual_filters.append("no_website")
    if f2.checkbox("Needs Social Media"):
        manual_filters.append("no_social_media")
    if f3.checkbox("Needs Phone Number"):
        manual_filters.append("no_phone")
    if f4.checkbox("Low Rating"):
        threshold = f4.slider("Rating below", 1.0, 5.0, 4.0, 0.1)
        manual_filters.append(("low_rating", threshold))

    use_google_maps = st.checkbox(
        "Include Google Maps (slower; often blocked on cloud servers)",
        value=GOOGLE_MAPS_DEFAULT,
        help="Google Maps adds phone numbers, ratings and websites that OpenStreetMap often "
             "lacks, but Google may show a CAPTCHA to automated browsing, especially from "
             "cloud servers. When that happens the search continues with OpenStreetMap only.")
    max_results = st.slider("Max results per source", 10, 200, 50, 10)
    st.caption(
        f"OpenStreetMap returns up to {max_results} businesses per category. Google Maps is "
        f"capped at {config.MAPS_MAX_RESULTS_CAP} per category "
        f"({config.ALL_CATEGORIES_MAPS_MAX} when searching all categories) to keep browsing light."
    )

request = build_request(text, category_choice, location_override, manual_filters)
if text.strip() or location_override.strip():
    st.caption(
        f"**Understood as:** {describe_category(request)} · "
        f"{request['location'] or '⚠️ no location yet'} · {describe_filters(request['filters'])}"
    )

find = st.button("Find Leads", type="primary")


# --- Run the pipeline --------------------------------------------------------

if find:
    if not request["location"]:
        st.error('Please include a location, e.g. "salons in **Karachi**", or set one in '
                 "Advanced Options.")
    else:
        many = len(request["categories"]) > 1
        maps_cap = config.ALL_CATEGORIES_MAPS_MAX if many else config.MAPS_MAX_RESULTS_CAP
        started = time.monotonic()
        st.info("This can take a few minutes. Please keep this tab open and don't change the "
                "inputs until it finishes.")
        status = st.status("Finding leads...", expanded=True)
        bar = status.progress(0.0, text="Starting...")
        detail = status.empty()

        def on_progress(stage: str, message: str, fraction: float | None) -> None:
            if stage == "detail":
                detail.caption(message)
            elif stage == "warning":
                status.warning(message)
            else:
                if stage in ("collect", "osm", "maps", "merge", "enrich", "score", "export"):
                    status.write(f"⏳ {message}")
                if fraction is not None:
                    elapsed = int(time.monotonic() - started)
                    bar.progress(min(max(fraction, 0.0), 1.0), text=f"{message}  ({elapsed}s)")

        try:
            result = run_pipeline(request, osm_max=max_results,
                                  maps_max=min(max_results, maps_cap),
                                  use_google_maps=use_google_maps, on_progress=on_progress)
        except Exception as exc:  # noqa: BLE001 - never show a raw crash to the user
            import logging
            logging.getLogger("leadscout.app").exception("Pipeline crashed")
            status.update(label="Something went wrong", state="error", expanded=True)
            st.error(f"The search stopped unexpectedly: {exc}. Details are in the log file"
                     f"{f' ({LOG_PATH})' if LOG_PATH else ''}.")
        else:
            detail.empty()
            state = "error" if result.errors and not result.leads else "complete"
            status.update(
                label=f"Done: {len(result.matched)} matching leads out of {len(result.leads)} "
                      f"found ({int(result.seconds // 60)}m {int(result.seconds % 60)}s)",
                state=state, expanded=False)
            if result.leads:
                save_to_history(text, request, result)
                st.rerun()  # redraw so the sidebar history includes this search
            else:
                st.warning("No businesses were found. Try a different area or business type.")
                for error in result.errors:
                    st.error(error)


# --- Results -----------------------------------------------------------------

entry = next((e for e in st.session_state.history if e["id"] == st.session_state.current), None)
if entry:
    st.divider()
    st.subheader(f"Results: {entry['request']}")
    st.caption(f"{describe_category(entry['parsed'])} · {entry['parsed']['location']} · "
               f"{describe_filters(entry['parsed']['filters'])}")

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Leads Found", entry["total"])
    m2.metric("Leads Matching Filters",
              entry["matched"] if entry["filters_applied"] else "n/a")
    m3.metric("Average Lead Score",
              f"{entry['average_score']:.0f}" if entry["average_score"] is not None else "–")

    if entry["errors"]:
        st.warning(
            "Some steps had problems, so these results may be incomplete:\n\n"
            + "\n".join(f"- {e}" for e in entry["errors"])
            + (f"\n\nDetails: `{LOG_PATH}`" if LOG_PATH else "")
        )
    if not entry["filters_applied"]:
        st.warning("The filters could not be applied, so all businesses are shown.")
    if entry["matched"] == 0:
        st.info("No businesses matched your filters. The Excel file contains all businesses found.")

    if entry["file_bytes"]:
        if entry["file_is_excel"]:
            st.download_button("⬇️ Download Excel File", entry["file_bytes"],
                               file_name=entry["file_name"], mime=XLSX_MIME, type="primary")
        else:
            st.warning("The Excel file couldn't be created, so the results were saved as JSON.")
            st.download_button("⬇️ Download results (JSON)", entry["file_bytes"],
                               file_name=entry["file_name"], mime="application/json")

    if entry["rows"]:
        df = pd.DataFrame(entry["rows"], columns=COLUMN_HEADERS)
        search = st.text_input("Search results", placeholder="Type to filter by any column...",
                               key=f"search_{entry['id']}")
        if search:
            mask = df.astype(str).apply(
                lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
            df = df[mask]
        st.caption(f"Showing {len(df)} of {len(entry['rows'])} leads · click a column header to "
                   "sort · red = key gap (no phone/website), orange = other missing info")
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

st.divider()
if HOSTED:
    st.caption("Online demo: files are not kept on the server - use **Download Excel File** to "
               "save your results. Searches run on a cloud server, where Google Maps is often "
               "blocked; for complete results run LeadScout on your own computer.")
st.caption("Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) "
           "(ODbL).")
st.caption("LeadScout AI uses only free and legal data sources (OpenStreetMap + limited Google "
           "Maps browsing). No paid API keys required.")
