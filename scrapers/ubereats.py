import re

# Assumed order subtotal used to evaluate conditional delivery fee thresholds
# (e.g. "Free delivery on orders over $15" → $0.00 with a $20 order).
_DEFAULT_SUBTOTAL = 20.0


def _parse_fee(text):
    """Extract a dollar fee amount from text, evaluating order-minimum conditionals
    against _DEFAULT_SUBTOTAL. Returns a '$X.XX delivery fee' string or None."""
    # Explicit dollar amounts (e.g. "$1.99 delivery fee", "$0.00 Delivery Fee")
    m = re.search(r'\$([\d]+\.[\d]{2})\s*delivery\s*fee', text, re.IGNORECASE)
    if m:
        return f"${float(m.group(1)):.2f} delivery fee"

    # "Free delivery on orders over/above $X" — resolve against default subtotal
    m = re.search(r'free delivery[^$\n]{0,40}\$(\d+(?:\.\d{1,2})?)', text, re.IGNORECASE)
    if m:
        threshold = float(m.group(1))
        return "$0.00 delivery fee" if _DEFAULT_SUBTOTAL >= threshold else None

    # Plain "free delivery" or "$0 delivery"
    if re.search(r'free delivery|\$0 delivery', text, re.IGNORECASE):
        return "$0.00 delivery fee"

    return None


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

        fee_text = _parse_fee(content) or "Unknown"

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
