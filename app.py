import os
import resource
import logging
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template

load_dotenv()
from compare import rank_results

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)


def _rss_mb():
    # Linux reports ru_maxrss in kilobytes; macOS in bytes.
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / 1024 if os.uname().sysname == 'Linux' else raw / (1024 * 1024)

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
    then close the browser. Peak memory = one Chromium process instead of three.

    All heavy imports (playwright, stealth, scrapers) are deferred to inside this
    function so gunicorn workers don't load them at startup — keeping idle RSS low
    and avoiding the OOM kill on Render's 512MB Starter plan.
    """
    # Deferred imports — only loaded when a request actually arrives.
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    import scrapers.ubereats as _ue
    import scrapers.grubhub as _gh
    import scrapers.doordash as _dd

    scrape_fns = [
        (_ue._scrape_with_page, "Uber Eats"),
        (_gh._scrape_with_page, "Grubhub"),
        (_dd._scrape_with_page, "DoorDash"),
    ]

    results = []
    log.info("MEM scrape_start: %.1f MB RSS", _rss_mb())

    with sync_playwright() as p:
        log.info("MEM playwright_init: %.1f MB RSS", _rss_mb())
        browser = p.chromium.launch(headless=False, args=_BROWSER_ARGS)
        log.info("MEM browser_launch: %.1f MB RSS", _rss_mb())
        try:
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={'width': 1280, 'height': 800},
                locale='en-US',
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            log.info("MEM page_ready: %.1f MB RSS", _rss_mb())
            try:
                for scrape_fn, name in scrape_fns:
                    log.info("MEM before_%s: %.1f MB RSS", name, _rss_mb())
                    result = scrape_fn(page, restaurant, address)
                    results.append(result)
                    log.info("MEM after_%s: %.1f MB RSS", name, _rss_mb())
            finally:
                context.close()
                log.info("MEM context_closed: %.1f MB RSS", _rss_mb())
        finally:
            browser.close()
            log.info("MEM browser_closed: %.1f MB RSS", _rss_mb())

    log.info("MEM scrape_done: %.1f MB RSS", _rss_mb())
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
