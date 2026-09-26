"""Collect business leads from OpenStreetMap via Nominatim + the Overpass API.

Flow:
    1. Geocode the location name to a bounding box with Nominatim.
    2. Query Overpass for named businesses of the category inside that box.
    3. Normalise each result into a flat lead dictionary.

Both services are free but have usage policies (max 1 request/second, an
identifying User-Agent). All HTTP calls go through `_get`, which enforces
config.OSM_REQUEST_DELAY between requests.
"""

import logging
import threading
import time

import requests

import config
from modules.lead import new_lead

log = logging.getLogger(__name__)

# Friendly category names -> OSM tag filters (key, value).
# Anything not listed is searched across the common business keys.
CATEGORY_TAGS = {
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "fast_food": [("amenity", "fast_food")],
    "bar": [("amenity", "bar"), ("amenity", "pub")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "hairdresser": [("shop", "hairdresser")],
    "beauty": [("shop", "beauty")],
    "spa": [("leisure", "spa"), ("shop", "massage")],
    "clinic": [("amenity", "clinic"), ("amenity", "doctors"), ("healthcare", "clinic")],
    "doctor": [("amenity", "doctors")],
    "dentist": [("amenity", "dentist")],
    "pharmacy": [("amenity", "pharmacy")],
    "hospital": [("amenity", "hospital")],
    "gym": [("leisure", "fitness_centre")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "bakery": [("shop", "bakery")],
    "supermarket": [("shop", "supermarket")],
    "school": [("amenity", "school")],
    "car_repair": [("shop", "car_repair")],
    "retail_store": [("shop", "clothes"), ("shop", "convenience"), ("shop", "department_store"),
                     ("shop", "general"), ("shop", "shoes"), ("shop", "electronics")],
    "real_estate": [("office", "estate_agent")],
    "lawyer": [("office", "lawyer")],
    "veterinary": [("amenity", "veterinary")],
}
FALLBACK_KEYS = ["amenity", "shop", "healthcare", "leisure", "tourism", "craft", "office"]

_session = requests.Session()
_session.headers["User-Agent"] = config.USER_AGENTS[0]
_last_request = 0.0
_lock = threading.Lock()


def _get(url: str, params: dict, timeout: float) -> requests.Response:
    """GET with a global minimum delay between OSM requests and retry on overload."""
    global _last_request
    for attempt in range(3):
        with _lock:
            wait = config.OSM_REQUEST_DELAY - (time.monotonic() - _last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = _session.get(url, params=params, timeout=timeout)
            finally:
                _last_request = time.monotonic()

        # 429 = rate limited, 502/503/504 = Overpass busy; back off and retry.
        if resp.status_code in (429, 502, 503, 504) and attempt < 2:
            backoff = 10 * (attempt + 1)
            log.warning("%s returned %s, retrying in %ss", url, resp.status_code, backoff)
            time.sleep(backoff)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable")


def geocode_bbox(location: str) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) for a place name using Nominatim."""
    resp = _get(
        config.NOMINATIM_URL,
        {"q": location, "format": "jsonv2", "limit": 1, "accept-language": "en"},
        timeout=config.REQUEST_TIMEOUT,
    )
    results = resp.json()
    if not results:
        raise ValueError(f"Location not found: {location!r}")
    south, north, west, east = (float(v) for v in results[0]["boundingbox"])
    return south, west, north, east


def _build_query(category: str, bbox: tuple, max_results: int) -> str:
    key = category.strip().lower().replace(" ", "_")
    tags = CATEGORY_TAGS.get(key) or [(k, key) for k in FALLBACK_KEYS]
    bbox_str = ",".join(str(v) for v in bbox)
    selectors = "\n".join(
        f'  nwr["{k}"="{v}"]["name"]({bbox_str});' for k, v in tags
    )
    return (
        f"[out:json][timeout:{config.OVERPASS_QUERY_TIMEOUT}];\n"
        f"(\n{selectors}\n);\n"
        f"out center tags {int(max_results)};"
    )


def _first(tags: dict, *keys: str) -> str:
    for k in keys:
        value = tags.get(k)
        if value:
            return value.strip()
    return ""


def _format_address(tags: dict) -> str:
    full = tags.get("addr:full")
    if full:
        return full.strip()
    street = " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p)
    parts = [street, tags.get("addr:suburb"), tags.get("addr:city"), tags.get("addr:postcode")]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _to_lead(element: dict, category: str) -> dict:
    tags = element.get("tags") or {}
    # Nodes carry lat/lon directly; ways/relations carry a computed "center".
    point = element if "lat" in element else element.get("center") or {}
    osm_type, osm_id = element.get("type", ""), element.get("id", "")
    return new_lead(
        name=_first(tags, "name", "name:en"),
        category=category,
        address=_format_address(tags),
        phone=_first(tags, "phone", "contact:phone", "mobile", "contact:mobile"),
        website=_first(tags, "website", "contact:website", "url"),
        latitude=point.get("lat"),
        longitude=point.get("lon"),
        source="OpenStreetMap",
        source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else "",
    )


def collect_from_osm(category: str, location: str, max_results: int = 100) -> list[dict]:
    """Collect up to `max_results` businesses of `category` in `location` from OSM.

    Each lead is a dict in the shared format from modules.lead (rating and
    review_count are always None for OSM). Missing text fields are "" and
    missing numbers are None.
    """
    bbox = geocode_bbox(location)
    log.info("Bounding box for %s: %s", location, bbox)

    query = _build_query(category, bbox, max_results)
    resp = _get(config.OVERPASS_URL, {"data": query},
                timeout=config.OVERPASS_QUERY_TIMEOUT + 30)
    elements = resp.json().get("elements", [])

    leads = []
    for element in elements:
        try:
            lead = _to_lead(element, category)
        except Exception:  # noqa: BLE001 - skip malformed elements, never crash
            log.warning("Skipping malformed OSM element: %r", element.get("id"))
            continue
        if lead["name"]:
            leads.append(lead)
    return leads[:max_results]
