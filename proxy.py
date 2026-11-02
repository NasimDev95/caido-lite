"""HTTP/HTTPS intercepting proxy core (pure standard library).

- Plain HTTP requests are forwarded and recorded.
- CONNECT tunnels are man-in-the-middled: the client sees a certificate signed by
  the Caido Lite root CA, the decrypted request is forwarded to the real server
  over verified TLS, and the exchange is recorded.
- While Intercept is on, requests are held (see intercept.py) until the user
  forwards them, optionally edited, or drops them.
"""

import gzip
import http.client
import socket
import socketserver
import ssl
import threading
import time
import zlib

from certs import CertError
from intercept import Interceptor

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-connection", "proxy-authenticate",
    "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade",
}
MAX_BODY = 25 * 1024 * 1024
CA_HOSTS = {"caido.lite", "caido-lite.local"}


class Request:
    __slots__ = ("method", "target", "version", "headers", "body")

    def __init__(self, method, target, version, headers, body):
        self.method = method
        self.target = target
        self.version = version
        self.headers = headers
        self.body = body

    def header(self, name, default=None):
        name = name.lower()
        for k, v in self.headers:
            if k.lower() == name:
                return v
        return default


def read_line(rfile):
    line = rfile.readline(65537)
    if len(line) > 65536:
        raise ValueError("line too long")
    return line


def read_headers(rfile):
    headers = []
    while True:
        line = read_line(rfile)
        if line in (b"", b"\r\n", b"\n"):
            return headers
        text = line.decode("latin-1").rstrip("\r\n")
        if ":" not in text:
            continue
        name, value = text.split(":", 1)
        headers.append((name.strip(), value.strip()))


def read_chunked(rfile):
    out = bytearray()
    while True:
        size_line = read_line(rfile).strip()
        if not size_line:
            continue
        size = int(size_line.split(b";", 1)[0], 16)
        if size == 0:
            while read_line(rfile) not in (b"", b"\r\n", b"\n"):
                pass
            break
        out += rfile.read(size)
        read_line(rfile)
        if len(out) > MAX_BODY:
            raise ValueError("body too large")
    return bytes(out)


def read_body(rfile, headers):
    te = ""
    length = None
    for k, v in headers:
        lk = k.lower()
        if lk == "transfer-encoding":
            te = v.lower()
        elif lk == "content-length":
            try:
                length = int(v)
            except ValueError:
                length = None
    if "chunked" in te:
        return read_chunked(rfile)
    if length is not None:
        if length > MAX_BODY:
            raise ValueError("body too large")
        return rfile.read(length) if length else b""
    return b""


def read_request(rfile):
    while True:
        line = read_line(rfile)
        if line == b"":
            return None
        if line.strip():
            break
    parts = line.decode("latin-1").strip().split(" ", 2)
    if len(parts) != 3:
        raise ValueError("bad request line")
    method, target, version = parts
    headers = read_headers(rfile)
    body = read_body(rfile, headers)
    return Request(method, target, version, headers, body)


def split_target(req, default_scheme):
    """Return (scheme, host, port, path) for a request, from absolute or origin-form."""
    target = req.target
    scheme = default_scheme
    if target.lower().startswith(("http://", "https://")):
        scheme, rest = target.split("://", 1)
        scheme = scheme.lower()
        hostport, _, path = rest.partition("/")
        path = "/" + path
    else:
        hostport = req.header("Host", "")
        path = target
    default_port = 443 if scheme == "https" else 80
    host, port = hostport, default_port
    if hostport.startswith("["):
        end = hostport.find("]")
        host = hostport[: end + 1]
        if hostport[end + 1:].startswith(":"):
            port = int(hostport[end + 2:])
    elif ":" in hostport:
        host, p = hostport.rsplit(":", 1)
        port = int(p)
    return scheme, host, port, path


def build_url(scheme, host, port, path):
    if path.lower().startswith(("http://", "https://")):
        return path
    default = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    return f"{scheme}://{host}{'' if default else ':' + str(port)}{path}"


def decode_body(body, headers):
    """Decode gzip/deflate for display only. The stored bytes stay untouched."""
    enc = ""
    for k, v in headers:
        if k.lower() == "content-encoding":
            enc = v.lower().strip()
    try:
        if enc == "gzip":
            return gzip.decompress(body)
        if enc == "deflate":
            try:
                return zlib.decompress(body)
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS)
    except Exception:
        pass
    return body


class Proxy:
    """Owns the listening socket, the certificate manager, the history store and interception."""

    def __init__(self, store, certs, host="127.0.0.1", port=8080, mitm=True, interceptor=None):
        self.store = store
        self.certs = certs
        self.host = host
        self.port = port
        self.mitm = mitm
        self.interceptor = interceptor or Interceptor()
        self._server = None
        self._thread = None

    def start(self):
        server = _ThreadedServer((self.host, self.port), _Handler)
        server.proxy = self
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def running(self):
        return self._server is not None

    # ----- upstream -------------------------------------------------------

    def send_upstream(self, scheme, host, port, method, path, headers, body):
        """Forward one request over verified TLS (or plain HTTP) and return the response."""
        if scheme == "https":
            conn = http.client.HTTPSConnection(
                host, port, timeout=30, context=ssl.create_default_context()
            )
        else:
            conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            has_host = False
            for k, v in headers:
                lk = k.lower()
                if lk in HOP_BY_HOP or lk == "content-length":
                    continue
                if lk == "host":
                    has_host = True
                conn.putheader(k, v)
            if not has_host:
                conn.putheader("Host", host if port in (80, 443) else f"{host}:{port}")
            if body or method.upper() in ("POST", "PUT", "PATCH"):
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body or None)
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, resp.reason, resp.getheaders(), data
        finally:
            conn.close()

    def replay(self, scheme, host, port, method, path, headers, body):
        """Send a request built by the UI (Replay tab) and record it as a replay."""
        started = time.time()
        tx_id = self.store.start(
            method=method, scheme=scheme, host=host, port=port, path=path,
            url=build_url(scheme, host, port, path),
            req_headers=[list(h) for h in headers], req_body=body, source="replay",
        )
        try:
            status, reason, rh, rb = self.send_upstream(scheme, host, port, method, path, headers, body)
            self.store.finish(
                tx_id, status=status, reason=reason, resp_headers=rh, resp_body=rb,
                duration_ms=(time.time() - started) * 1000,
            )
            return tx_id
        except Exception as exc:
            self.store.fail(tx_id, str(exc), (time.time() - started) * 1000)
            raise


