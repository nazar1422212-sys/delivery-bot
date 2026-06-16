from flask import Flask
from threading import Thread
import logging

logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/', methods=['GET', 'HEAD'])
def home():
    """Health check endpoint"""
    return "Bot is running", 200

@app.route('/health', methods=['GET'])
def health():
    """Detailed health check"""
    return {"status": "healthy", "service": "delivery-bot"}, 200

def run():
    """Run Flask app"""
    try:
        app.run(host='0.0.0.0', port=8080, debug=False)
    except Exception as e:
        logger.error(f"Error running Flask app: {e}")

def run_web():
    """Start Flask app in a background thread (non-daemon for graceful shutdown)"""
    try:
        t = Thread(target=run, daemon=False)  # daemon=False for graceful shutdown
        t.start()
        logger.info("Keep-alive web server started")
        return t
    except Exception as e:
        logger.error(f"Error starting web server: {e}")
        return None
