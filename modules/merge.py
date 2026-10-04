"""Merge leads from several sources into one deduplicated, normalized list.

Two leads are treated as the same business when their names match closely
(rapidfuzz) AND their location agrees (similar address, nearby coordinates or
the same phone number). Location matters because chains share names: two
"KFC" branches across town must stay separate.
"""

import contextvars
import math
import re
import urllib.parse

import phonenumbers

from rapidfuzz import fuzz

import config
from modules.lead import LEAD_FIELDS, new_lead

# Words that don't help tell businesses apart; removed before comparing names.
_GENERIC_NAME_WORDS = {
    "the", "and", "restaurant", "restaurants", "cafe", "café", "salon", "salons",
    "clinic", "hotel", "bakery", "pvt", "ltd", "private", "limited", "co",
    "shop", "store", "center", "centre", "official",
}
_TRACKING_PARAMS = ("utm_", "fbclid", "gclid")

# Matching thresholds (0-100 similarity, metres for distance).
NAME_STRONG = 90      # names this similar only need weak location agreement
NAME_WEAK = 80        # names this similar need strong location agreement
ADDRESS_MATCH = 75
NEAR_METRES = 150     # "same place" if within this distance
FAR_METRES = 1000     # never merge leads further apart than this


# --- Normalization -----------------------------------------------------------

# Country of the current search (two-letter code), set by modules.pipeline from
# the searched city. Local numbers are read as belonging to this country.
_PHONE_REGION: contextvars.ContextVar = contextvars.ContextVar("phone_region", default=None)


def set_phone_region(region: str | None) -> None:
    _PHONE_REGION.set((region or "").upper() or None)


def phone_region() -> str:
    return _PHONE_REGION.get() or config.DEFAULT_PHONE_REGION


def normalize_phone(raw: str, region: str | None = None) -> str:
    """Normalize one or more phone numbers to international E.164 format.

    Local numbers are read in the country of the current search, e.g.
    '0321-4481300' (PK) -> '+923214481300', '(212) 555-0123' (US) ->
    '+12125550123'. Several numbers (separated by ; , / or 'or') are each
    normalized and joined with '; '. Text that isn't a possible phone number
    is kept as digits rather than guessed.
    """
    if not raw:
        return ""
    region = (region or phone_region()).upper()
    numbers = []
    for part in re.split(r"[;,/]|\bor\b", raw):
        digits = re.sub(r"\D", "", part)
        if len(digits) < 6:
            continue
        candidate = part.strip()
        if candidate.startswith("00"):
            candidate = "+" + candidate[2:]
        try:
            parsed = phonenumbers.parse(candidate, region)
            number = (phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                      if phonenumbers.is_possible_number(parsed) else digits)
        except phonenumbers.NumberParseException:
            number = digits
        if number not in numbers:
            numbers.append(number)
    return "; ".join(numbers)


def normalize_website(raw: str) -> str:
    """Normalize a URL: add https:// if missing, lowercase host, drop tracking params."""
    url = (raw or "").strip()
    if not url:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        url = "https://" + url.lstrip("/")
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
         if not k.lower().startswith(_TRACKING_PARAMS)]
    )
    path = parts.path if parts.path not in ("", "/") else ""
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def normalize_lead(lead: dict) -> dict:
    """Return a copy of a lead with every field present and phone/website normalized."""
    clean = new_lead(**{k: lead.get(k) for k in LEAD_FIELDS})
    clean["name"] = re.sub(r"\s+", " ", clean["name"]).strip()
    clean["address"] = re.sub(r"\s+", " ", clean["address"]).strip().strip(",")
    clean["phone"] = normalize_phone(clean["phone"])
    clean["website"] = normalize_website(clean["website"])
    return clean


# --- Matching ----------------------------------------------------------------

def _name_key(name: str) -> str:
    words = re.sub(r"[^\w\s]", " ", name.lower()).split()
    kept = [w for w in words if w not in _GENERIC_NAME_WORDS]
    return " ".join(kept or words)


