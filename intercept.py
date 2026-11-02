"""Request interception: hold requests in a queue until the user forwards or drops them.

Flow:
  1. The proxy calls Interceptor.hold() for every request while interception is on.
  2. The request sits in the queue; its client connection waits.
  3. The UI lists it, the user edits the raw request and clicks Forward or Drop.
  4. Forward sends the (possibly edited) request upstream. Drop closes the connection.
  5. If the user does not answer within HOLD_TIMEOUT seconds, the request is forwarded unchanged.
"""

import threading
import time

HOLD_TIMEOUT = 600  # seconds


def build_raw(method, target, headers, body):
    """Render a request as the text shown in the Intercept editor (HTTP/1.1 wire format)."""
    lines = [f"{method} {target} HTTP/1.1"]
    lines += [f"{k}: {v}" for k, v in headers]
    return "\n".join(lines) + "\n\n" + body.decode("utf-8", "replace")


def parse_raw(raw):
    """Parse edited raw request text back into (method, path, headers, body).

    Raises ValueError with a readable message when the text is malformed.
    """
    text = raw.replace("\r\n", "\n")
    head, _, body = text.partition("\n\n")
    lines = head.split("\n")
    first = lines[0].strip().split(" ")
    if len(first) < 2 or not first[0]:
        raise ValueError("First line must look like: METHOD /path HTTP/1.1")
    method, path = first[0].upper(), first[1]
    headers = []
    for line in lines[1:]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError("Bad header line: " + line[:80])
        k, v = line.split(":", 1)
        headers.append((k.strip(), v.strip()))
    headers = [(k, v) for k, v in headers if k.lower() not in ("content-length", "transfer-encoding")]
    return method, path, headers, body.encode("utf-8")


class Held:
    """One request waiting for a decision."""

    __slots__ = (
        "id", "created", "method", "scheme", "host", "port", "path", "url",
        "raw", "event", "action", "override",
    )

    def __init__(self, hid, method, scheme, host, port, path, url, raw):
        self.id = hid
        self.created = time.time()
        self.method = method
        self.scheme = scheme
        self.host = host
        self.port = port
        self.path = path
        self.url = url
        self.raw = raw
        self.event = threading.Event()
        self.action = None      # "forward", "drop", or None (timed out)
        self.override = None    # (method, path, headers, body) when the user edited the request


class Interceptor:
    def __init__(self, timeout=HOLD_TIMEOUT):
        self.enabled = False
        self.scope = ""
        self.timeout = timeout
        self._lock = threading.Lock()
        self._seq = 0
        self._held = {}

    # ----- state ------------------------------------------------------

    def snapshot(self):
        with self._lock:
            pending = [
                {
                    "id": h.id,
                    "created": h.created,
                    "method": h.method,
                    "scheme": h.scheme,
                    "host": h.host,
                    "port": h.port,
                    "path": h.path,
                    "url": h.url,
                    "raw": h.raw,
                }
                for h in sorted(self._held.values(), key=lambda x: x.id)
            ]
            return {"enabled": self.enabled, "scope": self.scope, "pending": pending}

    def configure(self, enabled=None, scope=None):
        release = []
        with self._lock:
            if scope is not None:
                self.scope = str(scope).strip()
            if enabled is not None:
                self.enabled = bool(enabled)
                if not self.enabled:
                    release = list(self._held.values())
                    for h in release:
                        h.action = "forward"
        for h in release:
            h.event.set()
        return self.snapshot()

    # ----- proxy side -------------------------------------------------

    def hold(self, method, scheme, host, port, path, url, headers, body):
        """Queue a request if interception applies to it. Returns the Held object or None."""
        with self._lock:
            if not self.enabled:
                return None
            if self.scope and self.scope.lower() not in url.lower():
                return None
            self._seq += 1
            held = Held(
                self._seq, method, scheme, host, port, path, url,
                build_raw(method, path, headers, body),
            )
            self._held[held.id] = held
            return held

    def wait(self, held):
        """Block until the user decides or the timeout passes, then unqueue the request."""
        held.event.wait(self.timeout)
        with self._lock:
            self._held.pop(held.id, None)
        return held

    # ----- UI side ----------------------------------------------------

    def decide(self, hid, action, raw=None):
        """Forward (optionally with edited raw text) or drop a held request.

        Returns False when the id is unknown (already decided or timed out).
        Raises ValueError when the edited raw text cannot be parsed; the request stays held.
        """
        with self._lock:
            held = self._held.get(hid)
            if held is None:
                return False
            override = None
            if action == "forward" and raw is not None and raw != held.raw:
                override = parse_raw(raw)
            held.override = override
            held.action = action
        held.event.set()
        return True
