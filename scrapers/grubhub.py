from playwright.sync_api import sync_playwright
import re

def scrape_grubhub(restaurant_name, address):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            url = f"https://www.grubhub.com/search?queryText={restaurant_name.replace(' ', '+')}&location={address.replace(' ', '+')}"
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)

            page.click('[placeholder="Address or zip code"]')
            page.wait_for_timeout(500)
            page.type('[placeholder="Address or zip code"]', address, delay=50)
            page.wait_for_timeout(2000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(4000)

            content = page.content()

            time_match = re.search(r'(\d+)\s*min', content)
            time_text = time_match.group(0) if time_match else "Unknown"

            fee_match = re.search(r'\$[\d\.]+\s*delivery fee|free delivery|\$0 delivery', content, re.IGNORECASE)
            fee_text = fee_match.group(0) if fee_match else "Unknown"

            return {
                "app": "Grubhub",
                "available": True,
                "delivery_time": time_text,
                "delivery_fee": fee_text
            }

        except Exception as e:
            return {
                "app": "Grubhub",
                "available": False,
                "error": str(e)
            }
        finally:
            browser.close()

if __name__ == "__main__":
    result = scrape_grubhub("Shake Shack", "New York, NY 10001")
    print(result)