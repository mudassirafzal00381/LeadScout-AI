"""Enrich leads with social media links and an email address from their website.

For each lead with a website, the homepage is fetched once and scanned for
links to Facebook, Instagram, LinkedIn, Twitter/X, TikTok, YouTube and
WhatsApp, plus a visible email address. Unreachable or blocking sites are
skipped and recorded in "website_status" (useful later: a broken website is
itself a sales lead).
"""

import logging
import random
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

import config

log = logging.getLogger(__name__)
# Detail that belongs in the log file but not on screen (see main.setup_logging).
FILE_ONLY = {"file_only": True}

# platform -> (host regex, path regex a profile link must match)
# Hosts are matched after stripping "www." / "m." / "web.".
SOCIAL_PATTERNS = {
    "facebook": (r"^(facebook\.com|fb\.com|fb\.me)$",
                 r"^/(?!sharer|share|plugins|dialog|tr\b|login|l\.php|2008/)[^/?#]+"),
    "instagram": (r"^instagram\.com$", r"^/(?!p/|reel/|share|explore|accounts)[^/?#]+"),
    "linkedin": (r"^([a-z]{2}\.)?linkedin\.com$", r"^/(company|in|school|showcase)/[^/?#]+"),
    "twitter": (r"^(twitter\.com|x\.com)$",
                r"^/(?!intent|share|home|search|i/)[A-Za-z0-9_]{1,15}/?$"),
    "tiktok": (r"^tiktok\.com$", r"^/@[^/?#]+"),
    "youtube": (r"^youtube\.com$", r"^/(channel/|c/|user/|@)[^/?#]+"),
    "whatsapp": (r"^(wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com)$", r"^/(?!$).*"),
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
# Addresses that are never the business's own contact email.
_EMAIL_BLOCKLIST = re.compile(
    r"(example\.(com|org)|sentry|wixpress\.com|domain\.com|email\.com|yourdomain|"
    r"^(your|my)[._-]?(e?mail|name)@|^(user|username|name|email)@|"  # template placeholders
    r"\.(png|jpe?g|gif|svg|webp|css|js)$)",
    re.IGNORECASE,
)

FREE_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "rocketmail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "icloud.com", "me.com", "aol.com", "proton.me",
    "protonmail.com", "zoho.com", "yandex.com", "gmx.com", "mail.com", "yahoo.co.uk",
    "hotmail.co.uk",
}

_session = requests.Session()
_session.headers.update({
    "User-Agent": config.ENRICHMENT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})


# --- Fetching ----------------------------------------------------------------

def _fetch_html(url: str) -> tuple[str, str]:
    """Return (status, html). status is "ok" or a short reason the page was skipped.

    Connection failures and timeouts are retried once after a short pause:
    small-business hosting is often flaky, and wrongly marking a site as
    broken would inflate its lead score.
    """
    status, html = _fetch_once(url)
    if status in ("unreachable", "timeout"):
        time.sleep(3)
        status, html = _fetch_once(url)
    return status, html


def _fetch_once(url: str) -> tuple[str, str]:
    candidates = [url]
    if url.startswith("https://"):
        candidates.append("http://" + url[len("https://"):])  # some small sites lack HTTPS

    status = "unreachable"
    for candidate in candidates:
        try:
            with _session.get(candidate, timeout=config.REQUEST_TIMEOUT, stream=True,
                              allow_redirects=True) as resp:
                if resp.status_code in (401, 403, 429, 503):
                    return "blocked", ""
                if resp.status_code >= 400:
                    return f"http_{resp.status_code}", ""
                if "html" not in resp.headers.get("Content-Type", "html").lower():
                    return "not_html", ""
                body = b""
                for chunk in resp.iter_content(64_000):
                    body += chunk
                    if len(body) >= config.ENRICHMENT_MAX_PAGE_BYTES:
                        break
                resp.encoding = resp.encoding or resp.apparent_encoding
                return "ok", body.decode(resp.encoding or "utf-8", errors="replace")
        except requests.Timeout:
            status = "timeout"
            log.info("Timeout for %s", candidate, extra=FILE_ONLY)
        except (requests.exceptions.SSLError, requests.ConnectionError) as exc:
            status = "unreachable"  # try the http:// fallback, if any
            log.info("Connection failed for %s: %s", candidate, exc, extra=FILE_ONLY)
        except requests.RequestException as exc:
            log.debug("Request failed for %s: %s", candidate, exc)
            status = "error"
    return status, ""


