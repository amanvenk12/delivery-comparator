from playwright.sync_api import sync_playwright
import re

def scrape_doordash(restaurant_name, address):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        page = context.new_page()
        
        try:
            page.goto("https://www.doordash.com", timeout=30000)
            page.wait_for_timeout(4000)

            # try to close login popup by clicking the X button
            try:
                close = page.query_selector('button[aria-label="Close"]')
                if close:
                    close.click()
                    page.wait_for_timeout(1000)
                else:
                    # click outside the modal to dismiss it
                    page.mouse.click(10, 10)
                    page.wait_for_timeout(1000)
            except:
                pass

            page.click('input[placeholder="Enter delivery address"]')
            page.wait_for_timeout(500)
            page.type('input[placeholder="Enter delivery address"]', address, delay=50)
            page.wait_for_timeout(2000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(4000)

            page.click('input[placeholder="Search DoorDash"]')
            page.wait_for_timeout(500)
            page.type('input[placeholder="Search DoorDash"]', restaurant_name, delay=50)
            page.wait_for_timeout(2000)

            first_result = page.query_selector('li[data-anchor-id="SearchDropdownOption"]')
            if first_result:
                first_result.click()
            else:
                page.keyboard.press("Enter")
            
            page.wait_for_timeout(4000)

            content = page.content()

            time_match = re.search(r'(\d+)\s*min', content)
            time_text = time_match.group(0) if time_match else "Unknown"

            fee_match = re.search(r'\$0 delivery fee|free delivery|\$[\d\.]+ delivery fee', content, re.IGNORECASE)
            fee_text = fee_match.group(0) if fee_match else "Unknown"

            return {
                "app": "DoorDash",
                "available": True,
                "delivery_time": time_text,
                "delivery_fee": fee_text
            }

        except Exception as e:
            return {
                "app": "DoorDash",
                "available": False,
                "error": str(e)
            }
        finally:
            browser.close()

if __name__ == "__main__":
    result = scrape_doordash("Shake Shack", "New York, NY 10001")
    print(result)