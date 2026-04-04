from flask import Flask, jsonify, request
from scrapers.ubereats import scrape_ubereats
from scrapers.grubhub import scrape_grubhub
from scrapers.doordash import scrape_doordash

app = Flask(__name__)

@app.route('/')
def home():
    return 'Delivery Comparator is running!'

@app.route('/compare')
def compare():
    restaurant = request.args.get('restaurant', 'Shake Shack')
    address = request.args.get('address', 'New York, NY 10001')
    ubereats_result = scrape_ubereats(restaurant, address)
    grubhub_result = scrape_grubhub(restaurant, address)
    doordash_result = scrape_doordash(restaurant, address)
    results = [ubereats_result, grubhub_result, doordash_result]
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)