# --- Extraction --------------------------------------------------------------

def _match_platform(url: str) -> str | None:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    host = re.sub(r"^(www|m|web)\.", "", (parts.hostname or "").lower())
    for platform, (host_re, path_re) in SOCIAL_PATTERNS.items():
        if re.search(host_re, host) and re.match(path_re, parts.path or "/"):
            return platform
    return None


def _whatsapp_link(phone: str) -> str:
    """Return https://wa.me/<digits>, or "" for missing/placeholder numbers."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 8 or re.search(r"0{6,}$", digits) or len(set(digits[-7:])) == 1:
        return ""  # e.g. template numbers like 923000000000
    return f"https://wa.me/{digits}"


def _clean_social_url(url: str, platform: str) -> str:
    parts = urllib.parse.urlsplit(url)
    host = re.sub(r"^(m|web)\.", "www.", (parts.hostname or "").lower())
    if platform == "whatsapp":
        if host == "chat.whatsapp.com":  # group invite link
            return urllib.parse.urlunsplit(("https", host, parts.path.rstrip("/"), "", ""))
        # wa.me/<phone> or api.whatsapp.com/send?phone=<phone>; drop pre-filled messages.
        phone = urllib.parse.parse_qs(parts.query).get("phone", [""])[0] or parts.path
        return _whatsapp_link(phone)
    # Other platforms drop tracking query strings.
    return urllib.parse.urlunsplit(("https", host, parts.path.rstrip("/"), "", ""))


def extract_social_links(soup: BeautifulSoup, html: str, base_url: str) -> dict:
    """Return {platform: url} for the first profile link found per platform."""
    found: dict[str, str] = {}
    hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]
    # Links injected by scripts/widgets only appear in the raw HTML.
    # (JSON inside scripts often escapes slashes as "\/".)
    hrefs += re.findall(r"https?://[^\s\"'<>\\)]+", html.replace("\\/", "/"))
    for href in hrefs:
        href = href.strip()
        if href.startswith("whatsapp://send"):
            phone = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("phone", [""])[0]
            link = _whatsapp_link(phone)
            if link and "whatsapp" not in found:
                found["whatsapp"] = link
            continue
        url = urllib.parse.urljoin(base_url, href)
        platform = _match_platform(url)
        if platform and platform not in found:
            cleaned = _clean_social_url(url, platform)
            if cleaned:
                found[platform] = cleaned
    return found


def _decode_cfemail(encoded: str) -> str:
    """Decode Cloudflare's email obfuscation (data-cfemail="...")."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except ValueError:
        return ""


def _theme_names(soup: BeautifulSoup) -> set[str]:
    """WordPress theme folder names used by the page, e.g. {"hadkaur"}.

    Sites built from a theme sometimes still show the theme's demo email
    (info@<themename>.com); those addresses belong to the theme, not the business.
    """
    names = set()
    for tag in soup.find_all(["link", "script", "img"]):
        src = tag.get("href") or tag.get("src") or ""
        match = re.search(r"/wp-content/themes/([\w-]+)/", src)
        if match:
            names.add(match.group(1).lower().replace("-child", ""))
    return names


