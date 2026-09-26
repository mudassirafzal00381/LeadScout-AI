"""Global settings for LeadScout AI.

Any setting marked "env" can be overridden with an environment variable,
so deployments can be adjusted without editing code.
"""

import os
import sys
import tempfile
from pathlib import Path

# --- Paths ---
# When packaged with PyInstaller, keep user files next to the .exe
# (not in the temporary unpack folder).
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# env: LEADSCOUT_OUTPUT_DIR
OUTPUT_DIR = Path(os.environ.get("LEADSCOUT_OUTPUT_DIR", BASE_DIR / "output"))
# One log file per day (errors with full details). env: LEADSCOUT_LOG_DIR
LOG_DIR = Path(os.environ.get("LEADSCOUT_LOG_DIR", BASE_DIR / "logs"))


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


# Some hosting platforms make the app folder read-only; fall back to the temp folder.
if not _writable(OUTPUT_DIR):
    OUTPUT_DIR = Path(tempfile.gettempdir()) / "leadscout" / "output"
if not _writable(LOG_DIR):
    LOG_DIR = Path(tempfile.gettempdir()) / "leadscout" / "logs"

# --- Rate limits (seconds between requests) ---
OSM_REQUEST_DELAY = 1.0
# Google Maps waits a random time in this range (seconds) between actions.
MAPS_DELAY_RANGE = (1.5, 4.0)
# Most Google Maps listings opened per category in one search, whatever the
# "max results" setting in the web app (keeps browsing light; see maps_collector).
MAPS_MAX_RESULTS_CAP = 25
MAPS_PAGE_TIMEOUT = 30  # seconds to wait for a Google Maps page to load
ENRICHMENT_REQUEST_DELAY = 1.5

# --- Search categories ---
# Searched one by one when a request names no specific business type
# (e.g. "businesses in Lahore that need a website"). Names must be keys of
# modules.osm_collector.CATEGORY_TAGS.
DEFAULT_CATEGORIES = [
    "restaurant", "cafe", "salon", "gym", "clinic", "dentist",
    "pharmacy", "hotel", "bakery", "retail_store", "real_estate", "car_repair",
]
# Smaller per-category limits for multi-category runs, to keep Google Maps use light.
ALL_CATEGORIES_OSM_MAX = 50
ALL_CATEGORIES_MAPS_MAX = 10

# --- Data cleaning ---
# Country calling code used to convert local numbers ("0321...") to "+92321...".
# env: LEADSCOUT_PHONE_COUNTRY_CODE  (digits only, e.g. "92" Pakistan, "1" USA)
DEFAULT_PHONE_COUNTRY_CODE = os.environ.get("LEADSCOUT_PHONE_COUNTRY_CODE", "92").lstrip("+")

# --- HTTP ---
REQUEST_TIMEOUT = 15  # seconds

# Business websites are fetched with a regular desktop-browser User-Agent,
# since many small sites reject unknown clients.
ENRICHMENT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)
ENRICHMENT_MAX_PAGE_BYTES = 3_000_000  # stop reading very large homepages

# OpenStreetMap's Nominatim/Overpass usage policy requires a User-Agent that
# identifies the application and how to reach its operator.
# env: LEADSCOUT_CONTACT  (a URL or email address)
CONTACT = os.environ.get("LEADSCOUT_CONTACT", "https://github.com/mudassirafzal00381/LeadScout-AI")
USER_AGENTS = [
    f"LeadScoutAI/1.0 (+{CONTACT})",
    # Add additional user-agent strings here.
]

# Google Maps collection can be switched off, e.g. on cloud servers where Google
# tends to block automated browsing. env: LEADSCOUT_GOOGLE_MAPS ("1"/"0")
GOOGLE_MAPS_ENABLED = os.environ.get("LEADSCOUT_GOOGLE_MAPS", "1") != "0"

# Web app password. Leave unset for local use (no login). On a hosted copy, set
# it as a secret environment variable - never commit it to the repository.
# env: LEADSCOUT_PASSWORD
APP_PASSWORD = os.environ.get("LEADSCOUT_PASSWORD", "")

# --- Browser (Playwright) ---
# Browsers are tried in order; the first one installed on the machine is used.
# On Windows: Google Chrome first, then the preinstalled Microsoft Edge, so no
# browser download is needed. Elsewhere (e.g. the Docker image), use
# Playwright's bundled Chromium.
# env: LEADSCOUT_BROWSER_CHANNELS  comma-separated, e.g. "chrome,msedge" or "bundled"
_default_channels = "chrome,msedge" if sys.platform == "win32" else "bundled"
BROWSER_CHANNELS = [
    c.strip().lower()
    for c in os.environ.get("LEADSCOUT_BROWSER_CHANNELS", _default_channels).split(",")
    if c.strip()
]

# env: LEADSCOUT_HEADLESS  ("1"/"0")
HEADLESS = os.environ.get("LEADSCOUT_HEADLESS", "1") != "0"

# --- OpenStreetMap (Nominatim geocoding + Overpass API) ---
# Both allow at most 1 request/second (see OSM_REQUEST_DELAY) and require an
# identifying User-Agent (USER_AGENTS[0]).
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY_TIMEOUT = 90  # seconds the Overpass server may spend on a query
