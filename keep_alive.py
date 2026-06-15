from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

# В вашем файле keep_alive.py добавьте поддержку HEAD:
@app.route('/', methods=['GET', 'HEAD'])
def home():
    return "Bot is running", 200

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_web():
    server = HTTPServer(("0.0.0.0", 10000), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
