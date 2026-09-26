"""Collect business leads from Google Maps using a Playwright-driven browser.

!! IMPORTANT - READ BEFORE USING !!
- This scrapes the public Google Maps website. It is intended for PERSONAL /
  LIGHT USE ONLY (a few searches at a time), not bulk or commercial harvesting.
  Automated access may conflict with Google's Terms of Service.
- It depends on Google's current page structure (HTML attributes such as
  data-item-id, role="feed", aria-labels). Google changes this without notice,
  so this collector MAY BREAK at any time and the selectors below will need
  updating. All selectors are kept together in SELECTORS to make that easy.
- Heavy or rapid use (many searches, large max_results, short delays) may get
  your IP address temporarily blocked or shown CAPTCHAs by Google. Keep
  max_results modest and do not lower config.MAPS_DELAY_RANGE.
- This code does not attempt to solve or bypass CAPTCHAs. If Google shows one,
  collection stops and returns what was gathered so far.
"""

import logging
import random
import re
import time
import urllib.parse

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

import config
from modules.browser import launch_browser
from modules.lead import new_lead

log = logging.getLogger(__name__)

MAPS_SEARCH_URL = "https://www.google.com/maps/search/{query}?hl=en"

# Google Maps page structure as of 2026-09. Update here if Google changes it.
SELECTORS = {
    "feed": 'div[role="feed"]',
    "card_link": 'div[role="feed"] a[href*="/maps/place/"]',
    "end_of_list": "text=You've reached the end of the list",
    "place_panel": 'div[role="main"][aria-label]',
    "name": 'div[role="main"] h1',
    "category": 'button[jsaction*="category"]',
    "address": 'button[data-item-id="address"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "website": 'a[data-item-id="authority"]',
    "rating_block": "div.F7nice",
    "review_count": 'div.F7nice span[aria-label*="review"]',
    "consent_reject": 'button:has-text("Reject all")',
}

_COORDS_RE = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
_STARS_RE = re.compile(r"([\d.]+)\s*stars?\s*([\d,]+)?\s*review", re.IGNORECASE)
# Visible rating text such as "4.3(22,717)" or "4.3\n(22,717)".
_RATING_TEXT_RE = re.compile(r"(\d(?:\.\d)?)\s*\(([\d,]+)\)")
# Note: Google sometimes omits review counts entirely (varies between visits);
# review_count is then None.


class GoogleMapsBlocked(RuntimeError):
    """Google showed a CAPTCHA / "unusual traffic" page before any results were collected."""


def _pause(scale: float = 1.0) -> None:
    """Sleep a random, human-like amount of time to reduce detection risk."""
    low, high = config.MAPS_DELAY_RANGE
    time.sleep(random.uniform(low, high) * scale)


def _to_int(text: str | None) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _to_float(text: str | None) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else None


def _strip_label(label: str | None, prefix: str) -> str:
    """'Address: 12 Main St ' -> '12 Main St'."""
    label = (label or "").strip()
    return label[len(prefix):].strip() if label.lower().startswith(prefix.lower()) else label


def _clean_website(href: str | None) -> str:
    """Unwrap Google redirect links like /url?q=https://example.com&..."""
    if not href:
        return ""
    parsed = urllib.parse.urlparse(href)
    if parsed.path == "/url":
        return urllib.parse.parse_qs(parsed.query).get("q", [href])[0]
    return href


def _coords_from_url(url: str) -> tuple[float | None, float | None]:
    match = _COORDS_RE.search(url or "")
    return (float(match.group(1)), float(match.group(2))) if match else (None, None)


def _text_or_empty(page, selector: str, attr: str | None = None) -> str:
    loc = page.locator(selector).first
    try:
        if loc.count() == 0:
            return ""
        value = loc.get_attribute(attr, timeout=2000) if attr else loc.inner_text(timeout=2000)
        return (value or "").strip()
    except PlaywrightTimeout:
        return ""


def _handle_consent(page) -> None:
    """Dismiss Google's cookie consent page (shown in some regions) choosing 'Reject all'."""
    if "consent.google" not in page.url:
        return
    try:
        page.locator(SELECTORS["consent_reject"]).first.click(timeout=5000)
        page.wait_for_load_state("domcontentloaded")
    except PlaywrightTimeout:
        log.warning("Could not dismiss the Google consent page.")


def _is_blocked(page) -> bool:
    """True if Google is showing a CAPTCHA / unusual-traffic page."""
    return "/sorry/" in page.url or page.locator("text=unusual traffic").count() > 0


