from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return 'Delivery Comparator is running!'

@app.route('/compare')
def compare():
    return 'Compare endpoint ready!'

if __name__ == '__main__':
    app.run(debug=True)