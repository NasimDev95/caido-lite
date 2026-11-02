#!/usr/bin/env python3
"""Caido Lite: a small intercepting HTTP/HTTPS proxy with a Caido-style web UI.

Run in Termux:
    python main.py                       # proxy :8080, UI http://127.0.0.1:9090
    python main.py --lan                 # let other devices on Wi-Fi use the proxy
    python main.py --export-ca           # copy the root CA to Downloads for Android

Then open http://127.0.0.1:9090 in any browser on the phone.
"""

import argparse
import os
import shutil
import sys
import threading

from certs import CertManager, CertError
from intercept import Interceptor
from proxy import Proxy
from server import serve_ui
from store import Store

DATA_DIR = os.path.join(os.path.expanduser("~"), ".caido-lite")
DOWNLOAD_CANDIDATES = [
    os.path.join(os.path.expanduser("~"), "storage", "downloads"),
    "/sdcard/Download",
]


class App:
    def __init__(self, args):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.args = args
        self.certs = CertManager(os.path.join(DATA_DIR, "ca"))
        self.store = Store(os.path.join(DATA_DIR, "history.db"))
        self.interceptor = Interceptor()
        self.proxy = Proxy(
            self.store,
            self.certs,
            host=args.proxy_host,
            port=args.proxy_port,
            mitm=not args.no_mitm,
            interceptor=self.interceptor,
        )
        self.ui = None
        self._lock = threading.Lock()

    def start_proxy(self):
        with self._lock:
            if not self.proxy.running:
                self.proxy.start()

    def stop_proxy(self):
        with self._lock:
            self.proxy.stop()

    def status(self):
        return {
            "running": self.proxy.running,
            "proxy_host": self.proxy.host,
            "proxy_port": self.proxy.port,
            "mitm": self.proxy.mitm,
            "ui_port": self.args.ui_port,
            "count": self.store.count(),
            "ca_url": "http://caido.lite/ca.crt",
        }

    def start_ui(self):
        self.ui = serve_ui(self, self.args.ui_host, self.args.ui_port)


def export_ca(certs):
    for folder in DOWNLOAD_CANDIDATES:
        if os.path.isdir(folder):
            dest = os.path.join(folder, "caido-lite-ca.crt")
            certs.export_ca(dest)
            return dest
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Caido Lite proxy for Termux")
    parser.add_argument("--proxy-host", default="127.0.0.1", help="proxy bind address")
    parser.add_argument("--proxy-port", type=int, default=8080)
    parser.add_argument("--ui-host", default="127.0.0.1", help="web UI bind address")
    parser.add_argument("--ui-port", type=int, default=9090)
    parser.add_argument("--lan", action="store_true", help="bind proxy to 0.0.0.0")
    parser.add_argument("--no-mitm", action="store_true", help="tunnel HTTPS without decrypting")
    parser.add_argument("--export-ca", action="store_true", help="copy root CA to Downloads and exit")
    parser.add_argument("--no-autostart", action="store_true", help="do not start the proxy at launch")
    args = parser.parse_args(argv)
    if args.lan:
        args.proxy_host = "0.0.0.0"

    try:
        app = App(args)
    except CertError as exc:
        print(f"[!] Certificate setup failed: {exc}")
        return 1

    if args.export_ca:
        dest = export_ca(app.certs)
        if dest:
            print(f"[+] Root CA copied to {dest}")
            print("    Android: Settings > Security > Encryption & credentials > Install a certificate > CA certificate")
        else:
            print(f"[!] No Downloads folder found. Run: termux-setup-storage, then try again.")
            print(f"    CA file is at: {os.path.join(DATA_DIR, 'ca', 'caido-lite-ca.crt')}")
        return 0

    app.start_ui()
    if not args.no_autostart:
        app.start_proxy()

    print("Caido Lite is running")
    print(f"  Web UI : http://{args.ui_host}:{args.ui_port}")
    print(f"  Proxy  : {args.proxy_host}:{args.proxy_port}  (set this in your browser or Wi-Fi settings)")
    print(f"  CA     : {os.path.join(DATA_DIR, 'ca', 'caido-lite-ca.crt')}")
    print("  Install the CA by opening http://caido.lite/ through the proxy, or run --export-ca")
    print("Press Ctrl+C to stop.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        app.stop_proxy()
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
