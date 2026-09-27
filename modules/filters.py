"""Rule-based lead filtering and scoring.

Rules can be written as:
    "no_website"                              a rule name
    ("low_rating", 3.5)                       a rule with a parameter
    {"rule": "low_rating", "threshold": 3.5}  a rule with named parameters
    {"any": [rule, rule, ...]}                OR  - at least one must match
    {"all": [rule, rule, ...]}                AND - every one must match
    {"not": rule}                             NOT - the rule must not match

Groups can be nested, e.g. businesses with no website OR no social media,
that do have a phone number to call:

    filter_leads(leads, [{"any": ["no_website", "no_social_media"]}, "has_phone"])

A plain list of rules is combined with AND by default (mode="OR" to change).
"""

from typing import Callable

# Website statuses that mean "has a website, but it's broken" (see modules.enrichment).
BROKEN_WEBSITE_STATUSES = {"unreachable", "timeout", "error"}

# Points added per gap. Total of the main gaps is 100.
SCORE_WEIGHTS = {
    "website": 40,       # no website, or only a social media page, or a broken one
    "social_media": 30,
    "phone": 30,
}

_RULES: dict[str, Callable[..., bool]] = {}


def rule(name: str):
    """Register a filter rule under `name`."""
    def register(func):
        _RULES[name] = func
        return func
    return register


def available_rules() -> list[str]:
    return sorted(_RULES)


# --- Helpers -----------------------------------------------------------------

def _has_real_website(b: dict) -> bool:
    """A website that isn't just a Facebook/Instagram page."""
    return bool(b.get("website")) and b.get("website_status") != "social_only"


def _website_broken(b: dict) -> bool:
    status = b.get("website_status") or ""
    return _has_real_website(b) and (status in BROKEN_WEBSITE_STATUSES or status.startswith("http_5"))


# --- Rules -------------------------------------------------------------------

@rule("no_website")
def no_website(b: dict) -> bool:
    """No website, or the 'website' is only a social media page."""
    return not _has_real_website(b)


@rule("broken_website")
def broken_website(b: dict) -> bool:
    """Has a website, but it didn't load (unreachable, timeout, server error)."""
    return _website_broken(b)


@rule("no_social_media")
def no_social_media(b: dict) -> bool:
    return not b.get("social_media")


@rule("no_phone")
def no_phone(b: dict) -> bool:
    return not b.get("phone")


@rule("has_phone")
def has_phone(b: dict) -> bool:
    """Useful to keep only leads you can actually call."""
    return bool(b.get("phone"))


@rule("no_email")
def no_email(b: dict) -> bool:
    return not b.get("email")


@rule("low_rating")
def low_rating(b: dict, threshold: float = 4.0) -> bool:
    """Rating below threshold. Businesses with no rating don't match."""
    rating = b.get("rating")
    return rating is not None and rating < float(threshold)


# --- Engine ------------------------------------------------------------------

def _evaluate(b: dict, spec) -> bool:
    if isinstance(spec, str):
        return _call_rule(spec, b)
    if isinstance(spec, tuple) and spec and isinstance(spec[0], str):
        return _call_rule(spec[0], b, *spec[1:])
    if isinstance(spec, dict):
        if "any" in spec:
            return any(_evaluate(b, s) for s in spec["any"])
        if "all" in spec:
            return all(_evaluate(b, s) for s in spec["all"])
        if "not" in spec:
            return not _evaluate(b, spec["not"])
        if "rule" in spec:
            params = {k: v for k, v in spec.items() if k != "rule"}
            return _call_rule(spec["rule"], b, **params)
    raise ValueError(f"Invalid filter rule: {spec!r}")


def _validate(spec) -> None:
    """Raise ValueError for unknown rule names or malformed rules, anywhere in the tree."""
    if isinstance(spec, str):
        name = spec
    elif isinstance(spec, tuple) and spec and isinstance(spec[0], str):
        name = spec[0]
    elif isinstance(spec, dict) and ("any" in spec or "all" in spec):
        group = spec.get("any", spec.get("all"))
        if not isinstance(group, (list, tuple)):
            raise ValueError(f"'any'/'all' must hold a list of rules: {spec!r}")
        for sub in group:
            _validate(sub)
        return
    elif isinstance(spec, dict) and "not" in spec:
        _validate(spec["not"])
        return
    elif isinstance(spec, dict) and "rule" in spec:
        name = spec["rule"]
    else:
        raise ValueError(f"Invalid filter rule: {spec!r}")
    if name not in _RULES:
        raise ValueError(f"Unknown filter rule {name!r}. Available: {', '.join(available_rules())}")


def _call_rule(name: str, b: dict, *args, **kwargs) -> bool:
    func = _RULES.get(name)
    if func is None:
        raise ValueError(f"Unknown filter rule {name!r}. Available: {', '.join(available_rules())}")
    return func(b, *args, **kwargs)


def find_missing_fields(business: dict) -> list[str]:
    """List what a business is missing, e.g. ["website", "social_media", "email"]."""
    missing = []
    if not _has_real_website(business):
        missing.append("website")
    elif _website_broken(business):
        missing.append("website (broken)")
    for field in ("social_media", "phone", "email", "address"):
        if not business.get(field):
            missing.append(field)
    return missing


def calculate_lead_score(business: dict) -> int:
    """Score 0-100: higher means more gaps, i.e. more services to sell.

    No (real/working) website +40, no social media +30, no phone +30.
    """
    score = 0
    if not _has_real_website(business) or _website_broken(business):
        score += SCORE_WEIGHTS["website"]
    if not business.get("social_media"):
        score += SCORE_WEIGHTS["social_media"]
    if not business.get("phone"):
        score += SCORE_WEIGHTS["phone"]
    return min(score, 100)


def score_leads(business_list: list[dict]) -> list[dict]:
    """Add "lead_score" and "missing_fields" to every business (in place)."""
    for business in business_list:
        business["lead_score"] = calculate_lead_score(business)
        business["missing_fields"] = find_missing_fields(business)
    return business_list


def filter_leads(business_list: list[dict], rules=None, mode: str = "AND") -> list[dict]:
    """Return businesses matching `rules`, scored and sorted by lead_score (highest first).

    rules: a list of rules (see module docstring), combined with `mode`
           ("AND" or "OR"). None or [] keeps every business.
    Every business in business_list gets "lead_score" and "missing_fields".
    Ties are broken by: has a phone first, then has an email, then more reviews.
    """
    mode = mode.upper()
    if mode not in ("AND", "OR"):
        raise ValueError("mode must be 'AND' or 'OR'")
    rules = list(rules or [])
    spec = {"all" if mode == "AND" else "any": rules}
    _validate(spec)  # a typo fails fast, before any work is done

    score_leads(business_list)
    matched = [b for b in business_list if not rules or _evaluate(b, spec)]
    return sorted(
        matched,
        key=lambda b: (b["lead_score"], bool(b.get("phone")), bool(b.get("email")),
                       b.get("review_count") or 0),
        reverse=True,
    )
