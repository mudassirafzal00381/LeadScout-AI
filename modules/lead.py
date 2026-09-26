"""Shared lead record format used by every collector, so sources can be merged."""

# Text fields default to "", numeric fields to None.
LEAD_FIELDS = {
    "name": "",
    "category": "",
    "address": "",
    "phone": "",
    "website": "",
    "latitude": None,
    "longitude": None,
    "rating": None,        # float, e.g. 4.3 (Google Maps only)
    "review_count": None,  # int (Google Maps only)
    "source": "",          # "OpenStreetMap" or "Google Maps"
    "source_url": "",      # link to the listing on its source
    # Filled in by modules.enrichment:
    "email": "",
    "social_media": {},    # platform -> URL, e.g. {"facebook": "https://facebook.com/x"}
    "website_status": "",  # "ok", "no_website", "unreachable", "timeout", "blocked", ...
    # Filled in by modules.filters:
    "lead_score": None,    # 0-100, higher = more services to sell
    "missing_fields": [],  # e.g. ["website", "social_media"]
}


def new_lead(**values) -> dict:
    """Return a lead dict with every field present, filling missing ones with defaults."""
    unknown = set(values) - set(LEAD_FIELDS)
    if unknown:
        raise KeyError(f"Unknown lead fields: {sorted(unknown)}")
    # Copy mutable defaults so leads never share the same dict.
    lead = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in LEAD_FIELDS.items()}
    lead.update({k: v for k, v in values.items() if v is not None})
    return lead
