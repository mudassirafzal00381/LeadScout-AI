"""Parse plain-language requests into search parameters (no AI/API needed).

    parse_user_request("restaurants in Lahore that need a website")
    -> {"category": "restaurant", "categories": ["restaurant"],
        "location": "Lahore", "filters": ["no_website"]}

Everything is keyword/pattern based, so it runs offline and instantly. To teach
it new words, extend CATEGORY_SYNONYMS, FILTER_PATTERNS or KNOWN_PLACES.
"""

import re

import config

# Canonical category -> words people use for it (singular; plurals handled).
# Canonical names must match modules.osm_collector.CATEGORY_TAGS keys.
CATEGORY_SYNONYMS = {
    "restaurant": ["restaurant", "eatery", "diner", "dhaba", "food place", "grill", "steakhouse"],
    "cafe": ["cafe", "café", "coffee shop", "coffee house", "tea house"],
    "fast_food": ["fast food", "burger joint", "pizza place", "pizzeria"],
    "bakery": ["bakery", "bakeries", "cake shop", "patisserie"],
    "salon": ["salon", "hair salon", "beauty salon", "beauty parlour", "beauty parlor", "parlour",
              "parlor", "barber", "barbershop", "hairdresser", "nail salon"],
    "spa": ["spa", "massage center", "massage centre"],
    "gym": ["gym", "fitness center", "fitness centre", "fitness studio", "health club"],
    "clinic": ["clinic", "medical center", "medical centre", "health center", "health centre"],
    "doctor": ["doctor", "physician", "gp"],
    "dentist": ["dentist", "dental clinic", "dental"],
    "pharmacy": ["pharmacy", "pharmacies", "chemist", "drugstore", "medical store"],
    "hospital": ["hospital"],
    "hotel": ["hotel", "guest house", "guesthouse", "motel", "hostel"],
    "retail_store": ["retail store", "retail shop", "retailer", "store", "shop", "boutique",
                     "clothing store", "clothing shop"],
    "supermarket": ["supermarket", "grocery store", "grocery", "groceries", "mart"],
    "real_estate": ["real estate", "estate agent", "property dealer", "realtor", "real estate agent"],
    "car_repair": ["car repair", "auto repair", "mechanic", "workshop", "garage"],
    "lawyer": ["lawyer", "law firm", "attorney", "advocate"],
    "school": ["school", "academy", "tuition center", "tuition centre"],
    "veterinary": ["vet", "veterinary", "veterinarian", "pet clinic"],
}

# Requests with no category word ("businesses in Lahore ...") search all
# of config.DEFAULT_CATEGORIES.

# Filter intent: regex -> filter rule (see modules.filters). Checked in order.
FILTER_PATTERNS = [
    (r"\b(broken|down|not working|dead|offline)\s+(web ?sites?|sites?)\b|"
     r"\b(web ?sites?|sites?)\s+(is |are )?(broken|down|not working|offline)\b", "broken_website"),
    (r"\b(need|needs|needing|want|wants|require|requires|without|no|lack|lacks|lacking|missing|"
     r"don'?t have|do not have|doesn'?t have|does not have|with no)\b[\w\s]{0,15}?\bweb ?sites?\b",
     "no_website"),
    (r"\bno[- ]website\b|\bwebsite[- ]less\b", "no_website"),
    (r"\b(social media|social presence|socials|instagram|facebook|tiktok|online presence)\b",
     "no_social_media"),
    (r"\b(without|no|missing|lack\w*)\b[\w\s]{0,10}?\b(phone|contact number|phone number)s?\b",
     "no_phone"),
    (r"\b(without|no|missing|lack\w*)\b[\w\s]{0,10}?\bemails?\b", "no_email"),
    (r"\b(with|has|have|having)\s+(a\s+)?(phone|contact number|phone number)s?\b|"
     r"\b(can|could)\s+call\b|\bcontactable\b", "has_phone"),
]
_LOW_RATING_RE = re.compile(
    r"\b(low|bad|poor|negative)\s+(ratings?|reviews?|stars?)\b|"
    r"\brat(ed|ing|ings)\s+(below|under|less than|lower than)\s+(\d(?:\.\d)?)", re.IGNORECASE)

# Places recognised even without "in ..." (e.g. "Lahore salons"). Not exhaustive:
# anything after "in/near/around" is accepted as a location regardless.
KNOWN_PLACES = [
    # Pakistan
    "Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar", "Quetta",
    "Sialkot", "Gujranwala", "Hyderabad", "Bahawalpur", "Sargodha", "Abbottabad", "Pakistan",
    # Middle East / South Asia
    "Dubai", "Abu Dhabi", "Sharjah", "Riyadh", "Jeddah", "Doha", "UAE", "Saudi Arabia", "Qatar",
    "Delhi", "Mumbai", "Bangalore", "India", "Dhaka", "Bangladesh",
    # Europe / Americas / Oceania
    "London", "Manchester", "Birmingham", "UK", "United Kingdom", "England", "Paris", "Berlin",
    "Toronto", "Vancouver", "Canada", "New York", "Los Angeles", "Chicago", "Houston", "Miami",
    "USA", "United States", "Sydney", "Melbourne", "Australia",
]
_ACRONYMS = {"usa": "USA", "us": "USA", "uk": "UK", "uae": "UAE", "ksa": "KSA", "nyc": "NYC"}