def _distance_m(a: dict, b: dict) -> float | None:
    if None in (a["latitude"], a["longitude"], b["latitude"], b["longitude"]):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians,
                                 (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6_371_000 * 2 * math.asin(math.sqrt(h))


def _phones(lead: dict) -> set[str]:
    return {p for p in lead["phone"].split("; ") if p}


def is_same_business(a: dict, b: dict) -> bool:
    """Decide whether two normalized leads describe the same business."""
    name_a, name_b = _name_key(a["name"]), _name_key(b["name"])
    if not name_a or not name_b:
        return False
    # set_score is 100 when one name contains the other ("Monal" vs "Monal Lahore").
    # Averaging with sort_score stops a short generic name from matching
    # everything on its own; set_score alone is trusted only when the two
    # leads are physically next to each other.
    set_score = fuzz.token_set_ratio(name_a, name_b)
    name_score = (set_score + fuzz.token_sort_ratio(name_a, name_b)) / 2

    distance = _distance_m(a, b)
    if distance is not None and distance > FAR_METRES:
        return False  # e.g. two branches of the same chain

    same_phone = bool(_phones(a) & _phones(b))
    if same_phone and name_score >= 60:
        return True

    near = distance is not None and distance <= NEAR_METRES
    if near and set_score >= NAME_STRONG:
        return True
    if a["address"] and b["address"]:
        address_ok = fuzz.token_set_ratio(a["address"].lower(), b["address"].lower()) >= ADDRESS_MATCH
    else:
        address_ok = False

    if name_score >= NAME_STRONG:
        # Nothing contradicts it and at least one location signal agrees
        # (distance > FAR_METRES was already rejected above).
        return near or address_ok or distance is not None
    if name_score >= NAME_WEAK:
        return near or (address_ok and distance is None)
    return False


# --- Merging -----------------------------------------------------------------

def _completeness(lead: dict) -> int:
    return sum(1 for k in ("name", "address", "phone", "website", "latitude", "rating",
                           "review_count", "category") if lead.get(k) not in ("", None))


def _join_unique(*values: str, sep: str) -> str:
    items = []
    for value in values:
        for item in (value or "").split(sep):
            if item and item not in items:
                items.append(item)
    return sep.join(items)


def merge_leads(a: dict, b: dict) -> dict:
    """Merge two leads for the same business, preferring the more complete one."""
    primary, other = (a, b) if _completeness(a) >= _completeness(b) else (b, a)
    merged = dict(primary)
    for field, default in LEAD_FIELDS.items():
        if merged[field] in ("", None, {}, []) and other[field] not in ("", None, {}, []):
            merged[field] = other[field]
    # Longer address is usually the more complete one.
    if len(other["address"]) > len(merged["address"]):
        merged["address"] = other["address"]
    merged["phone"] = _join_unique(primary["phone"], other["phone"], sep="; ")
    merged["source"] = _join_unique(primary["source"], other["source"], sep=", ")
    merged["source_url"] = _join_unique(primary["source_url"], other["source_url"], sep=" ; ")
    return merged


def merge_and_deduplicate(osm_results: list[dict], maps_results: list[dict]) -> list[dict]:
    """Combine OSM and Google Maps leads into one clean, deduplicated list.

    - Normalizes phone numbers (E.164) and websites (https://, no tracking params).
    - Merges leads that are the same business (fuzzy name + address/location),
      filling gaps from whichever source has the data.
    - Also removes duplicates within a single source.
    """
    unified: list[dict] = []
    for raw in list(maps_results or []) + list(osm_results or []):
        try:
            lead = normalize_lead(raw)
        except Exception:  # noqa: BLE001 - skip malformed records, never crash
            continue
        if not lead["name"]:
            continue
        for i, existing in enumerate(unified):
            if is_same_business(existing, lead):
                unified[i] = merge_leads(existing, lead)
                break
        else:
            unified.append(lead)
    return unified
