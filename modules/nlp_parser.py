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
              "parlor", "hairdresser"],
    "spa": ["spa", "massage center", "massage centre"],
    "gym": ["gym", "fitness center", "fitness centre", "fitness studio", "health club"],
    "clinic": ["clinic", "medical center", "medical centre", "health center", "health centre"],
    "doctor": ["doctor", "physician", "gp"],
    "dentist": ["dentist", "dental clinic", "dental"],
    "pharmacy": ["pharmacy", "pharmacies", "chemist", "drugstore", "medical store"],
    "hospital": ["hospital"],
    "hotel": ["hotel", "guest house", "guesthouse", "motel", "hostel"],
    "retail_store": ["retail store", "retail shop", "retailer", "store", "shop"],
    "supermarket": ["supermarket", "grocery store", "grocery", "groceries", "mart"],
    "real_estate": ["real estate", "estate agent", "property dealer", "realtor", "real estate agent"],
    "car_repair": ["car repair", "auto repair", "mechanic", "workshop", "garage"],
    "lawyer": ["lawyer", "law firm", "attorney", "advocate", "solicitor"],
    "plumber": ["plumber", "plumbing", "plumbing company"],
    "electrician": ["electrician", "electrical contractor", "electrical company"],
    "roofer": ["roofer", "roofing", "roofing company", "roofing contractor"],
    "painter": ["painter", "painting contractor", "house painter"],
    "carpenter": ["carpenter", "joiner", "carpentry"],
    "hvac": ["hvac", "air conditioning", "ac repair", "heating and cooling"],
    "landscaper": ["landscaper", "landscaping", "gardener", "lawn care"],
    "builder": ["builder", "contractor", "construction company", "general contractor"],
    "cleaning": ["cleaning company", "cleaning service", "cleaner", "dry cleaner", "laundry",
                 "maid service", "janitorial"],
    "florist": ["florist", "flower shop"],
    "photographer": ["photographer", "photography studio", "photo studio"],
    "accountant": ["accountant", "accounting firm", "cpa", "bookkeeper", "tax advisor"],
    "insurance": ["insurance agent", "insurance agency", "insurance broker"],
    "travel_agency": ["travel agency", "travel agent", "tour operator"],
    "optician": ["optician", "optometrist", "eye clinic", "optical store"],
    "physiotherapist": ["physiotherapist", "physical therapist", "physiotherapy", "physio"],
    "chiropractor": ["chiropractor"],
    "car_wash": ["car wash", "car detailing", "auto detailing"],
    "car_dealer": ["car dealer", "car dealership", "auto dealer", "car showroom"],
    "furniture": ["furniture store", "furniture shop"],
    "jewelry": ["jewelry store", "jeweller", "jeweler", "jewellery shop", "jewelry shop"],
    "pet_store": ["pet store", "pet shop", "pet grooming", "pet groomer"],
    "tattoo": ["tattoo studio", "tattoo shop", "tattoo parlor", "tattoo parlour"],
    "nail_salon": ["nail salon", "nail studio", "nail bar"],
    "barber": ["barber", "barbershop", "barber shop"],
    "yoga": ["yoga studio", "pilates studio"],
    "daycare": ["daycare", "day care", "nursery", "preschool", "childcare"],
    "driving_school": ["driving school"],
    "printing": ["print shop", "printing shop", "printing press", "printer"],
    "hardware": ["hardware store", "hardware shop"],
    "electronics": ["electronics store", "mobile shop", "phone shop", "electronics shop"],
    "clothing": ["clothing store", "boutique", "fashion store", "clothing shop"],
    "bookstore": ["bookstore", "book shop", "bookshop"],
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


# --- Filter text box ---------------------------------------------------------

_RATING_WORDS = re.compile(r"\b(rat(ed|ing|ings)|reviews?|stars?)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d(?:\.\d+)?")
_HAS_PHONE = re.compile(r"\b(has|have|having|with|can call)\b.*\b(phone|number|contact)", re.IGNORECASE)
_BROKEN_SITE = re.compile(r"\b(broken|down|not working|offline|dead)\b.*\bweb ?sites?\b|"
                          r"\bweb ?sites?\b.*\b(broken|down|not working|offline|dead)\b", re.IGNORECASE)
