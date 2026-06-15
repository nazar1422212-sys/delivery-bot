from flask import Flask
from threading import Thread

app = Flask(__name__) # ЭТА СТРОКА ДОЛЖНА БЫТЬ ПЕРВОЙ

@app.route('/', methods=['GET', 'HEAD'])
def home():
    return "Bot is running", 200

def run():
    app.run(host='0.0.0.0', port=8080)

def run_web():
    t = Thread(target=run)
    t.start()
