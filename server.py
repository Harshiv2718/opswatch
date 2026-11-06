"""Serve the OpsWatch historical evaluation locally; no external dependencies."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
ARTIFACTS = ROOT / "artifacts"
STATIC = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/app.js": "app.js", "/data.js": "data.js"}


class Handler(BaseHTTPRequestHandler):
    def send_body(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/api/report", "/api/events"):
            file = ARTIFACTS / ("report.json" if path.endswith("report") else "events.json")
            if file.is_file():
                try:
                    body = file.read_bytes()
                    json.loads(body)
                except (OSError, ValueError):
                    return self.send_body(500, b'{"error":"Evaluation artifact is unreadable."}', "application/json; charset=utf-8")
            else:
                body = json.dumps({"status": "not_ready", "events": [], "message": "No evaluation artifacts yet. Run the training pipeline first."}).encode()
            return self.send_body(200, body, "application/json; charset=utf-8")
        filename = STATIC.get(path)
        file = WEB / filename if filename else None
        if file is None or not file.is_file():
            return self.send_body(404, b"Not found", "text/plain; charset=utf-8")
        mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        return self.send_body(200, file.read_bytes(), mime + "; charset=utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OpsWatch at http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
