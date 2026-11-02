(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const state = { view: "history", selectedId: null, lastCount: -1, status: null, items: [] };

  // ----- helpers -------------------------------------------------------

  async function api(path, opts = {}) {
    const init = { headers: {}, ...opts };
    if (opts.body !== undefined && typeof opts.body !== "string") {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, init);
    let data = null;
    try { data = await res.json(); } catch (_) { /* not JSON */ }
    if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
    return data;
  }

  function toast(msg, isErr = false) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.toggle("err", isErr);
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { el.hidden = true; }, 2600);
  }

  function fmtBytes(n) {
    if (n == null) return "";
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }

  function fmtTime(ts) {
    const d = new Date(ts * 1000);
    return d.toTimeString().slice(0, 8);
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function statusClass(code) {
    if (!code) return "";
    return "s" + Math.floor(code / 100);
  }

  function hostPort(item) {
    const std = (item.scheme === "https" && item.port === 443) || (item.scheme === "http" && item.port === 80);
    return std ? item.host : `${item.host}:${item.port}`;
  }

  // ----- views ---------------------------------------------------------

  function showView(name) {
    state.view = name;
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
    if (name === "history") loadHistory();
    if (name === "settings") renderSettings();
  }

  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });

  // ----- status and proxy toggle --------------------------------------

  function renderStatus(s) {
    state.status = s;
    const pill = $("#statusPill");
    pill.classList.toggle("on", s.running);
    pill.classList.toggle("off", !s.running);
    $("#statusText").textContent = s.running ? "Proxy running" : "Proxy stopped";
    $("#proxyAddr").textContent = `${s.proxy_host}:${s.proxy_port}`;
    const btn = $("#toggleProxy");
    btn.querySelector("span").textContent = s.running ? "Stop" : "Start";
    btn.dataset.action = s.running ? "stop" : "start";
    if (s.count !== state.lastCount) {
      state.lastCount = s.count;
      if (state.view === "history") loadHistory();
    }
  }

  async function refreshStatus() {
    try {
      renderStatus(await api("/api/status"));
    } catch (err) {
      $("#statusText").textContent = "UI offline";
      $("#statusPill").classList.add("off");
    }
  }

  $("#toggleProxy").addEventListener("click", async (e) => {
    const action = e.currentTarget.dataset.action || "start";
    try {
      renderStatus(await api("/api/proxy", { method: "POST", body: { action } }));
      toast(action === "start" ? "Proxy started" : "Proxy stopped");
    } catch (err) {
      toast(err.message, true);
    }
  });

  $("#refreshBtn").addEventListener("click", () => {
    refreshStatus();
    if (state.view === "history") loadHistory();
  });

  // ----- history -------------------------------------------------------

  async function loadHistory() {
    const q = $("#searchInput").value.trim();
    const method = $("#methodFilter").value;
    const params = new URLSearchParams({ limit: "500" });
    if (q) params.set("q", q);
    if (method) params.set("method", method);
    try {
      const data = await api("/api/history?" + params.toString());
      state.items = data.items;
      renderHistory(data);
    } catch (err) {
      toast(err.message, true);
    }
  }

  function renderHistory(data) {
    const body = $("#historyBody");
    body.textContent = "";
    $("#countText").textContent = `${data.items.length} shown / ${data.total} total`;
    $("#emptyState").hidden = data.items.length > 0;
    const frag = document.createDocumentFragment();
    for (const item of data.items) {
      const tr = document.createElement("tr");
      tr.dataset.id = item.id;
      if (item.id === state.selectedId) tr.classList.add("selected");

      tr.appendChild(el("td", "col-id", item.id));

      const tdM = el("td", "col-method");
      tdM.appendChild(el("span", "method-badge method-" + item.method, item.method));
      tr.appendChild(tdM);

      const tdH = el("td", "host", hostPort(item));
      tdH.title = item.url;
      tr.appendChild(tdH);

      const tdP = el("td", "path mono", item.path);
      tdP.title = item.path;
      tr.appendChild(tdP);

      const tdS = el("td", "col-status");
      if (item.error) {
        tdS.appendChild(el("span", "status-err", "ERR"));
        tdS.title = item.error;
      } else if (item.status) {
        tdS.appendChild(el("span", "status-code " + statusClass(item.status), item.status));
      } else {
        tdS.appendChild(el("span", "muted", "..."));
      }
      tr.appendChild(tdS);

      tr.appendChild(el("td", "col-len", item.resp_length != null ? fmtBytes(item.resp_length) : ""));
      tr.appendChild(el("td", "col-time", fmtTime(item.created)));

      tr.addEventListener("click", () => selectTx(item.id));
      frag.appendChild(tr);
    }
    body.appendChild(frag);
  }

  $("#searchInput").addEventListener("input", debounce(loadHistory, 250));
  $("#methodFilter").addEventListener("change", loadHistory);
  $("#clearBtn").addEventListener("click", async () => {
    if (!confirm("Clear all stored traffic?")) return;
    await api("/api/clear", { method: "POST", body: {} });
    closeDetail();
    loadHistory();
    refreshStatus();
  });

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  // ----- detail --------------------------------------------------------

  function bodyText(view) {
    if (!view || !view.size) return "";
    if (view.encoding === "base64") return `[binary body, ${fmtBytes(view.size)}]`;
    return view.text;
  }

  function buildRawRequest(tx) {
    const lines = [`${tx.method} ${tx.path} HTTP/1.1`];
    for (const [k, v] of tx.req_headers) lines.push(`${k}: ${v}`);
    let text = lines.join("\n") + "\n\n";
    text += bodyText(tx.req_body_view);
    return text;
  }

  function buildRawResponse(tx) {
    if (tx.error) return `Error: ${tx.error}`;
    if (!tx.status) return "Waiting for response...";
    const lines = [`HTTP/1.1 ${tx.status} ${tx.reason || ""}`.trim()];
    for (const [k, v] of tx.resp_headers) lines.push(`${k}: ${v}`);
    return lines.join("\n") + "\n\n" + bodyText(tx.resp_body_view);
  }

  async function selectTx(id) {
    state.selectedId = id;
    document.querySelectorAll("#historyBody tr").forEach((r) => r.classList.toggle("selected", Number(r.dataset.id) === id));
    try {
      const tx = await api("/api/tx/" + id);
      state.currentTx = tx;
      $("#detail").hidden = false;
      $("#dMethod").textContent = tx.method;
      $("#dMethod").className = "method-badge method-" + tx.method;
      $("#dUrl").textContent = tx.url;
      $("#dMeta").textContent = [
        tx.status ? `${tx.status} ${tx.reason || ""}`.trim() : (tx.error ? "error" : "pending"),
        tx.duration_ms != null ? `${Math.round(tx.duration_ms)} ms` : null,
        tx.source,
      ].filter(Boolean).join("  ·  ");
      $("#dReq").textContent = buildRawRequest(tx);
      $("#dResp").textContent = buildRawResponse(tx);
    } catch (err) {
      toast(err.message, true);
    }
  }

  function closeDetail() {
    state.selectedId = null;
    state.currentTx = null;
    $("#detail").hidden = true;
  }

  $("#closeDetail").addEventListener("click", closeDetail);

  $("#sendToReplay").addEventListener("click", () => {
    const tx = state.currentTx;
    if (!tx) return;
    $("#rScheme").value = tx.scheme;
    $("#rHost").value = tx.host;
    $("#rPort").value = tx.port;
    $("#rRaw").value = buildRawRequest(tx);
    $("#rResp").textContent = "";
    showView("replay");
  });

  // ----- replay --------------------------------------------------------

  $("#sendReplay").addEventListener("click", async () => {
    const btn = $("#sendReplay");
    const scheme = $("#rScheme").value;
    const host = $("#rHost").value.trim();
    const port = $("#rPort").value.trim() || (scheme === "https" ? "443" : "80");
    const raw = $("#rRaw").value;
    if (!host) return toast("Enter a host", true);
    if (!raw.trim()) return toast("Enter a raw request", true);
    btn.disabled = true;
    $("#replayStatus").textContent = "Sending...";
    try {
      const { id } = await api("/api/replay", { method: "POST", body: { scheme, host, port: Number(port), raw } });
      const tx = await api("/api/tx/" + id);
      $("#rResp").textContent = buildRawResponse(tx);
      $("#replayStatus").textContent = tx.status ? `${tx.status} in ${Math.round(tx.duration_ms)} ms` : "No response";
      state.lastCount = -1;
    } catch (err) {
      $("#rResp").textContent = "Error: " + err.message;
      $("#replayStatus").textContent = "Failed";
    } finally {
      btn.disabled = false;
    }
  });

  // ----- settings and certificate -------------------------------------

  function renderSettings() {
    const s = state.status;
    if (!s) return;
    $("#sAddr").textContent = `${s.proxy_host}:${s.proxy_port}`;
    $("#sMitm").textContent = s.mitm ? "Enabled (CA required on client)" : "Disabled (tunnel only)";
    $("#sUi").textContent = s.ui_port;
    $("#sCount").textContent = s.count;
  }

  $("#copyCaUrl").addEventListener("click", async () => {
    const url = (state.status && state.status.ca_url) || "http://caido.lite/ca.crt";
    try {
      await navigator.clipboard.writeText(url);
      toast("Copied " + url);
    } catch (_) {
      toast(url);
    }
  });

  // ----- boot ----------------------------------------------------------

  refreshStatus();
  loadHistory();
  setInterval(refreshStatus, 2000);
})();
