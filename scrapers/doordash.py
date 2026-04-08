import re
import logging
import os
import requests
from urllib.parse import quote_plus

log = logging.getLogger(__name__)

# Assumed order subtotal used to evaluate conditional delivery fee thresholds.
_DEFAULT_SUBTOTAL = 20.0


def _parse_fee(text):
    """Extract a dollar fee amount from text, evaluating order-minimum conditionals
    against _DEFAULT_SUBTOTAL. Returns a '$X.XX delivery fee' string or None."""
    m = re.search(r'\$([\d]+\.[\d]{2})\s*delivery\s*fee', text, re.IGNORECASE)
    if m:
        return f"${float(m.group(1)):.2f} delivery fee"

    m = re.search(r'free delivery[^$\n]{0,40}\$(\d+(?:\.\d{1,2})?)', text, re.IGNORECASE)
    if m:
        threshold = float(m.group(1))
        return "$0.00 delivery fee" if _DEFAULT_SUBTOTAL >= threshold else None

    if re.search(r'free delivery|\$0 delivery', text, re.IGNORECASE):
        return "$0.00 delivery fee"

    return None

_DEBUG_SCREENSHOT_PATH = "/tmp/doordash_cloud_debug.png"


def _screenshot(page, path, label):
    try:
        page.screenshot(path=path)
        log.info("DoorDash debug screenshot saved: %s (%s)", path, label)
    except Exception as e:
        log.warning("DoorDash screenshot failed (%s): %s", label, e)


def _scrape_via_scrapingbee(restaurant_name, address):
    """Fallback when Playwright is bot-blocked: fetch via ScrapingBee API."""
    api_key = os.environ.get('SCRAPINGBEE_API_KEY', '')
    if not api_key:
        log.warning("DoorDash ScrapingBee fallback: SCRAPINGBEE_API_KEY not set")
        return {"app": "DoorDash", "available": False, "error": "Bot-blocked and no SCRAPINGBEE_API_KEY set."}

    # Build the DoorDash search URL — restaurant name only, no address
    search_url = "https://www.doordash.com/search/store/" + quote_plus(restaurant_name) + "/"
    params = {
        "api_key": api_key,
        "url": search_url,
        "render_js": "true",
        "premium_proxy": "true",
        "country_code": "us",
        "wait": "3000",  # ms — let JS render store cards
    }

    log.info("DoorDash ScrapingBee fallback: fetching %s", search_url)
    try:
        resp = requests.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=60)
        log.info("DoorDash ScrapingBee status: %d", resp.status_code)
        if resp.status_code != 200:
            return {"app": "DoorDash", "available": False, "error": f"ScrapingBee returned HTTP {resp.status_code}"}
    except requests.RequestException as e:
        return {"app": "DoorDash", "available": False, "error": f"ScrapingBee request failed: {e}"}

    html = resp.text
    log.info("DoorDash ScrapingBee HTML preview: %r", html[:500])

    time_text = "Unknown"
    fee_text = "Unknown"

    time_match = (
        re.search(r'[·•]\s*(\d+)\s*min', html) or
        re.search(r'"deliveryTime[^"]*"[^:]*:\s*"?(\d+)', html) or
        re.search(r'\b(\d+)\s*min\b', html)
    )
    if time_match:
        time_text = time_match.group(1) + " min"

    fee_text = _parse_fee(html) or fee_text
    if fee_text == "Unknown":
        # Try JSON delivery fee field as last resort
        m = re.search(r'"deliveryFee[^"]*"[^:]*:\s*"?([\d\.]+)"?', html)
        if m:
            fee_text = f"${float(m.group(1)):.2f} delivery fee"

    log.info("DoorDash ScrapingBee extracted — time: %r, fee: %r", time_text, fee_text)
    return {
        "app": "DoorDash",
        "available": True,
        "delivery_time": time_text,
        "delivery_fee": fee_text,
        "via_fallback": True,
    }


