import os
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

baghdad_tz = timezone(timedelta(hours=3))


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def run_web_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


def background_loop():
    while True:
        now_iq = datetime.now(baghdad_tz).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[ALIVE] Server running in Baghdad time: {now_iq}", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    background_loop()