# In the filter box everything describes what the leads are MISSING, so a bare
# word is enough: "website, social media" = no website and no social media.
_MISSING = [
    (re.compile(r"\bweb ?sites?\b|\bsite\b", re.IGNORECASE), "no_website"),
    (re.compile(r"\bsocial\b|facebook|instagram|tiktok|linkedin|twitter|\bx\b|youtube|whatsapp",
                re.IGNORECASE), "no_social_media"),
    (re.compile(r"\bphones?\b|\bnumbers?\b|\bcontact\b|\bmobile\b", re.IGNORECASE), "no_phone"),
    (re.compile(r"\be-?mails?\b", re.IGNORECASE), "no_email"),
]


def parse_filter_text(text: str) -> tuple[list, list[str]]:
    """Read the Advanced Options filter box, e.g. "no website, no social media, rating below 4".

    Items are separated by commas or "and". Returns (filters, unrecognised items).
    """
    filters: list = []
    unknown: list[str] = []

    def add(rule) -> None:
        if rule not in filters:
            filters.append(rule)

    for part in re.split(r",|;|/|&|\+|\n|\band\b", text or "", flags=re.IGNORECASE):
        item = part.strip(" .")
        if not item:
            continue
        if _RATING_WORDS.search(item):
            number = _NUMBER.search(item)
            add(("low_rating", float(number.group())) if number else "low_rating")
        elif _HAS_PHONE.search(item):
            add("has_phone")
        elif _BROKEN_SITE.search(item):
            add("broken_website")
        else:
            matched = [rule for regex, rule in _MISSING if regex.search(item)]
            for rule in matched:
                add(rule)
            if not matched:
                unknown.append(item)
    return filters, unknown


# --- Public API --------------------------------------------------------------

# Words that mean "any business" rather than a specific type.
_GENERIC = {"business", "businesses", "company", "companies", "place", "places", "lead", "leads",
            "client", "clients", "customer", "customers", "local business", "local businesses",
            "small business", "small businesses", "smb", "smbs", "firm", "firms", "brand", "brands",
            "all", "everything", "anything"}
_LEADING = re.compile(r"^(?:please\s+)?(?:find|show|get|search|list|give)(?:\s+me)?\s+|"
                      r"^(?:all|some|any|the|local|small)\s+", re.IGNORECASE)


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _custom_category(text: str) -> str | None:
    """A business type we have no list entry for, e.g. "solar installers in Austin" -> "solar installer".

    Google Maps understands any business type, and OpenStreetMap is searched for
    the same word, so unknown types still work instead of falling back to "all".
    """
    match = re.match(r"^(.+?)\s+(?:in|near|around|at|within)\s+", text, re.IGNORECASE)
    if not match:
        return None
    phrase = match.group(1).strip().lower()
    for _ in range(3):  # strip "find me all local ..." step by step
        phrase = _LEADING.sub("", phrase).strip()
    phrase = re.sub(r"[^\w\s&'-]", "", phrase)
    words = phrase.split()
    if not words or phrase in _GENERIC or len(words) > 4:
        return None
    words[-1] = _singular(words[-1])
    custom = " ".join(words)
    return None if custom in _GENERIC else custom


def parse_user_request(text: str) -> dict:
    """Turn a plain-language request into {category, categories, location, filters}.

    category:   the first business type mentioned, or "all" if none/generic.
    categories: every category to search. For "all" this is
                config.DEFAULT_CATEGORIES, so callers can simply loop over it.
    location:   the place to search, or None if none was found.
    filters:    filter rules for modules.filters.filter_leads, e.g. ["no_website"].
    """
    text = (text or "").strip()
    categories = _find_categories(text) or [c for c in [_custom_category(text)] if c]
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