class _ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _Handler(socketserver.BaseRequestHandler):
    proxy: Proxy

    def handle(self):
        self.proxy = self.server.proxy
        self.request.settimeout(60)
        rfile = self.request.makefile("rb")
        try:
            req = read_request(rfile)
            if req is None:
                return
            if req.method.upper() == "CONNECT":
                self._connect(req, rfile)
            else:
                self._loop(rfile, self.request, "http", None, None, first=req)
        except (ValueError, OSError):
            pass
        finally:
            try:
                rfile.close()
            except OSError:
                pass

    def _connect(self, req, rfile):
        host, _, port_s = req.target.rpartition(":")
        port = int(port_s or 443)
        if not self.proxy.mitm:
            self._tunnel(host, port)
            return
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        try:
            ctx = self.proxy.certs.server_context(host)
        except CertError:
            self._tunnel(host, port)
            return
        try:
            tls = ctx.wrap_socket(self.request, server_side=True)
        except (ssl.SSLError, OSError):
            # Client rejected our certificate (CA not installed, or app pinning).
            return
        tls_rfile = tls.makefile("rb")
        try:
            self._loop(tls_rfile, tls, "https", host, port)
        finally:
            tls_rfile.close()

    def _tunnel(self, host, port):
        try:
            upstream = socket.create_connection((host, port), timeout=30)
        except OSError:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        _pipe(self.request, upstream)

    def _loop(self, rfile, client, scheme, host, port, first=None):
        while True:
            req = first or read_request(rfile)
            first = None
            if req is None:
                return
            close = (req.header("Connection", "") or "").lower() == "close"
            keep = self._serve(req, client, scheme, host, port)
            if close or not keep:
                return

    def _serve(self, req, client, scheme, host, port):
        """Handle one request. Returns False when the connection should be closed."""
        if host is None:
            scheme, host, port, path = split_target(req, "http")
        else:
            path = req.target
        host_l = (host or "").lower()

        if host_l in CA_HOSTS and path.split("?", 1)[0] in ("/", "/ca.crt", "/ca.pem"):
            return self._send_ca(client, path)

        method, headers, body = req.method, req.headers, req.body
        url = build_url(scheme, host, port, path)

        held = self.proxy.interceptor.hold(method, scheme, host, port, path, url, headers, body)
        if held is not None:
            self.proxy.interceptor.wait(held)
            if held.action == "drop":
                self._record_dropped(method, scheme, host, port, path, url, headers, body)
                return False
            if held.override is not None:
                method, path, headers, body = held.override
                url = build_url(scheme, host, port, path)

        started = time.time()
        store = self.proxy.store
        tx_id = store.start(
            method=method, scheme=scheme, host=host, port=port, path=path, url=url,
            req_headers=[list(h) for h in headers], req_body=body,
            source="intercept" if held is not None else "proxy",
        )
        try:
            status, reason, rh, rb = self.proxy.send_upstream(
                scheme, host, port, method, path, headers, body
            )
        except Exception as exc:
            store.fail(tx_id, str(exc), (time.time() - started) * 1000)
            msg = f"Upstream error: {exc}".encode()
            client.sendall(
                b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n"
                b"Content-Length: " + str(len(msg)).encode() + b"\r\nConnection: close\r\n\r\n" + msg
            )
            return False

        store.finish(
            tx_id, status=status, reason=reason, resp_headers=rh, resp_body=rb,
            duration_ms=(time.time() - started) * 1000,
        )
        out = [f"HTTP/1.1 {status} {reason}\r\n"]
        for k, v in rh:
            if k.lower() in HOP_BY_HOP or k.lower() == "content-length":
                continue
            out.append(f"{k}: {v}\r\n")
        out.append(f"Content-Length: {len(rb)}\r\n\r\n")
        client.sendall("".join(out).encode("latin-1", "replace") + rb)
        return True

    def _record_dropped(self, method, scheme, host, port, path, url, headers, body):
        store = self.proxy.store
        tx_id = store.start(
            method=method, scheme=scheme, host=host, port=port, path=path, url=url,
            req_headers=[list(h) for h in headers], req_body=body, source="intercept",
        )
        store.fail(tx_id, "Dropped in Intercept", 0)

    def _send_ca(self, client, path):
        if path.split("?", 1)[0] == "/":
            body = (
                b"<!doctype html><meta charset=utf-8><title>Caido Lite</title>"
                b"<h1>Caido Lite CA</h1><p><a href='/ca.crt'>Download root certificate</a></p>"
            )
            ctype = b"text/html; charset=utf-8"
        else:
            body = self.proxy.certs.ca_pem()
            ctype = b"application/x-x509-ca-cert"
        client.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: " + ctype +
            b"\r\nContent-Length: " + str(len(body)).encode() +
            b"\r\nConnection: close\r\n\r\n" + body
        )
        return False


def _pipe(a, b):
    def pump(src, dst):
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    t = threading.Thread(target=pump, args=(b, a), daemon=True)
    t.start()
    pump(a, b)
    t.join(5)
