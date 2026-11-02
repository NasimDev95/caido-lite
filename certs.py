"""Local root CA plus on-the-fly per-host certificates for TLS interception.

Uses the openssl command line tool (available in Termux via `pkg install openssl`),
so no pip packages are needed.
"""

import ipaddress
import os
import shutil
import ssl
import subprocess
import tempfile
import threading


class CertError(RuntimeError):
    pass


def _is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class CertManager:
    """Creates a root CA once, then issues a server certificate for each intercepted host."""

    def __init__(self, cert_dir):
        self.dir = cert_dir
        os.makedirs(cert_dir, exist_ok=True)
        self.ca_key = os.path.join(cert_dir, "caido-lite-ca.key")
        self.ca_cert = os.path.join(cert_dir, "caido-lite-ca.crt")
        self.ca_serial = os.path.join(cert_dir, "caido-lite-ca.srl")
        self._contexts = {}
        self._lock = threading.Lock()
        self._ensure_ca()

    def _openssl(self, *args):
        if shutil.which("openssl") is None:
            raise CertError("openssl is missing. Install it with: pkg install openssl")
        proc = subprocess.run(["openssl", *args], capture_output=True)
        if proc.returncode != 0:
            raise CertError("openssl failed: " + proc.stderr.decode("utf-8", "replace").strip())

    def _ensure_ca(self):
        if os.path.isfile(self.ca_key) and os.path.isfile(self.ca_cert):
            return
        self._openssl(
            "req", "-x509", "-new", "-nodes",
            "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
            "-days", "3650",
            "-keyout", self.ca_key,
            "-out", self.ca_cert,
            "-subj", "/C=IN/O=Caido Lite/CN=Caido Lite Root CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
            "-addext", "subjectKeyIdentifier=hash",
        )
        os.chmod(self.ca_key, 0o600)

    def ca_pem(self):
        with open(self.ca_cert, "rb") as fh:
            return fh.read()

    def export_ca(self, dest_path):
        shutil.copyfile(self.ca_cert, dest_path)
        return dest_path

    def server_context(self, host):
        """Return a TLS server context presenting a certificate for `host`."""
        with self._lock:
            ctx = self._contexts.get(host)
            if ctx is None:
                ctx = self._issue(host)
                self._contexts[host] = ctx
            return ctx

    def _issue(self, host):
        san = ("IP" if _is_ip(host) else "DNS") + ":" + host
        with tempfile.TemporaryDirectory() as tmp:
            key = os.path.join(tmp, "leaf.key")
            csr = os.path.join(tmp, "leaf.csr")
            crt = os.path.join(tmp, "leaf.crt")
            ext = os.path.join(tmp, "leaf.ext")
            with open(ext, "w") as fh:
                fh.write(
                    "basicConstraints=CA:FALSE\n"
                    "keyUsage=critical,digitalSignature,keyEncipherment\n"
                    "extendedKeyUsage=serverAuth\n"
                    "authorityKeyIdentifier=keyid\n"
                    "subjectAltName=" + san + "\n"
                )
            self._openssl(
                "req", "-new", "-nodes",
                "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                "-keyout", key, "-out", csr,
                "-subj", "/CN=" + host,
            )
            self._openssl(
                "x509", "-req", "-in", csr,
                "-CA", self.ca_cert, "-CAkey", self.ca_key,
                "-CAserial", self.ca_serial, "-CAcreateserial",
                "-days", "825", "-sha256",
                "-extfile", ext, "-out", crt,
            )
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(crt, key)
            ctx.set_alpn_protocols(["http/1.1"])
            return ctx