def _scrape_with_page(page, restaurant_name, address):
    """Scrape DoorDash using a pre-existing Playwright page."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    try:
        page.goto("https://www.doordash.com", timeout=30000)
        page.wait_for_timeout(4000)

        content = page.content()
        if 'Verify you are human' in content or 'security verification' in content.lower():
            _screenshot(page, _DEBUG_SCREENSHOT_PATH, "bot_blocked")
            log.info("DoorDash bot-blocked — trying ScrapingBee fallback")
            return _scrape_via_scrapingbee(restaurant_name, address)

        # Dismiss login/signup modal if present
        try:
            page.wait_for_selector(
                '[data-testid="identity-iframe"]', state='hidden', timeout=3000
            )
        except Exception:
            page.evaluate(
                'document.querySelector("[data-testid=\'LAYER-MANAGER-MODAL\']")?.remove()'
            )
            page.wait_for_timeout(400)

        # Enter delivery address
        try:
            addr_input = page.wait_for_selector(
                'input[placeholder="Enter delivery address"]', timeout=10000
            )
        except PlaywrightTimeoutError:
            return {"app": "DoorDash", "available": False, "error": "Address field not found."}

        addr_input.click()
        page.wait_for_timeout(400)
        addr_input.type(address, delay=50)
        page.wait_for_timeout(2000)

        try:
            suggestion = page.wait_for_selector(
                '[data-anchor-id="AddressAutoSuggestItem"]', timeout=3000
            )
            suggestion.click()
        except PlaywrightTimeoutError:
            page.keyboard.press("Enter")

        try:
            page.wait_for_selector(
                'input[placeholder="Search DoorDash"]', timeout=12000
            )
        except PlaywrightTimeoutError:
            return {
                "app": "DoorDash",
                "available": False,
                "error": "Address not accepted — search bar never appeared.",
            }

        page.wait_for_timeout(800)

        # Search for the restaurant — use fill() to clear any pre-filled
        # address text before typing, since type() appends to existing content.
        page.click('input[placeholder="Search DoorDash"]')
        page.wait_for_timeout(400)
        page.fill('input[placeholder="Search DoorDash"]', restaurant_name)

        try:
            first_result = page.wait_for_selector(
                'li[data-anchor-id="SearchDropdownOption"]', timeout=6000
            )
            first_result.click()
        except PlaywrightTimeoutError:
            page.keyboard.press("Enter")

        try:
            page.wait_for_selector('[data-anchor-id="StoreCard"]', timeout=12000)
        except PlaywrightTimeoutError:
            pass

        page.wait_for_timeout(1500)
        _screenshot(page, _DEBUG_SCREENSHOT_PATH, "after_search")

        # Dump page state for debugging
        current_url = page.url
        page_title = page.title()
        all_text = page.inner_text("body")[:500]  # first 500 chars

        log.info(f"DoorDash URL after search: {current_url}")
        log.info(f"DoorDash page title: {page_title}")
        log.info(f"DoorDash body preview: {all_text}")

        # Also dump ALL data-testid attributes present on page
        testids = page.eval_on_selector_all(
            "[data-testid]",
            "els => els.map(e => e.getAttribute('data-testid')).slice(0, 20)"
        )
        log.info(f"DoorDash testids found: {testids}")

        time_text = "Unknown"
        fee_text = "Unknown"

        first_card = page.query_selector('[data-anchor-id="StoreCard"]')
        if first_card:
            card_text = first_card.inner_text()
            log.info("DoorDash first StoreCard text: %r", card_text[:300])
            time_match = (
                re.search(r'[·•]\s*(\d+)\s*min', card_text) or
                re.search(r'\b(\d+)\s*min\b', card_text)
            )
            if time_match:
                time_text = time_match.group(1) + " min"
            fee_text = _parse_fee(card_text) or fee_text
        else:
            log.info("DoorDash: no StoreCard found — falling back to page content search")
            content = page.content()
            time_match = re.search(r'[·•]\s*(\d+)\s*min', content)
            if time_match:
                time_text = time_match.group(1) + " min"
            fee_text = _parse_fee(content) or fee_text

        return {
            "app": "DoorDash",
            "available": True,
            "delivery_time": time_text,
            "delivery_fee": fee_text,
        }

    except Exception as e:
        return {"app": "DoorDash", "available": False, "error": str(e)}


def scrape_doordash(restaurant_name, address):
    """Standalone entry point — launches its own browser (used for local testing).

    PRODUCTION NOTE: DoorDash requires headless=False due to Cloudflare Turnstile.
    In production, run under Xvfb:
        rm -f /tmp/.X99-lock && Xvfb :99 -screen 0 1280x800x24 &
        DISPLAY=:99 python app.py
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--window-size=1280,800',
            ]
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
            locale='en-US',
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        try:
            return _scrape_with_page(page, restaurant_name, address)
        finally:
            browser.close()


if __name__ == "__main__":
    result = scrape_doordash("Shake Shack", "New York, NY 10001")
    print(result)
