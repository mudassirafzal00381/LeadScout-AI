"""Developer test commands for LeadScout AI (run via main.py --test-*).

Each test exercises one stage of the pipeline with fixed example inputs.
The real, user-facing pipeline lives in main.py.
"""

import config  # noqa: F401  (keeps settings loading consistent with main.py)


def print_leads(leads: list[dict]) -> None:
    """Print leads and a short summary."""
    for i, lead in enumerate(leads, 1):
        print(f"{i:>3}. {lead['name']}  [{lead['category'] or '-'}]")
        print(f"     Address : {lead['address'] or '-'}")
        print(f"     Phone   : {lead['phone'] or '-'}")
        print(f"     Website : {lead['website'] or '-'}")
        if lead["rating"] is not None:
            reviews = lead["review_count"]
            print(f"     Rating  : {lead['rating']} "
                  f"({f'{reviews:,} reviews' if reviews is not None else 'review count not shown'})")
        print(f"     Location: {lead['latitude']}, {lead['longitude']}")

    with_phone = sum(1 for lead in leads if lead["phone"])
    with_site = sum(1 for lead in leads if lead["website"])
    print(f"\n{len(leads)} leads found | {with_phone} with phone | "
          f"{with_site} with website | {len(leads) - with_site} need a website")


def test_osm(category: str = "restaurant", location: str = "Lahore, Pakistan",
             max_results: int = 20) -> int:
    """Run collect_from_osm and print the results."""
    from modules.osm_collector import collect_from_osm

    print(f"Searching OpenStreetMap for {category!r} in {location!r}...\n")
    try:
        leads = collect_from_osm(category, location, max_results=max_results)
    except Exception as exc:  # noqa: BLE001
        print(f"OSM collection failed: {exc}")
        return 1
    print_leads(leads)
    return 0 if leads else 1


def test_maps(category: str = "restaurant", location: str = "Lahore, Pakistan",
              max_results: int = 10) -> int:
    """Run collect_from_google_maps and print the results."""
    import logging

    from modules.maps_collector import collect_from_google_maps

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(f"Searching Google Maps for {category!r} in {location!r} "
          f"(max {max_results})...\n")
    leads = collect_from_google_maps(category, location, max_results=max_results)
    print()
    print_leads(leads)
    return 0 if leads else 1


def collect_and_merge(category: str, location: str, osm_max: int = 100,
                      maps_max: int = 20) -> list[dict]:
    """Collect from OSM and Google Maps, then merge/deduplicate (phases 1-3)."""
    from modules.maps_collector import collect_from_google_maps
    from modules.merge import merge_and_deduplicate
    from modules.osm_collector import collect_from_osm

    print(f"Collecting {category!r} in {location!r} from both sources...")
    osm = collect_from_osm(category, location, max_results=osm_max)
    print(f"  OpenStreetMap: {len(osm)} leads")
    maps = collect_from_google_maps(category, location, max_results=maps_max)
    print(f"  Google Maps  : {len(maps)} leads")
    merged = merge_and_deduplicate(osm, maps)
    both = sum(1 for lead in merged if "," in lead["source"])
    print(f"  Merged       : {len(osm) + len(maps)} raw -> {len(merged)} unique "
          f"({both} found in both sources)\n")
    return merged


def test_merge(category: str = "restaurant", location: str = "Lahore, Pakistan") -> int:
    """Collect from both sources, merge them, and print the unified list."""
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    merged = collect_and_merge(category, location)
    print_leads(merged)
    for lead in merged:
        if "," in lead["source"]:
            print(f"  merged: {lead['name']}")
    return 0 if merged else 1


