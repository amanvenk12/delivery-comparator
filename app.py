import gc
import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template

load_dotenv()
from scrapers.ubereats import scrape_ubereats
from scrapers.grubhub import scrape_grubhub
from scrapers.doordash import scrape_doordash
from compare import rank_results

app = Flask(__name__)

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

    # Run scrapers sequentially and force GC between each one so the
    # Playwright browser process and Python objects are fully released
    # before the next browser launches. Prevents memory spikes on Render.
    ubereats_result = scrape_ubereats(restaurant, address)
    gc.collect()
    grubhub_result = scrape_grubhub(restaurant, address)
    gc.collect()
    doordash_result = scrape_doordash(restaurant, address)
    gc.collect()
    results, recommendation = rank_results(
        [ubereats_result, grubhub_result, doordash_result],
        memberships=memberships,
        promos=promos,
    )
    return jsonify({
        "results": results,
        "recommendation": recommendation,
    })

if __name__ == '__main__':
    app.run(debug=True)
