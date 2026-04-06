import re


def _scrape_with_page(page, restaurant_name, address):
    """Scrape Uber Eats using a pre-existing Playwright page."""
    try:
        page.goto("https://www.ubereats.com", timeout=30000)
        page.wait_for_timeout(3000)

        page.click('[placeholder="Enter delivery address"]')
        page.wait_for_timeout(1000)
        page.type('[placeholder="Enter delivery address"]', address, delay=50)
        page.wait_for_timeout(2000)

        suggestion = page.query_selector('[data-testid="address-autosuggest-item"]')
        if suggestion:
            suggestion.click()
        else:
            page.keyboard.press("Enter")

        page.wait_for_timeout(3000)

        search = page.query_selector('[placeholder="Search Uber Eats"]')
        if search:
            search.click()
            page.wait_for_timeout(500)
            page.type('[placeholder="Search Uber Eats"]', restaurant_name, delay=50)
            page.keyboard.press("Enter")
            page.wait_for_timeout(4000)

        content = page.content()

        time_match = re.search(r'(\d+)\s*min', content)
        time_text = time_match.group(0) if time_match else "Unknown"

        fee_match = re.search(
            r'\$[\d\.]+\s*delivery fee|\$0 delivery|free delivery',
            content, re.IGNORECASE
        )
        fee_text = fee_match.group(0) if fee_match else "Unknown"

        return {
            "app": "Uber Eats",
            "available": True,
            "delivery_time": time_text,
            "delivery_fee": fee_text,
        }

    except Exception as e:
        return {"app": "Uber Eats", "available": False, "error": str(e)}


def scrape_ubereats(restaurant_name, address):
    """Standalone entry point — launches its own browser (used for local testing)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            return _scrape_with_page(page, restaurant_name, address)
        finally:
            browser.close()


if __name__ == "__main__":
    result = scrape_ubereats("Shake Shack", "New York, NY 10001")
    print(result)
