# Caido Lite

A small intercepting HTTP/HTTPS proxy with a Caido-style web UI, written in pure
Python standard library. It runs in Termux on Android.

## Features

- HTTP and HTTPS interception (TLS MITM) with per-host certificates signed by a local root CA
- HTTP History with search, method filter, request and response viewer
- Replay tab to edit a raw request and resend it
- Root CA download page and install steps
- Font Awesome icons, dark theme, phone-friendly layout

## Install in Termux

```bash
pkg update && pkg upgrade -y
pkg install python openssl -y
termux-setup-storage            # allows the CA to be copied to Downloads
mkdir -p ~/caido-lite && cd ~/caido-lite
# copy all project files here (main.py, certs.py, proxy.py, server.py, store.py, webui/)
python main.py
```

Open the web UI at `http://127.0.0.1:9090` in any browser on the phone.

## Install the root CA on Android

1. `python main.py --export-ca` (copies `caido-lite-ca.crt` to Downloads)
2. Settings > Security > Encryption and credentials > Install a certificate > CA certificate
3. Choose `caido-lite-ca.crt` from Downloads and confirm
4. Chrome and Firefox on Android trust user-installed CAs. Most other apps (targeting Android 7 or newer) ignore user CAs by default, and apps that pin certificates reject them. That is expected, and it is why you intercept with a browser.

## Use the proxy from the phone

Set the proxy to `127.0.0.1:8080` of your wifi or cellular data using our vpn proxy app., or in Wi-Fi advanced settings.

For another device on the same Wi-Fi:

```bash
python main.py --lan
```

Then set that device's proxy to the phone's Wi-Fi IP and port 8080.

## Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--proxy-port` | 8080 | Proxy listening port |
| `--ui-port` | 9090 | Web UI port |
| `--lan` | off | Bind proxy to 0.0.0.0 |
| `--ui-host` | 127.0.0.1 | Web UI bind address (keep on localhost) |
| `--no-mitm` | off | Tunnel HTTPS without decrypting |
| `--no-autostart` | off | Start without the proxy running |
| `--export-ca` | - | Copy root CA to Downloads and exit |

## Files

- `main.py` entry point and CLI
- `certs.py` root CA and per-host certificate generation (uses `openssl`)
- `proxy.py` proxy server, request parsing, TLS interception, forwarding
- `store.py` SQLite history at `~/.caido-lite/history.db`
- `server.py` web UI server and JSON API
- `webui/` the front end (HTML, CSS, JS)

## Intercept

1. Open the **Intercept** tab and switch it on. Every new request is held.
2. Optionally type a scope (for example `example.com`) so only matching URLs are held.
3. Select a held request, edit the raw request in the editor (method, path, headers, body), then:
   - **Forward** sends it upstream with your edits. Ctrl+Enter also forwards.
   - **Drop** closes the connection, so the browser sees a failed request.
   - **Reset edits** restores the original text.
4. Requests nobody answers within 10 minutes are forwarded unchanged. Switching Intercept off releases everything held.

Edited requests are recorded in the history with source `intercept`.

## Limits

- Only requests are intercepted. Responses are not held yet.
- Only use this on traffic and devices you own or are authorized to test.
- Certificate-pinned apps cannot be intercepted without patching them.