def extract_email(soup: BeautifulSoup, website: str) -> str:
    """Return the most likely business email on the page, or ""."""
    themes = _theme_names(soup)
    candidates: list[str] = []
    mailto: set[str] = set()
    for a in soup.select('a[href^="mailto:" i]'):
        address = urllib.parse.unquote(a["href"][7:].split("?")[0]).strip()
        candidates.append(address)
        mailto.add(address.lower())
    for tag in soup.select("[data-cfemail]"):
        candidates.append(_decode_cfemail(tag["data-cfemail"]))
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    candidates += EMAIL_RE.findall(soup.get_text(" "))

    valid = []
    for email in candidates:
        email = email.strip().strip(".").lower()
        if not EMAIL_RE.fullmatch(email) or _EMAIL_BLOCKLIST.search(email) or email in valid:
            continue
        if email.split("@")[1].split(".")[0] in themes:
            continue  # the website theme's demo address
        valid.append(email)
    if not valid:
        return ""
    # Prefer an address on the business's own domain, then a free-mail address.
    # Other domains seen only in page text are usually the web designer's or the
    # website theme's demo address, so they are accepted only from mailto: links.
    domain = (urllib.parse.urlsplit(website).hostname or "").lower().removeprefix("www.")
    site_label = domain.split(".")[0]

    def related(email: str) -> bool:
        # e.g. site poethospitalitygroup.com, email @poethospitality.com
        label = email.split("@")[1].split(".")[0]
        return len(label) >= 4 and len(site_label) >= 4 and (label in site_label or site_label in label)

    same_domain = [e for e in valid if domain and e.split("@")[1].endswith(domain)]
    related_domain = [e for e in valid if related(e)]
    free_mail = [e for e in valid if e.split("@")[1] in FREE_MAIL_DOMAINS]
    linked = [e for e in valid if e in mailto]
    return (same_domain or related_domain or free_mail or linked or [""])[0]


# --- Public API --------------------------------------------------------------

def enrich_with_social_and_contact(business_list: list[dict]) -> list[dict]:
    """Add "social_media", "email" and "website_status" to each business.

    Businesses are updated in place and the same list is returned. A site
    that is unreachable, times out or blocks scraping is skipped, never fatal.
    """
    to_fetch = {b["website"].strip() for b in business_list
                if (b.get("website") or "").strip() and not _match_platform(b["website"])}
    cache: dict[str, tuple[str, dict, str]] = {}  # website -> (status, social, email)

    for business in business_list:
        business.setdefault("social_media", {})
        business.setdefault("email", "")
        website = (business.get("website") or "").strip()
        if not website:
            business["website_status"] = "no_website"
            continue

        # The "website" is sometimes just a social profile (e.g. a Facebook page).
        platform = _match_platform(website)
        if platform:
            cleaned = _clean_social_url(website, platform)
            if cleaned:
                business["social_media"].setdefault(platform, cleaned)
            business["website_status"] = "social_only"
            continue

        if website not in cache:  # several branches often share one website
            if cache:
                low = config.ENRICHMENT_REQUEST_DELAY
                time.sleep(random.uniform(low, low * 1.5))
            cache[website] = _enrich_one(website, len(cache) + 1, len(to_fetch))
        status, social, email = cache[website]
        business["website_status"] = status
        for name, url in social.items():
            business["social_media"].setdefault(name, url)
        business["email"] = business["email"] or email
    return business_list


def _enrich_one(website: str, index: int, total: int) -> tuple[str, dict, str]:
    """Fetch one website and return (status, social_media, email). Never raises."""
    try:
        status, html = _fetch_html(website)
        if status != "ok":
            log.info("  [%d/%d] %s: skipped (%s)", index, total, website, status)
            return status, {}, ""
        soup = BeautifulSoup(html, "html.parser")
        social = extract_social_links(soup, html, website)
        email = extract_email(soup, website)
        log.info("  [%d/%d] %s: %d social, email=%s", index, total, website,
                 len(social), email or "-")
        return "ok", social, email
    except Exception as exc:  # noqa: BLE001 - one bad site must not stop the run
        log.warning("  [%d/%d] %s: failed (%s)", index, total, website, exc)
        return "error", {}, ""
