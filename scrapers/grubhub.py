from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import re


def scrape_grubhub(restaurant_name, address):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            url = (
                "https://www.grubhub.com/search"
                f"?queryText={restaurant_name.replace(' ', '+')}"
                f"&location={address.replace(' ', '+')}"
            )
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)

            # Grubhub shows an address modal on first visit — dismiss it so the
            # address bar in the nav becomes interactive instead.
            try:
                page.click('button[aria-label="Close"]', timeout=3000)
                page.wait_for_timeout(600)
            except Exception:
                pass

            # Set address via the nav address field
            try:
                addr_input = page.wait_for_selector(
                    '[placeholder="Address or zip code"]', timeout=8000
                )
                addr_input.click()
                page.wait_for_timeout(400)
                addr_input.fill('')
                addr_input.type(address, delay=50)
                page.wait_for_timeout(1500)
                page.keyboard.press("Enter")
            except PlaywrightTimeoutError:
                pass  # URL params may have already applied the address

            # Wait for restaurant cards to appear
            try:
                page.wait_for_selector('[class*="restaurantCard"], [data-testid="restaurant-card"], li[class*="restaurant"]', timeout=10000)
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(1500)

            # Delivery time is visible on the search results card
            time_text = "Unknown"
            fee_text = "Unknown"

            content = page.content()
            time_match = re.search(r'(\d+)\s*min', content)
            if time_match:
                time_text = time_match.group(0)

            # Delivery fee is NOT shown on the search results page — only on the
            # individual restaurant page. Click the first result and read it there.
            first_link = page.query_selector(
                'a[href*="/restaurant/"], a[class*="restaurantCard"], '
                '[data-testid="restaurant-card"] a, li[class*="restaurant"] a'
            )
            if first_link:
                first_link.click()
                # Wait for the restaurant page to load — fee info is in the header
                try:
                    page.wait_for_selector(
                        '[class*="restaurantInfo"], [class*="restaurant-info"], '
                        '[data-testid="restaurant-header"], main',
                        timeout=10000
                    )
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(1500)

                restaurant_content = page.content()
                fee_match = re.search(
                    r'\$0\.00 delivery fee'
                    r'|\$0 delivery fee'
                    r'|free delivery'
                    r'|\$[\d]+\.[\d]{2}\s*delivery fee'
                    r'|\$[\d]+\.[\d]{2}\s*Delivery Fee',
                    restaurant_content, re.IGNORECASE
                )
                if fee_match:
                    fee_text = fee_match.group(0)
                else:
                    # Broader fallback: any dollar amount near "delivery"
                    fee_match = re.search(
                        r'delivery(?:\s+fee)?[^$\n]{0,30}\$([\d]+\.[\d]{2})'
                        r'|\$([\d]+\.[\d]{2})[^$\n]{0,30}delivery',
                        restaurant_content, re.IGNORECASE
                    )
                    if fee_match:
                        amount = fee_match.group(1) or fee_match.group(2)
                        fee_text = f"${amount} delivery fee"

            return {
                "app": "Grubhub",
                "available": True,
                "delivery_time": time_text,
                "delivery_fee": fee_text,
            }

        except Exception as e:
            return {
                "app": "Grubhub",
                "available": False,
                "error": str(e),
            }
        finally:
            browser.close()


if __name__ == "__main__":
    result = scrape_grubhub("Shake Shack", "New York, NY 10001")
    print(result)
