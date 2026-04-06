from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import re


def scrape_doordash(restaurant_name, address):
    # PRODUCTION NOTE: DoorDash runs Cloudflare Turnstile which reliably blocks
    # headless Chromium regardless of stealth flags — the check is IP/TLS-level,
    # not just navigator.webdriver. headless=False is the only reliable local fix.
    # For cloud deployment, run under a virtual display:
    #   apt-get install -y xvfb
    #   Xvfb :99 -screen 0 1280x800x24 &
    #   DISPLAY=:99 python app.py
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
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

        try:
            page.goto("https://www.doordash.com", timeout=30000)
            page.wait_for_timeout(4000)

            # Dismiss login/signup modal if present — it overlays the address field.
            # wait_for_selector with state='hidden' first (it sometimes self-dismisses),
            # then forcefully remove the modal node from the DOM if still present.
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

            # Prefer clicking the first autocomplete suggestion; fall back to Enter.
            try:
                suggestion = page.wait_for_selector(
                    '[data-anchor-id="AddressAutoSuggestItem"]', timeout=3000
                )
                suggestion.click()
            except PlaywrightTimeoutError:
                page.keyboard.press("Enter")

            # Search bar appearing confirms address was accepted.
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

            # Click the first autocomplete result; fall back to Enter.
            try:
                first_result = page.wait_for_selector(
                    'li[data-anchor-id="SearchDropdownOption"]', timeout=6000
                )
                first_result.click()
            except PlaywrightTimeoutError:
                page.keyboard.press("Enter")

            # Wait for store cards to render.
            try:
                page.wait_for_selector('[data-anchor-id="StoreCard"]', timeout=12000)
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(1500)

            time_text = "Unknown"
            fee_text  = "Unknown"

            first_card = page.query_selector('[data-anchor-id="StoreCard"]')
            if first_card:
                card_text = first_card.inner_text()
                # Card format: "4.4 (6k+) · 0.4 mi · 24 min"
                # Ratings (4.4) and distances (0.4 mi) never end in "min",
                # so this match is unambiguous within scoped card text.
                # Try separator character first; fall back to plain match in case
                # of encoding differences between headed/headless rendering.
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
                # Fallback: search full page with separator to stay precise.
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
            return {
                "app": "DoorDash",
                "available": False,
                "error": str(e),
            }
        finally:
            browser.close()


if __name__ == "__main__":
    result = scrape_doordash("Shake Shack", "New York, NY 10001")
    print(result)
