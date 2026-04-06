from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
import re


def _scrape_with_page(page, restaurant_name, address):
    """Scrape DoorDash using a pre-existing Playwright page."""
    try:
        page.goto("https://www.doordash.com", timeout=30000)
        page.wait_for_timeout(4000)

        content = page.content()
        if 'Verify you are human' in content or 'security verification' in content.lower():
            return {
                "app": "DoorDash",
                "available": False,
                "error": "Bot detection triggered — try again or use a residential proxy.",
            }

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

        # Search for the restaurant
        page.click('input[placeholder="Search DoorDash"]')
        page.wait_for_timeout(400)
        page.type('input[placeholder="Search DoorDash"]', restaurant_name, delay=50)

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

        time_text = "Unknown"
        fee_text = "Unknown"

        first_card = page.query_selector('[data-anchor-id="StoreCard"]')
        if first_card:
            card_text = first_card.inner_text()
            time_match = (
                re.search(r'[·•]\s*(\d+)\s*min', card_text) or
                re.search(r'\b(\d+)\s*min\b', card_text)
            )
            if time_match:
                time_text = time_match.group(1) + " min"
            fee_match = re.search(
                r'\$0 delivery fee|free delivery|\$[\d\.]+ delivery fee',
                card_text, re.IGNORECASE
            )
            if fee_match:
                fee_text = fee_match.group(0)
        else:
            content = page.content()
            time_match = re.search(r'[·•]\s*(\d+)\s*min', content)
            if time_match:
                time_text = time_match.group(1) + " min"
            fee_match = re.search(
                r'\$0 delivery fee|free delivery|\$[\d\.]+ delivery fee',
                content, re.IGNORECASE
            )
            if fee_match:
                fee_text = fee_match.group(0)

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
