"""Web UI and JSON API for Caido Lite.

Serves the static UI from ./webui and a small API used by the front end:
  GET  /api/status                       proxy state, port, transaction count
  POST /api/proxy                        {"action": "start"|"stop"}
  GET  /api/history?q=&method=&limit=&offset=
  GET  /api/tx/<id>                      full request and response (bodies decoded for display)
  POST /api/replay                       {"raw": "...", "scheme": "https", "host": "...", "port": 443}
  POST /api/clear                        wipe the history
  GET  /api/ca                           root certificate download
  GET  /api/intercept                    intercept state and held requests
  POST /api/intercept                    {"enabled": true|false, "scope": "text"}
  POST /api/intercept/<id>/forward       {"raw": "..."} optional edited request
  POST /api/intercept/<id>/drop
"""

import base64
import json
import mimetypes
import os
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from intercept import parse_raw
from proxy import decode_body

WEBUI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")
MAX_JSON = 30 * 1024 * 1024


def body_for_display(data, headers):
    if data is None:
        return {"encoding": "text", "text": "", "size": 0}
    size = len(data)
    raw = decode_body(data, headers)
    try:
        return {"encoding": "text", "text": raw.decode("utf-8"), "size": size}
    except UnicodeDecodeError:
        return {"encoding": "base64", "text": base64.b64encode(raw).decode(), "size": size}


class UIHandler(BaseHTTPRequestHandler):
    server_version = "CaidoLite/1.1"

    # ----- helpers --------------------------------------------------------

    def log_message(self, fmt, *args):
        pass

    @property
    def app(self):
        return self.server.app

    def _json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > MAX_JSON:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _bytes(self, data, ctype, filename=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _static(self, rel):
        rel = "index.html" if rel in ("", "/") else rel.lstrip("/")
        full = os.path.normpath(os.path.join(WEBUI_DIR, rel))
        if not full.startswith(WEBUI_DIR + os.sep) or not os.path.isfile(full):
            self.send_error(404)
            return
        with open(full, "rb") as fh:
            data = fh.read()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ----- GET ------------------------------------------------------------

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        try:
            if path == "/api/ca":
                return self._bytes(self.app.certs.ca_pem(), "application/x-x509-ca-cert", "caido-lite-ca.crt")
            if path == "/api/status":
                return self._json(self.app.status())
            if path == "/api/intercept":
                return self._json(self.app.interceptor.snapshot())
            if path == "/api/history":
                limit = min(int(qs.get("limit", ["500"])[0]), 2000)
                offset = int(qs.get("offset", ["0"])[0])
                rows = self.app.store.search(
                    query=qs.get("q", [""])[0],
                    method=qs.get("method", [""])[0],
                    limit=limit,
                    offset=offset,
                )
                return self._json({"items": rows, "total": self.app.store.count()})
            m = re.fullmatch(r"/api/tx/(\d+)", path)
            if m:
                tx = self.app.store.get(int(m.group(1)))
                if tx is None:
                    return self._json({"error": "not found"}, 404)
                tx["req_body_view"] = body_for_display(tx.pop("req_body"), tx["req_headers"])
                resp_headers = tx.pop("resp_headers")
                resp_body = tx.pop("resp_body")
                tx["resp_headers"] = resp_headers or []
                tx["resp_body_view"] = body_for_display(resp_body, resp_headers or [])
                return self._json(tx)
            return self._static(path)
        except (ValueError, KeyError) as exc:
            return self._json({"error": str(exc)}, 400)

    # ----- POST -----------------------------------------------------------

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            data = self._read_json()
            if path == "/api/proxy":
                action = data.get("action")
                if action == "start":
                    self.app.start_proxy()
                elif action == "stop":
                    self.app.stop_proxy()
                else:
                    return self._json({"error": "action must be start or stop"}, 400)
                return self._json(self.app.status())
            if path == "/api/replay":
                scheme = data.get("scheme", "https")
                host = data["host"]
                port = int(data.get("port") or (443 if scheme == "https" else 80))
                method, rpath, headers, body = parse_raw(data["raw"])
                tx_id = self.app.proxy.replay(scheme, host, port, method, rpath, headers, body)
                return self._json({"id": tx_id})
            if path == "/api/clear":
                self.app.store.clear()
                return self._json({"ok": True})
            if path == "/api/intercept":
                snap = self.app.interceptor.configure(
                    enabled=data.get("enabled"), scope=data.get("scope")
                )
                return self._json(snap)
            m = re.fullmatch(r"/api/intercept/(\d+)/(forward|drop)", path)
            if m:
                hid, action = int(m.group(1)), m.group(2)
                try:
                    found = self.app.interceptor.decide(hid, action, data.get("raw"))
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                if not found:
                    return self._json({"error": "request is no longer held"}, 404)
                return self._json({"ok": True})
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as exc:
            return self._json({"error": str(exc)}, 400)


class UIServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, app):
        self.app = app
        super().__init__(addr, UIHandler)


def serve_ui(app, host, port):
    httpd = UIServer((host, port), app)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