def _collect_cards(page, max_results: int) -> list[dict]:
    """Scroll the results panel and return basic info for up to max_results listings."""
    feed = page.locator(SELECTORS["feed"])
    links = page.locator(SELECTORS["card_link"])
    stalled = 0
    while links.count() < max_results and stalled < 3:
        before = links.count()
        feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        _pause(0.8)
        if page.locator(SELECTORS["end_of_list"]).count() > 0:
            break
        stalled = stalled + 1 if links.count() == before else 0

    cards, seen = [], set()
    for link in links.all():
        try:
            href = link.get_attribute("href") or ""
            if not href or href in seen:
                continue
            seen.add(href)
            # The card's star image reads e.g. "4.3 stars 22,717 Reviews".
            stars = link.locator("xpath=..").locator('[role="img"][aria-label*="star"]')
            stars_label = stars.first.get_attribute("aria-label") if stars.count() else ""
            match = _STARS_RE.search(stars_label or "")
            rating = float(match.group(1)) if match else _to_float(stars_label)
            reviews = _to_int(match.group(2)) if match and match.group(2) else None
            if reviews is None:
                text_match = _RATING_TEXT_RE.search(link.locator("xpath=..").inner_text())
                if text_match:
                    rating = rating if rating is not None else float(text_match.group(1))
                    reviews = _to_int(text_match.group(2))
            cards.append({
                "name": (link.get_attribute("aria-label") or "").strip(),
                "url": href,
                "rating": rating,
                "review_count": reviews,
            })
        except Exception as exc:  # noqa: BLE001 - one bad card must not stop the run
            log.warning("Skipping unreadable result card: %s", exc)
        if len(cards) >= max_results:
            break
    return cards


def _scrape_place(page, card: dict, category: str) -> dict:
    """Open a listing and extract its details, falling back to the card's data."""
    page.goto(card["url"], wait_until="domcontentloaded", timeout=config.MAPS_PAGE_TIMEOUT * 1000)
    page.wait_for_selector(SELECTORS["place_panel"], timeout=config.MAPS_PAGE_TIMEOUT * 1000)
    try:  # details load slightly after the panel appears
        page.wait_for_selector(SELECTORS["address"], timeout=4000)
    except PlaywrightTimeout:
        pass

    lat, lng = _coords_from_url(card["url"])
    if lat is None:
        lat, lng = _coords_from_url(page.url)

    rating_text = _text_or_empty(page, SELECTORS["rating_block"])
    rating = _to_float(rating_text.split("\n")[0])
    reviews = _to_int(_text_or_empty(page, SELECTORS["review_count"], "aria-label"))
    if reviews is None:
        text_match = _RATING_TEXT_RE.search(rating_text)
        reviews = _to_int(text_match.group(2)) if text_match else None

    return new_lead(
        name=_text_or_empty(page, SELECTORS["name"]) or card["name"],
        category=_text_or_empty(page, SELECTORS["category"]) or category,
        address=_strip_label(_text_or_empty(page, SELECTORS["address"], "aria-label"), "Address:"),
        phone=_strip_label(_text_or_empty(page, SELECTORS["phone"], "aria-label"), "Phone:"),
        website=_clean_website(_text_or_empty(page, SELECTORS["website"], "href")),
        latitude=lat,
        longitude=lng,
        rating=rating if rating is not None else card["rating"],
        review_count=reviews if reviews is not None else card["review_count"],
        source="Google Maps",
        source_url=card["url"],
    )


def collect_from_google_maps(category: str, location: str, max_results: int = 50) -> list[dict]:
    """Search Google Maps for "{category} in {location}" and return up to max_results leads.

    Returns dicts in the shared format from modules.lead (same as osm_collector).
    Personal/light use only - see the module docstring.
    """
    search_term = category.replace("_", " ")  # "retail_store" -> "retail store"
    query = urllib.parse.quote_plus(f"{search_term} in {location}")
    leads: list[dict] = []
    blocked = False

    with sync_playwright() as p:
        browser, channel = launch_browser(p)
        log.info("Google Maps: using browser %s", channel)
        try:
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(MAPS_SEARCH_URL.format(query=query), wait_until="domcontentloaded",
                      timeout=config.MAPS_PAGE_TIMEOUT * 1000)
            _handle_consent(page)
            if _is_blocked(page):
                blocked = True
                return leads

            try:
                page.wait_for_selector(SELECTORS["feed"], timeout=config.MAPS_PAGE_TIMEOUT * 1000)
                _pause(0.5)
                cards = _collect_cards(page, max_results)
            except PlaywrightTimeout:
                # A very specific query can open a single place instead of a result list.
                if "/maps/place/" in page.url:
                    cards = [{"name": "", "url": page.url, "rating": None, "review_count": None}]
                else:
                    log.error("No Google Maps results found for %r.", f"{category} in {location}")
                    return leads
            log.info("Google Maps: %d listings found, fetching details...", len(cards))

            for i, card in enumerate(cards, 1):
                try:
                    _pause()
                    leads.append(_scrape_place(page, card, category))
                    log.info("  [%d/%d] %s", i, len(cards), leads[-1]["name"])
                except Exception as exc:  # noqa: BLE001 - one failed listing must not stop the run
                    log.warning("  [%d/%d] failed (%s): %s", i, len(cards), card.get("name"),
                                str(exc).splitlines()[0])
                    if _is_blocked(page):
                        blocked = True
                        log.error("Google started blocking requests; stopping early.")
                        break
        except Exception as exc:  # noqa: BLE001 - return partial results instead of crashing
            log.error("Google Maps collection stopped: %s", str(exc).splitlines()[0])
        finally:
            browser.close()
            if blocked and not leads:
                # Raised after cleanup so the caller can show a clear message.
                raise GoogleMapsBlocked(
                    "Google showed a CAPTCHA / unusual-traffic page. This is common on cloud "
                    "servers; try again later, or run LeadScout on your own computer.")

    return leads
