import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

load_dotenv()
import scrapers.ubereats as _ue
import scrapers.grubhub as _gh
import scrapers.doordash as _dd
from compare import rank_results

app = Flask(__name__)

# Browser launch config — headless=False required for DoorDash (Cloudflare Turnstile
# blocks headless regardless of stealth flags). Uber Eats and Grubhub work fine in
# headed mode too, so all three share one browser instance per request.
_BROWSER_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--window-size=1280,800',
]
_USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


def _run_scrapers(restaurant, address):
    """Launch one browser, run all three scrapers sequentially on separate pages,
    then close the browser. Peak memory = one Chromium process instead of three."""
    results = []
    scrapers = [
        (_ue._scrape_with_page, "Uber Eats"),
        (_gh._scrape_with_page, "Grubhub"),
        (_dd._scrape_with_page, "DoorDash"),
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=_BROWSER_ARGS)
        try:
            for scrape_fn, _ in scrapers:
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport={'width': 1280, 'height': 800},
                    locale='en-US',
                )
                page = context.new_page()
                Stealth().apply_stealth_sync(page)
                try:
                    results.append(scrape_fn(page, restaurant, address))
                finally:
                    context.close()  # closes page + frees context memory
        finally:
            browser.close()
    return results


@app.route('/')
def home():
    return render_template(
        'index.html',
        google_maps_api_key=os.environ.get('GOOGLE_MAPS_API_KEY', ''),
    )

@app.route('/compare')
def compare():
    restaurant = request.args.get('restaurant', 'Shake Shack')
    address = request.args.get('address', 'New York, NY 10001')
    memberships = []
    if request.args.get('dashpass') == 'true':
        memberships.append('dashpass')
    if request.args.get('grubhub_plus') == 'true':
        memberships.append('grubhub_plus')
    if request.args.get('uber_one') == 'true':
        memberships.append('uber_one')

    def _parse_promo(param):
        try:
            val = float(request.args.get(param, 0))
            return val if val > 0 else None
        except ValueError:
            return None

    promos = {}
    dd = _parse_promo('doordash_promo')
    gh = _parse_promo('grubhub_promo')
    ue = _parse_promo('ubereats_promo')
    if dd: promos['DoorDash'] = dd
    if gh: promos['Grubhub'] = gh
    if ue: promos['Uber Eats'] = ue

    scraper_results = _run_scrapers(restaurant, address)
    results, recommendation = rank_results(
        scraper_results,
        memberships=memberships,
        promos=promos,
    )
    return jsonify({
        "results": results,
        "recommendation": recommendation,
    })

if __name__ == '__main__':
    app.run(debug=True)