def test_enrich(category: str = "restaurant", location: str = "Lahore, Pakistan") -> int:
    """Collect, merge, enrich with social/contact data, and print sample results."""
    import json
    import logging
    from collections import Counter

    from modules.enrichment import enrich_with_social_and_contact

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("modules.maps_collector", "modules.osm_collector"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    merged = collect_and_merge(category, location)
    print(f"Enriching {sum(1 for b in merged if b['website'])} businesses that have a website...")
    enriched = enrich_with_social_and_contact(merged)

    statuses = Counter(b["website_status"] for b in enriched)
    with_social = sum(1 for b in enriched if b["social_media"])
    with_email = sum(1 for b in enriched if b["email"])
    print(f"\nWebsite status: {dict(statuses)}")
    print(f"{with_social} with social media | {with_email} with email\n")

    # Show the richest businesses as samples.
    samples = sorted(enriched, key=lambda b: (len(b["social_media"]), bool(b["email"])),
                     reverse=True)[:2]
    for business in samples:
        print("Sample enriched business:")
        print(json.dumps(business, indent=2, ensure_ascii=False))
    return 0 if enriched else 1


def test_filter(rules=("no_website",), category: str = "restaurant",
                location: str = "Lahore, Pakistan") -> int:
    """Collect, merge, enrich, then filter by `rules` and print the ranked leads."""
    import logging
    from collections import Counter

    from modules.enrichment import enrich_with_social_and_contact
    from modules.filters import filter_leads

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    merged = collect_and_merge(category, location)
    print(f"Enriching {sum(1 for b in merged if b['website'])} businesses that have a website...")
    enriched = enrich_with_social_and_contact(merged)

    leads = filter_leads(enriched, list(rules))
    print(f"\nrules={list(rules)} -> {len(leads)} of {len(enriched)} businesses match\n")
    print(f"{'Score':>5}  {'Name':<40} {'Phone':<16} Missing")
    for b in leads[:25]:
        print(f"{b['lead_score']:>5}  {b['name'][:40]:<40} {b['phone'][:16] or '-':<16} "
              f"{', '.join(b['missing_fields'])}")
    if len(leads) > 25:
        print(f"  ... and {len(leads) - 25} more")
    print(f"\nScore distribution: {dict(sorted(Counter(b['lead_score'] for b in leads).items(), reverse=True))}")
    return 0 if leads else 1


def test_export(rules=("no_website",), category: str = "restaurant",
                location: str = "Lahore, Pakistan") -> int:
    """Full chain: collect, merge, enrich, filter, then export to Excel."""
    import logging

    from modules.enrichment import enrich_with_social_and_contact
    from modules.excel_export import export_to_excel
    from modules.filters import filter_leads

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    merged = collect_and_merge(category, location)
    print(f"Enriching {sum(1 for b in merged if b['website'])} businesses that have a website...")
    enriched = enrich_with_social_and_contact(merged)
    leads = filter_leads(enriched, list(rules))
    print(f"rules={list(rules)} -> {len(leads)} of {len(enriched)} businesses match")

    path = export_to_excel(leads, category=category, location=location)
    print(f"\nExported {len(leads)} leads to:\n  {path}")
    return 0 if leads else 1


EXAMPLE_REQUESTS = [
    "restaurants in Lahore that need a website",
    "businesses in USA that need better social media presence",
    "salons in Karachi",
    "gyms in Islamabad without a website",
    "Find dental clinics near DHA Phase 5, Lahore with no website",
    "coffee shops in new york that don't have a website or instagram",
    "restaurants and cafes in Dubai with low ratings",
    "hotels in London rated below 3.5",
    "car mechanics in Rawalpindi that need a website and have a phone number",
]


def test_parser() -> int:
    """Parse example requests and print the structured output."""
    import json

    from modules.nlp_parser import parse_user_request

    for text in EXAMPLE_REQUESTS:
        parsed = parse_user_request(text)
        shown = dict(parsed)
        if parsed["category"] == "all":
            shown["categories"] = f"<all {len(parsed['categories'])} from config.DEFAULT_CATEGORIES>"
        print(f"{text!r}\n  -> {json.dumps(shown, ensure_ascii=False)}\n")
    return 0
