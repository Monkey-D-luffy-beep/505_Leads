"""
Web scraper service using Playwright and BeautifulSoup.
- GoogleMapsScraper: finds small businesses by keyword + location via Google Maps
- scrape_website_meta: extracts structured metadata from a company website
"""
from __future__ import annotations

import re
import time
import random
import asyncio
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright, Page, Browser
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Realistic Chrome User-Agent rotation list ──────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# ── Regex patterns ─────────────────────────────────────────────────────────
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)
PHONE_REGEX = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?\(?\d{2,4}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{3,4}",
)
SOCIAL_DOMAINS = {"facebook.com", "linkedin.com", "instagram.com", "twitter.com", "x.com"}
BOOKING_KEYWORDS = {"book", "schedule", "appointment", "calendly", "acuity"}


# ═══════════════════════════════════════════════════════════════════════════
#  Google Maps Scraper
# ═══════════════════════════════════════════════════════════════════════════


class GoogleMapsScraper:
    """Scrape Google Maps search results using Playwright (headless Chromium)."""

    def __init__(self):
        self._browser: Optional[Browser] = None

    # ── public API ─────────────────────────────────────────────────────────

    async def search(
        self,
        keyword: str,
        location: str,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search Google Maps for *keyword* in *location* and return up to
        *max_results* structured lead dicts.
        """
        leads: List[Dict[str, Any]] = []

        async with async_playwright() as pw:
            self._browser = await pw.chromium.launch(headless=True)
            context = await self._browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = await context.new_page()

            try:
                search_url = (
                    f"https://www.google.com/maps/search/"
                    f"{quote_plus(keyword + ' ' + location)}"
                )
                logger.info("Navigating to %s", search_url)
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

                # ── detect CAPTCHA ──────────────────────────────────────
                if await self._is_captcha(page):
                    logger.warning("CAPTCHA detected — aborting scrape job")
                    return [{"error": "captcha", "message": "Google returned a CAPTCHA page"}]

                # ── wait for feed ───────────────────────────────────────
                feed_sel = "div[role='feed']"
                try:
                    await page.wait_for_selector(feed_sel, timeout=15000)
                except Exception:
                    logger.warning("Results feed not found — possibly no results")
                    return []

                # ── scroll to load results ──────────────────────────────
                await self._scroll_feed(page, feed_sel, max_results)

                # ── collect result links ────────────────────────────────
                cards = await page.query_selector_all(f"{feed_sel} > div > div > a")
                logger.info("Found %d result cards", len(cards))

                for idx, card in enumerate(cards[:max_results]):
                    try:
                        lead = await self._extract_lead(page, card, location)
                        if lead and lead.get("company_name"):
                            leads.append(lead)
                            logger.info(
                                "[%d/%d] Scraped: %s",
                                idx + 1,
                                min(len(cards), max_results),
                                lead["company_name"],
                            )
                    except Exception as exc:
                        logger.error("Error extracting card %d: %s", idx, exc)

                    # anti-detection delay
                    await asyncio.sleep(random.uniform(1.5, 3.5))

            except Exception as exc:
                logger.error("Scraper error: %s", exc)
            finally:
                await self._browser.close()
                self._browser = None

        return leads

    # ── sync variant (Windows-safe, no subprocess) ─────────────────────

    def search_sync(
        self,
        keyword: str,
        location: str,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Synchronous version of search() using playwright.sync_api.
        Safe on Windows where async subprocess exec is not supported.
        Call via ``asyncio.to_thread(scraper.search_sync, ...)`` from async code.
        """
        leads: List[Dict[str, Any]] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = context.new_page()

            try:
                search_url = (
                    f"https://www.google.com/maps/search/"
                    f"{quote_plus(keyword + ' ' + location)}"
                )
                logger.info("Navigating to %s", search_url)
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

                # ── detect CAPTCHA
                url = page.url
                is_captcha = "sorry/index" in url or "google.com/sorry" in url
                if not is_captcha:
                    try:
                        if "unusual traffic" in page.content().lower():
                            is_captcha = True
                    except Exception:
                        pass
                if is_captcha:
                    logger.warning("CAPTCHA detected — aborting")
                    browser.close()
                    return [{"error": "captcha", "message": "Google returned a CAPTCHA page"}]

                # ── wait for feed
                feed_sel = "div[role='feed']"
                try:
                    page.wait_for_selector(feed_sel, timeout=15000)
                except Exception:
                    logger.warning("Results feed not found — possibly no results")
                    browser.close()
                    return []

                # ── scroll to load results
                feed = page.query_selector(feed_sel)
                if feed:
                    last_count = 0
                    stale_rounds = 0
                    for _ in range(30):
                        feed.evaluate("el => el.scrollTop = el.scrollHeight")
                        time.sleep(random.uniform(1.0, 2.0))
                        current_count = feed.evaluate(
                            "el => el.querySelectorAll(':scope > div > div > a').length"
                        )
                        if current_count >= max_results:
                            break
                        if current_count == last_count:
                            stale_rounds += 1
                            if stale_rounds >= 3:
                                end_marker = page.query_selector("span.HlvSq")
                                if end_marker:
                                    break
                                stale_rounds = 0
                        else:
                            stale_rounds = 0
                        last_count = current_count

                # ── collect result links
                cards = page.query_selector_all(f"{feed_sel} > div > div > a")
                logger.info("Found %d result cards", len(cards))

                for idx, card in enumerate(cards[:max_results]):
                    try:
                        lead = self._extract_lead_sync(page, card, location)
                        if lead and lead.get("company_name"):
                            leads.append(lead)
                            logger.info(
                                "[%d/%d] Scraped: %s",
                                idx + 1,
                                min(len(cards), max_results),
                                lead["company_name"],
                            )
                    except Exception as exc:
                        logger.error("Error extracting card %d: %s", idx, exc)

                    time.sleep(random.uniform(1.5, 3.5))

            except Exception as exc:
                logger.error("Scraper error: %s", exc)
            finally:
                browser.close()

        return leads

    def _extract_lead_sync(self, page, card, location: str) -> Optional[Dict[str, Any]]:
        """Sync version of _extract_lead."""
        # Try to get the business name from the card's aria-label before clicking
        card_name = None
        try:
            card_name = card.get_attribute("aria-label")
            if card_name:
                card_name = card_name.strip()
        except Exception:
            pass

        try:
            card.click()
        except Exception:
            return None

        # Wait for the detail panel to load
        try:
            page.wait_for_selector("div[role='main'] h1", timeout=5000)
        except Exception:
            pass
        time.sleep(random.uniform(1.5, 2.5))

        lead: Dict[str, Any] = {
            "company_name": None,
            "website": None,
            "phone": None,
            "address": None,
            "rating": None,
            "review_count": None,
            "category": None,
            "location": location,
            "maps_url": page.url,
        }

        # Extract company name from detail panel h1
        # Target the h1 inside the main content area (not the page-level "Results" h1)
        name_found = False
        for selector in ["div[role='main'] h1", "h1.DUwDvf", "h1"]:
            try:
                el = page.query_selector(selector)
                if el:
                    text = el.inner_text().strip()
                    if text and text.lower() not in ("results", "google maps"):
                        lead["company_name"] = text
                        name_found = True
                        break
            except Exception:
                pass

        # Fall back to card aria-label
        if not name_found and card_name:
            lead["company_name"] = card_name

        try:
            rating_el = page.query_selector("div.F7nice span[aria-hidden='true']")
            if rating_el:
                raw = rating_el.inner_text().strip().replace(",", ".")
                lead["rating"] = float(raw)
        except (ValueError, TypeError):
            pass

        try:
            review_el = page.query_selector("div.F7nice span[aria-label*='review']")
            if review_el:
                label = review_el.get_attribute("aria-label") or ""
                nums = re.findall(r"[\d,]+", label)
                if nums:
                    lead["review_count"] = int(nums[0].replace(",", ""))
        except (ValueError, TypeError):
            pass

        cat_el = page.query_selector("button[jsaction*='category']")
        if cat_el:
            lead["category"] = cat_el.inner_text().strip()

        info_buttons = page.query_selector_all("button[data-item-id], a[data-item-id]")
        for btn in info_buttons:
            data_id = btn.get_attribute("data-item-id") or ""
            aria = btn.get_attribute("aria-label") or ""

            if data_id.startswith("authority"):
                href = btn.get_attribute("href")
                if href:
                    lead["website"] = href
                elif aria:
                    lead["website"] = aria.replace("Website: ", "").strip()
            elif data_id.startswith("phone"):
                lead["phone"] = aria.replace("Phone: ", "").strip() if aria else None
            elif data_id.startswith("address") or "address" in data_id:
                lead["address"] = aria.replace("Address: ", "").strip() if aria else None

        if not lead["website"]:
            website_link = page.query_selector(
                "a[data-value='Website'], a[aria-label*='Website']"
            )
            if website_link:
                lead["website"] = website_link.get_attribute("href")

        return lead

    # ── private helpers ────────────────────────────────────────────────────

    async def _is_captcha(self, page: Page) -> bool:
        """Return True if Google is showing a CAPTCHA / sorry page."""
        url = page.url
        if "sorry/index" in url or "google.com/sorry" in url:
            return True
        # Also check page content for CAPTCHA indicators
        try:
            content = await page.content()
            if "unusual traffic" in content.lower():
                return True
        except Exception:
            pass
        return False

    async def _scroll_feed(
        self, page: Page, feed_selector: str, target: int
    ) -> None:
        """Scroll the results feed until *target* items loaded or end reached."""
        feed = await page.query_selector(feed_selector)
        if not feed:
            return

        last_count = 0
        stale_rounds = 0

        for _ in range(30):  # safety cap
            await feed.evaluate("el => el.scrollTop = el.scrollHeight")
            await asyncio.sleep(random.uniform(1.0, 2.0))

            current_count = await feed.evaluate(
                "el => el.querySelectorAll(':scope > div > div > a').length"
            )

            if current_count >= target:
                break

            if current_count == last_count:
                stale_rounds += 1
                if stale_rounds >= 3:
                    # check for "end of list" marker
                    end_marker = await page.query_selector(
                        "span.HlvSq"  # "You've reached the end of the list"
                    )
                    if end_marker:
                        break
                    stale_rounds = 0  # reset and try a bit more
            else:
                stale_rounds = 0

            last_count = current_count

    async def _extract_lead(
        self, page: Page, card, location: str
    ) -> Optional[Dict[str, Any]]:
        """Click a result card and scrape the detail panel."""
        try:
            await card.click()
        except Exception:
            return None

        await asyncio.sleep(random.uniform(1.5, 2.5))

        lead: Dict[str, Any] = {
            "company_name": None,
            "website": None,
            "phone": None,
            "address": None,
            "rating": None,
            "review_count": None,
            "category": None,
            "location": location,
            "maps_url": page.url,
        }

        # ── company name (h1) ──────────────────────────────────────────
        h1 = await page.query_selector("h1")
        if h1:
            lead["company_name"] = (await h1.inner_text()).strip()

        # ── rating ─────────────────────────────────────────────────────
        try:
            rating_el = await page.query_selector("div.F7nice span[aria-hidden='true']")
            if rating_el:
                raw = (await rating_el.inner_text()).strip().replace(",", ".")
                lead["rating"] = float(raw)
        except (ValueError, TypeError):
            pass

        # ── review count ───────────────────────────────────────────────
        try:
            review_el = await page.query_selector("div.F7nice span[aria-label*='review']")
            if review_el:
                label = await review_el.get_attribute("aria-label") or ""
                nums = re.findall(r"[\d,]+", label)
                if nums:
                    lead["review_count"] = int(nums[0].replace(",", ""))
        except (ValueError, TypeError):
            pass

        # ── category ───────────────────────────────────────────────────
        cat_el = await page.query_selector("button[jsaction*='category']")
        if cat_el:
            lead["category"] = (await cat_el.inner_text()).strip()

        # ── info buttons (website, phone, address) ─────────────────────
        info_buttons = await page.query_selector_all(
            "button[data-item-id], a[data-item-id]"
        )
        for btn in info_buttons:
            data_id = await btn.get_attribute("data-item-id") or ""
            aria = await btn.get_attribute("aria-label") or ""

            if data_id.startswith("authority"):
                href = await btn.get_attribute("href")
                if href:
                    lead["website"] = href
                elif aria:
                    # sometimes the website is in the aria-label
                    lead["website"] = aria.replace("Website: ", "").strip()

            elif data_id.startswith("phone"):
                # aria-label is like "Phone: +44 123 456 7890"
                lead["phone"] = aria.replace("Phone: ", "").strip() if aria else None

            elif data_id.startswith("address") or "address" in data_id:
                lead["address"] = aria.replace("Address: ", "").strip() if aria else None

        # If website not found via data-item-id, try generic link approach
        if not lead["website"]:
            website_link = await page.query_selector(
                "a[data-value='Website'], a[aria-label*='Website']"
            )
            if website_link:
                lead["website"] = await website_link.get_attribute("href")

        return lead


# ═══════════════════════════════════════════════════════════════════════════
#  Website Metadata Scraper
# ═══════════════════════════════════════════════════════════════════════════


async def scrape_website_meta(url: str) -> Dict[str, Any]:
    """
    Fetch a company website and extract structured metadata:
    title, description, emails, phones, social links, contact form, booking widget.
    """
    result: Dict[str, Any] = {
        "url": url,
        "title": None,
        "meta_description": None,
        "h1_text": None,
        "email_addresses": [],
        "phone_numbers": [],
        "social_links": [],
        "has_contact_form": False,
        "has_booking_widget": False,
    }

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=10.0,
            headers={"User-Agent": random.choice(USER_AGENTS)},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        result["error"] = str(exc)
        return result

    soup = BeautifulSoup(html, "html.parser")

    # ── title ──────────────────────────────────────────────────────────
    if soup.title and soup.title.string:
        result["title"] = soup.title.string.strip()

    # ── meta description ───────────────────────────────────────────────
    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta and meta.get("content"):
        result["meta_description"] = meta["content"].strip()

    # ── first H1 ───────────────────────────────────────────────────────
    h1 = soup.find("h1")
    if h1:
        result["h1_text"] = h1.get_text(strip=True)

    # ── visible text for regex extraction ──────────────────────────────
    # Remove script/style tags first
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = soup.get_text(separator=" ", strip=True)

    # ── email addresses ────────────────────────────────────────────────
    # From mailto: links
    mailto_links = soup.find_all("a", href=re.compile(r"^mailto:", re.I))
    for link in mailto_links:
        href = link.get("href", "")
        email = href.replace("mailto:", "").split("?")[0].strip()
        if email and email not in result["email_addresses"]:
            result["email_addresses"].append(email)

    # From visible text via regex
    for match in EMAIL_REGEX.findall(visible_text):
        # Filter out common false positives (image files, etc.)
        if not any(match.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
            if match not in result["email_addresses"]:
                result["email_addresses"].append(match)

    # ── phone numbers ──────────────────────────────────────────────────
    # From tel: links 
    tel_links = soup.find_all("a", href=re.compile(r"^tel:", re.I))
    for link in tel_links:
        href = link.get("href", "")
        phone = href.replace("tel:", "").strip()
        if phone and phone not in result["phone_numbers"]:
            result["phone_numbers"].append(phone)

    # From visible text
    for match in PHONE_REGEX.findall(visible_text):
        cleaned = match.strip()
        # Only keep phone-like strings with at least 7 digits
        digits = re.sub(r"\D", "", cleaned)
        if len(digits) >= 7 and cleaned not in result["phone_numbers"]:
            result["phone_numbers"].append(cleaned)

    # De-duplicate (keep first 10)
    result["phone_numbers"] = result["phone_numbers"][:10]

    # ── social links ───────────────────────────────────────────────────
    all_links = soup.find_all("a", href=True)
    for link in all_links:
        href = link["href"]
        for domain in SOCIAL_DOMAINS:
            if domain in href and href not in result["social_links"]:
                result["social_links"].append(href)
                break

    # ── has_contact_form ───────────────────────────────────────────────
    forms = soup.find_all("form")
    for form in forms:
        email_input = form.find("input", attrs={"type": "email"})
        if email_input:
            result["has_contact_form"] = True
            break
        # also check for name="email" or placeholder containing "email"
        any_email_field = form.find(
            "input",
            attrs={"name": re.compile(r"email", re.I)},
        )
        if any_email_field:
            result["has_contact_form"] = True
            break

    # ── has_booking_widget ─────────────────────────────────────────────
    text_lower = visible_text.lower()
    html_lower = html.lower()
    for kw in BOOKING_KEYWORDS:
        if kw in text_lower or kw in html_lower:
            result["has_booking_widget"] = True
            break

    # Also check for iframe-based booking tools (Calendly, Acuity, etc.)
    iframes = soup.find_all("iframe", src=True)
    for iframe in iframes:
        src = iframe["src"].lower()
        if any(kw in src for kw in ("calendly", "acuity", "booksy", "setmore")):
            result["has_booking_widget"] = True
            break

    return result
