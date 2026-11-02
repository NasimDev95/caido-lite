<p align="center">
  <img src="https://img.shields.io/badge/Caido%20Lite-1.2.0-orange?style=for-the-badge" alt="Caido Lite 1.2.0">
</p>

<h1 align="center">Caido Lite</h1>

<p align="center">
  <b>An intercepting HTTP/HTTPS proxy with a Caido-style web UI that runs on Android, inside Termux.</b>
</p>

<p align="center">
  Inspect, hold, edit, replay and export web traffic from your phone. No laptop needed.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white" alt="Python 3"></a>
  <a href="https://termux.dev"><img src="https://img.shields.io/badge/platform-Android%20(Termux)-3DDC84?logo=android&logoColor=white" alt="Platform: Android (Termux)"></a>
  <a href="#features"><img src="https://img.shields.io/badge/dependencies-none-brightgreen" alt="No dependencies"></a>
  <a href="https://github.com/NasimDev95/caido-lite/stargazers"><img src="https://img.shields.io/github/stars/NasimDev95/caido-lite?style=social" alt="GitHub stars"></a>
  <a href="https://github.com/NasimDev95/caido-lite/commits"><img src="https://img.shields.io/github/last-commit/NasimDev95/caido-lite" alt="Last commit"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#setup-guide-step-by-step">Setup guide</a> ·
  <a href="#downloads">Downloads</a> ·
  <a href="#troubleshooting">Troubleshooting</a> ·
  <a href="#contributing">Contributing</a>
</p>

---

Caido Lite is a small intercepting proxy for Android. It runs as a Python program inside Termux and gives you a web UI that works on a phone screen. You can record traffic, hold requests and edit them before they leave the device, replay them, and export the history as HAR.

> **Use it only on devices and networks you own, or for authorized testing.** Caido Lite is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by Caido Labs.

---

## Why Caido Lite?

Caido and Burp Suite are built for desktops. Caido Lite brings the same workflow to a phone:

- **Runs where you are.** Everything runs in Termux on Android. No PC, no VM, no root.
- **Zero dependencies.** Pure Python standard library. Nothing to `pip install`.
- **Phone-first UI.** Bottom navigation, full-screen details, touch-friendly controls.
- **Small and readable.** Each file has one job, so you can learn how an intercepting proxy works by reading it.

---

## Features

- **HTTP and HTTPS interception** (TLS MITM) with per-site certificates signed by a local root CA. Works even when a client connects by IP and sends SNI.
- **Intercept.** Hold requests, edit the raw text (method, path, headers, body), then forward or drop. Optional URL scope. Unanswered requests are forwarded automatically after 10 minutes.
- **HTTP History.** Live list with search, status filters (2xx to 5xx, errors), method and source filters, and paging.
- **Request detail.** Raw or pretty view of requests and responses, gzip, deflate and chunked decoding for display, copy as cURL, copy raw, download body, delete a row.
- **Replay.** Edit a raw request, resend it, and reuse recent replays.
- **HAR 1.2 export** for import into other tools.
- **Certificate page.** Download the root CA and follow the Android install steps.
- **Settings.** Proxy status, LAN address, theme (system, dark, light), refresh rate, clear history.
- **Mobile-first UI.** Bottom navigation on phones, split history and detail view on tablets and desktops, Font Awesome icons, dark and light themes.
- **WebSocket and Upgrade passthrough.** After a `101 Switching Protocols` response, the connection is relayed as a raw pipe.
- **Safer web UI.** The API accepts only JSON POST requests, and Host headers other than localhost are rejected. This blocks cross-site form requests and DNS rebinding.

---

## How it works

```
Browser / app on phone
      │
      ▼
Caido Lite proxy (127.0.0.1:8080)   ← records, holds, edits, replays
      │
      ▼
Internet
```

