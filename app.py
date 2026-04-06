import os
import uuid
import resource
import logging
import threading
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template

load_dotenv()
from compare import rank_results

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory job store: {job_id: {"status": "pending"|"done"|"error", "data": ...}}
# Simple dict is safe because gunicorn runs --workers 1 --threads 1.
_jobs = {}

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


def _rss_mb():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / 1024 if os.uname().sysname == 'Linux' else raw / (1024 * 1024)


def _run_scrapers(restaurant, address):
    # Deferred imports so gunicorn workers stay lean at startup.
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
            try:
                for scrape_fn, name in scrape_fns:
                    log.info("MEM before_%s: %.1f MB RSS", name, _rss_mb())
                    results.append(scrape_fn(page, restaurant, address))
                    log.info("MEM after_%s: %.1f MB RSS", name, _rss_mb())
            finally:
                context.close()
        finally:
            browser.close()
            log.info("MEM browser_closed: %.1f MB RSS", _rss_mb())

    return results


def _scrape_job(job_id, restaurant, address, memberships, promos):
    """Runs in a background thread. Stores result in _jobs when done."""
    try:
        scraper_results = _run_scrapers(restaurant, address)
        results, recommendation = rank_results(
            scraper_results,
            memberships=memberships,
            promos=promos,
        )
        _jobs[job_id] = {
            "status": "done",
            "data": {"results": results, "recommendation": recommendation},
        }
        log.info("Job %s done", job_id)
    except Exception as e:
        log.exception("Job %s failed", job_id)
        _jobs[job_id] = {"status": "error", "error": str(e)}


@app.route('/')
def home():
    return render_template(
        'index.html',
        google_maps_api_key=os.environ.get('GOOGLE_MAPS_API_KEY', ''),
    )


@app.route('/compare')
def compare():
    """Starts a scrape job and returns a job_id immediately.
    Responds in <100ms so Render's proxy never times out.
    """
    restaurant = request.args.get('restaurant', 'Shake Shack')
    address    = request.args.get('address', 'New York, NY 10001')

    memberships = []
    if request.args.get('dashpass')     == 'true': memberships.append('dashpass')
    if request.args.get('grubhub_plus') == 'true': memberships.append('grubhub_plus')
    if request.args.get('uber_one')     == 'true': memberships.append('uber_one')

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
    if dd: promos['DoorDash']  = dd
    if gh: promos['Grubhub']   = gh
    if ue: promos['Uber Eats'] = ue

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending"}

    t = threading.Thread(
        target=_scrape_job,
        args=(job_id, restaurant, address, memberships, promos),
        daemon=True,
    )
    t.start()

    return jsonify({"job_id": job_id})


@app.route('/result/<job_id>')
def result(job_id):
    """Polled by the frontend every 2 seconds until status is 'done' or 'error'."""
    job = _jobs.get(job_id)
    if job is None:
        return jsonify({"status": "not_found"}), 404
    if job["status"] == "done":
        # Clean up after delivery so _jobs doesn't grow unbounded.
        _jobs.pop(job_id, None)
        return jsonify({"status": "done", **job["data"]})
    if job["status"] == "error":
        _jobs.pop(job_id, None)
        return jsonify({"status": "error", "error": job.get("error")}), 500
    return jsonify({"status": "pending"})


if __name__ == '__main__':
    app.run(debug=True)