# "in <location>" ends where the rest of the sentence begins.
_LOCATION_STOP = (r"that|which|who|whose|with|without|needing|need|needs|lacking|lack|missing|"
                  r"having|has|have|where|and\s+(?:need|have|lack|want)|but|to|for|"
                  r"rated|rating|ratings|reviews?|reviewed|scoring|below|under|above|"
                  r"is|are|currently|lately|please|only")
_LOCATION_RE = re.compile(
    rf"\b(?:in|near|around|at|within|across|from)\s+(?!need\b|the\s+need\b)"
    rf"(.+?)(?=\s+(?:{_LOCATION_STOP})\b|[.;!?]|$)",
    re.IGNORECASE,
)


# --- Helpers -----------------------------------------------------------------

def _word_pattern(phrase: str) -> str:
    """Regex for a phrase with an optional plural on its last word."""
    words = [re.escape(w) for w in phrase.split()]
    last = words[-1]
    plural = r"(?:s|es)?" if not phrase.endswith("ies") else ""
    if phrase.endswith("y"):  # pharmacy -> pharmacies, bakery -> bakeries
        last = f"{re.escape(phrase.split()[-1][:-1])}(?:y|ies)"
        plural = ""
    return r"\b" + r"\s+".join(words[:-1] + [last + plural]) + r"\b"


# (compiled regex, canonical category, phrase length) sorted longest phrase first,
# so "dental clinic" wins over "clinic" and "beauty salon" over "salon".
_CATEGORY_MATCHERS = sorted(
    ((re.compile(_word_pattern(p), re.IGNORECASE), cat, len(p))
     for cat, phrases in CATEGORY_SYNONYMS.items() for p in phrases),
    key=lambda m: -m[2],
)
_KNOWN_PLACE_RES = [(re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE), p)
                    for p in sorted(KNOWN_PLACES, key=len, reverse=True)]


def _find_categories(text: str) -> list[str]:
    """All categories mentioned, in the order they appear in the text."""
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, str]] = []
    for regex, category, _ in _CATEGORY_MATCHERS:
        for m in regex.finditer(text):
            if any(m.start() < end and start < m.end() for start, end in taken):
                continue  # already covered by a longer phrase
            taken.append((m.start(), m.end()))
            found.append((m.start(), category))
    ordered = []
    for _, category in sorted(found):
        if category not in ordered:
            ordered.append(category)
    return ordered


def _tidy_location(raw: str) -> str:
    loc = re.sub(r"^(the\s+)", "", raw.strip(" ,"), flags=re.IGNORECASE)
    loc = re.sub(r"\s+(area|city|region|district)$", "", loc, flags=re.IGNORECASE)
    parts = []
    for word in loc.split():
        core = word.strip(",")
        if core.lower() in _ACRONYMS:
            fixed = _ACRONYMS[core.lower()]
        elif core.islower():
            fixed = core.capitalize()
        else:
            fixed = core  # keep the user's capitalisation ("DHA", "McLean")
        parts.append(word.replace(core, fixed))
    return " ".join(parts)


def _find_location(text: str) -> str | None:
    for match in _LOCATION_RE.finditer(text):
        candidate = _tidy_location(match.group(1))
        # Skip phrases that are really categories or filler ("in need", "in the area").
        if candidate and not _find_categories(candidate) and len(candidate) <= 60:
            return candidate
    for regex, place in _KNOWN_PLACE_RES:
        if regex.search(text):
            return place
    return None


def _find_filters(text: str) -> list:
    filters: list = []
    for pattern, rule in FILTER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE) and rule not in filters:
            filters.append(rule)
    low = _LOW_RATING_RE.search(text)
    if low:
        threshold = low.group(5)
        filters.append(("low_rating", float(threshold)) if threshold else "low_rating")
    # "broken website" also mentions a website; don't add the contradictory no_website.
    if "broken_website" in filters and "no_website" in filters:
        if not re.search(r"\b(no|without|need\w*|lack\w*)\s+(a\s+)?web ?sites?\b", text, re.IGNORECASE):
            filters.remove("no_website")
    return filters


# --- Public API --------------------------------------------------------------

def parse_user_request(text: str) -> dict:
    """Turn a plain-language request into {category, categories, location, filters}.

    category:   the first business type mentioned, or "all" if none/generic.
    categories: every category to search. For "all" this is
                config.DEFAULT_CATEGORIES, so callers can simply loop over it.
    location:   the place to search, or None if none was found.
    filters:    filter rules for modules.filters.filter_leads, e.g. ["no_website"].
    """
    text = (text or "").strip()
    categories = _find_categories(text)
    if not categories:
        category = "all"
        categories = list(config.DEFAULT_CATEGORIES)
    else:
        category = categories[0]
    return {
        "category": category,
        "categories": categories,
        "location": _find_location(text),
        "filters": _find_filters(text),
    }