- HTTP requests pass through the proxy as they are.
- HTTPS requests are decrypted by Caido Lite using a certificate for that site, signed by the **root CA** you install on Android. Apps that trust that CA see a normal HTTPS connection.
- The web UI at `http://127.0.0.1:9090` lets you watch and control everything.
- Optionally, the **Proxy-VPN** Android app sends all phone traffic to `http://127.0.0.1:8080`, so you do not have to set a proxy in each app.

---

## Downloads

| What | Link | Notes |
|------|------|-------|
| Termux (recommended) | [F-Droid](https://f-droid.org/packages/com.termux/) | Install from F-Droid |
| Termux (alternative) | [GitHub releases](https://github.com/termux/termux-app/releases) | Install the APK from GitHub |
| Proxy-VPN app | [Latest release](https://github.com/NasimDev95/Proxy-VPN/releases/latest) | Download the APK from the latest release |
| Caido Lite | [Repository](https://github.com/NasimDev95/caido-lite) | Clone the repo, or download the zip from Releases |

**Do not use the Termux version from the Play Store.** It is old and its packages no longer work.

---

## Requirements

- Android 7 or newer (Termux requirement)
- About 100 MB of free storage
- Termux from F-Droid or GitHub

---

## Quick start

For experienced users. The full guide below explains each step.

```bash
pkg update && pkg upgrade -y && pkg install python openssl git -y
termux-setup-storage
git clone https://github.com/NasimDev95/caido-lite.git ~/caido-lite
cd ~/caido-lite && python main.py
```

Then open `http://127.0.0.1:9090`, install the CA (`python main.py --export-ca`), and point your traffic at `127.0.0.1:8080`.

---

## Setup guide (step by step)

### Step 1: Install Termux

1. Install F-Droid from [f-droid.org](https://f-droid.org), or open the Termux link above in your browser.
2. Install Termux from F-Droid, or install the Termux APK from GitHub.
3. Open Termux once and wait until the prompt appears.

### Step 2: Install the tools Caido Lite needs

Run these commands in Termux:

```bash
pkg update && pkg upgrade -y
pkg install python openssl git unzip -y
termux-setup-storage
```

When Android asks for storage permission, tap **Allow**. This lets Caido Lite copy the root CA to your Downloads folder.

### Step 3: Get Caido Lite

Choose one option.

**Option A: clone with git (recommended, easy to update)**

```bash
git clone https://github.com/NasimDev95/caido-lite.git ~/caido-lite
```

**Option B: download the zip**

1. Download `caido-lite-v1.2.zip` from the Releases page.
2. Unzip it into your home folder:

```bash
cd ~/storage/downloads
unzip caido-lite-v1.2.zip -d ~/
```

You now have the project at `~/caido-lite`.

### Step 4: Start Caido Lite

```bash
cd ~/caido-lite
python main.py
```

You should see something like this:

```
Caido Lite 1.2.0 is running
  Web UI : http://127.0.0.1:9090
  Proxy  : 127.0.0.1:8080  (state: running)
```

Open **http://127.0.0.1:9090** in Chrome or any browser on your phone. The status pill at the top should say **Running**.

Keep Termux running in the background. In Android settings, set Termux to **Unrestricted** battery use, and tap **Acquire wakelock** in the Termux notification, so Android does not stop the proxy.

### Step 5: Install the root CA on Android

This step is needed only for HTTPS. Do it once.

1. Export the certificate:

   ```bash
   python main.py --export-ca
   ```

   This copies `caido-lite-ca.crt` into your Downloads folder.

2. Open **Settings > Security & privacy > More security settings > Encryption & credentials > Install a certificate > CA certificate**. On some phones the path is **Settings > Security > Encryption & credentials**.
3. Tap **Install anyway** if Android shows a warning.
4. Select `caido-lite-ca.crt` from Downloads.
5. Give it a name such as `Caido Lite` and confirm.

Chrome and Firefox trust user-installed CAs. Many other apps (targeting Android 7 or newer) do not. That is normal Android behavior.

### Step 6: Send traffic through Caido Lite

You have two options.

**Option 1 (recommended): Proxy-VPN app, whole phone**

1. Install the Proxy-VPN APK from the link above. Allow "Install unknown apps" for your browser or file manager if asked.
2. Open Proxy-VPN. The proxy URL is already set to `http://127.0.0.1:8080`, which matches Caido Lite's default port. Change it only if you used another port.
3. Tap **Connect** and allow the VPN permission.
4. Open Chrome and browse. The requests appear in Caido Lite's **History** tab.

Termux is excluded from the VPN automatically, so Caido Lite's own connections do not loop back into the VPN.

**Option 2: Wi-Fi manual proxy (Wi-Fi only)**

1. Open **Settings > Network > Wi-Fi**, long-press your network, and choose **Modify**.
2. Open **Advanced options**, set **Proxy** to **Manual**.
3. Set **Proxy hostname** to `127.0.0.1` and **Proxy port** to `8080`. Save.

Some apps ignore Wi-Fi proxy settings. Use Option 1 for those.

### Step 7: Test it

1. In Chrome, open `http://example.com`.
2. In Caido Lite, open **History**. You should see a `GET` row for `example.com` with status `200`.
3. Tap the row. The detail panel shows the request and response.
4. Open `https://example.com`. If the certificate is trusted, the row appears with the same details. If Chrome shows a certificate error, see [Troubleshooting](#troubleshooting).

### Step 8: Use Intercept

1. Open the **Intercept** tab and switch it on. New requests are now held.
2. Optional: type a scope such as `example.com` so only matching URLs are held.
3. In Chrome, open the site. The request appears in the **Held requests** list.
4. Select it and edit the raw text in the editor.
5. Tap **Forward** (or press Ctrl+Enter) to send it with your changes, or **Drop** to cancel it.
6. Switch Intercept off to release everything held.

### Optional: create a `caido` shortcut

This lets you start Caido Lite by typing `caido` in Termux:

```bash
printf '#!/data/data/com.termux/files/usr/bin/sh\ncd ~/caido-lite && python main.py "$@"\n' > $PREFIX/bin/caido
chmod +x $PREFIX/bin/caido
```

Then run:

```bash
caido
```

---

## Command-line options

| Flag | Default | Meaning |
|------|---------|---------|
| `--proxy-port` | `8080` | Proxy listening port |
| `--proxy-host` | `127.0.0.1` | Proxy bind address |
| `--ui-port` | `9090` | Web UI port |
| `--ui-host` | `127.0.0.1` | Web UI bind address (keep on localhost) |
| `--lan` | off | Bind the proxy to `0.0.0.0` so other devices on Wi-Fi can use it |
| `--no-mitm` | off | Tunnel HTTPS without decrypting (routing only) |
| `--no-autostart` | off | Start the UI without starting the proxy |
| `--export-ca` | | Copy the root CA to Downloads and exit |

Examples:

```bash
python main.py --proxy-port 8888          # use another port
python main.py --lan                      # let another device use this proxy
python main.py --no-mitm                  # route HTTPS without decrypting it
```

---

## Using the UI

- **History.** Tap a row to open its details. On phones the detail opens full screen. Use the chips at the top to filter by status.
- **Intercept.** Hold, edit, forward or drop requests. Edited requests are saved to History with source `intercept`.
- **Replay.** Paste or edit a raw request, set scheme, host and port, then Send (Ctrl+Enter also sends). Replays are saved with source `replay`.
- **Certificate.** Download the root CA and see the install steps.
- **Settings.** Check proxy status, export the history as HAR, clear history, change theme and refresh rate.

---

## Troubleshooting

**"Proxy could not start" or "Address already in use"**
Another app is using port 8080. Start Caido Lite on another port:

```bash
python main.py --proxy-port 8888
```

Then change the port in Proxy-VPN or your Wi-Fi proxy settings to match.

**Chrome shows a certificate error (`ERR_CERT_...`)**
- Check that `caido-lite-ca.crt` is installed under **CA certificate** (not VPN or user apps).
- Restart Chrome after installing the CA.
- Make sure you are using the same Caido Lite session. If you deleted `~/.caido-lite/`, export and install the CA again.
- Some apps pin their certificates and will always fail. This is expected.

**Connection refused (`ECONNREFUSED 127.0.0.1:8080`)**
Caido Lite is not running. Start it with `python main.py` in Termux and keep Termux open.

**History fills up with requests from other apps**
This is normal when Proxy-VPN is connected, because every app's traffic goes through the proxy. To reduce noise:
- Use the **Intercept** scope, or the History search and filters.
- Turn Intercept off when you are not testing. Requests are held only while it is on.

**Termux stops in the background**
Enable **Acquire wakelock** in the Termux notification, and set Termux battery usage to **Unrestricted**.

**Some apps show errors after I connect**
Apps that ignore user-installed CAs will fail on HTTPS when MITM is on. Use `--no-mitm` for those sessions, or test in Chrome.

---

## Project structure

```
caido-lite/
├── main.py          # entry point, CLI and app wiring
├── certs.py         # root CA and per-site certificate generation (uses openssl)
├── proxy.py         # proxy server, TLS interception, forwarding, WebSocket relay
├── intercept.py     # hold, edit, forward and drop queue
├── store.py         # SQLite history
├── server.py        # web UI server, JSON API and HAR export
├── LICENSE
└── webui/
    ├── index.html   # app shell
    ├── app.css      # styles (mobile first, dark and light themes)
    ├── app.js       # history, detail, replay, settings
    └── intercept.js # intercept view
```

Data is stored in `~/.caido-lite/`:
- `ca/` holds the root CA. **Keep `caido-lite-ca.key` private.**
- `history.db` holds the captured traffic.

Delete `~/.caido-lite/` to start fresh.

---

## Security notes

- The web UI binds to `127.0.0.1` only. Do not expose it to the internet. Use `--lan` only on networks you trust.
- The root CA can decrypt HTTPS traffic on any device that trusts it. Do not share `~/.caido-lite/ca/`, and remove the CA from Android when you stop testing (**Settings > Security > Encryption & credentials > Trusted credentials**).
- The web API rejects requests that are not JSON POST, and rejects Host headers other than localhost.
- Use Caido Lite only on your own devices and apps, or on systems where you have written permission to test. Do not use it to access accounts or data that are not yours.

To report a security issue, open a private security advisory on GitHub instead of a public issue.

---

## Known limitations

- Only requests are held by Intercept. Responses are shown as received.
- The proxy speaks HTTP/1.1. HTTP/2 from the client is not negotiated.
- WebSocket frames are relayed but not decoded in the UI.
- Certificate-pinned apps cannot be intercepted without patching them.

---

## Roadmap

- Hold and edit responses
- WebSocket frame viewer
- HTTP/2 support
- Saved filters and scope presets

---

## Contributing

Issues and pull requests are welcome.

1. Fork the repo and create a branch.
2. Keep the project dependency-free (standard library only).
3. Keep the UI usable on a phone screen.
4. Open a pull request with a short description of what changed and how you tested it.

Good first issues: UI wording, Termux setup notes, and new filters in History.

---

## Built with

- [Python 3](https://www.python.org/) standard library (no third-party packages)
- [Termux](https://termux.dev) for a real Linux shell on Android
- [OpenSSL](https://www.openssl.org) command-line tool for certificate generation
- [Font Awesome](https://fontawesome.com) icons
- Vanilla JavaScript, HTML and CSS for the web UI

---

## License

Released under the [MIT License](LICENSE). You can use, copy, modify and share this software, including in commercial projects, as long as the copyright notice stays in place.

Copyright (c) 2026 Nasim (NasimDev95)
