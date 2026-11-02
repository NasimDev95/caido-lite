(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const st = {
    enabled: false,
    pending: [],
    selectedId: null,
    drafts: new Map(),   // id -> edited text the user has not sent yet
    loadedFor: null,     // id whose raw text is currently in the editor
    busy: false,
  };

  async function call(path, body) {
    const init = body === undefined
      ? {}
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const res = await fetch(path, init);
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty */ }
    if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
    return data;
  }

  function note(msg, isErr) {
    const t = document.getElementById("toast");
    if (!t) return;
    t.textContent = msg;
    t.classList.toggle("err", !!isErr);
    t.hidden = false;
    clearTimeout(note._t);
    note._t = setTimeout(() => { t.hidden = true; }, 2600);
  }

  function ageText(ts) {
    const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
    if (s < 60) return s + "s";
    if (s < 3600) return Math.floor(s / 60) + "m";
    return Math.floor(s / 3600) + "h";
  }

  function hostPort(item) {
    const std = (item.scheme === "https" && item.port === 443) || (item.scheme === "http" && item.port === 80);
    return std ? item.host : `${item.host}:${item.port}`;
  }

  // ----- rendering -----------------------------------------------------

  function renderQueue() {
    const list = $("#iQueue");
    list.textContent = "";
    $("#iEmpty").hidden = st.pending.length > 0;
    for (const item of st.pending) {
      const row = document.createElement("button");
      row.className = "queue-item" + (item.id === st.selectedId ? " selected" : "");
      row.type = "button";
      row.dataset.id = item.id;

      const top = document.createElement("div");
      top.className = "queue-top";
      const m = document.createElement("span");
      m.className = "method-badge method-" + item.method;
      m.textContent = item.method;
      const age = document.createElement("span");
      age.className = "muted small mono";
      age.textContent = ageText(item.created);
      top.append(m, age);

      const url = document.createElement("div");
      url.className = "mono ellipsis small";
      url.textContent = hostPort(item) + item.path;
      url.title = item.url;

      if (st.drafts.has(item.id)) {
        const edited = document.createElement("span");
        edited.className = "edited-tag";
        edited.textContent = "edited";
        top.appendChild(edited);
      }
      row.append(top, url);
      row.addEventListener("click", () => select(item.id));
      list.appendChild(row);
    }
    const badge = document.getElementById("interceptBadge");
    if (badge) {
      badge.hidden = st.pending.length === 0;
      badge.textContent = st.pending.length;
    }
    $("#iCount").textContent = st.pending.length ? `${st.pending.length} held` : "Nothing held";
  }

  function renderSwitch() {
    const sw = $("#iSwitch");
    sw.checked = st.enabled;
    $("#iState").textContent = st.enabled ? "Intercept on" : "Intercept off";
    $("#iState").classList.toggle("on", st.enabled);
  }

  function renderEditor() {
    const editor = $("#iEditor");
    const actions = $("#iActions");
    const item = st.pending.find((p) => p.id === st.selectedId);
    if (!item) {
      editor.value = "";
      editor.disabled = true;
      actions.querySelectorAll("button").forEach((b) => (b.disabled = true));
      $("#iTitle").textContent = "Select a held request";
      $("#iUrl").textContent = "";
      st.loadedFor = null;
      return;
    }
    editor.disabled = false;
    actions.querySelectorAll("button").forEach((b) => (b.disabled = st.busy));
    $("#iTitle").textContent = item.method;
    $("#iTitle").className = "method-badge method-" + item.method;
    $("#iUrl").textContent = item.url;
    if (st.loadedFor !== item.id) {
      editor.value = st.drafts.has(item.id) ? st.drafts.get(item.id) : item.raw;
      st.loadedFor = item.id;
    }
  }

  function render() {
    renderSwitch();
    renderQueue();
    renderEditor();
  }

  // ----- data ----------------------------------------------------------

  async function refresh() {
    try {
      const data = await call("/api/intercept");
      applySnapshot(data);
    } catch (_) {
      /* UI offline; the status bar already shows it */
    }
  }

  function applySnapshot(data) {
    const before = new Set(st.pending.map((p) => p.id));
    st.enabled = data.enabled;
    st.pending = data.pending;
    for (const id of [...st.drafts.keys()]) {
      if (!st.pending.some((p) => p.id === id)) st.drafts.delete(id);
    }
    if (st.selectedId !== null && !st.pending.some((p) => p.id === st.selectedId)) {
      if (before.has(st.selectedId)) note("Request was released or timed out", false);
      st.selectedId = null;
      st.loadedFor = null;
    }
    if (st.selectedId === null && st.pending.length) {
      st.selectedId = st.pending[0].id;
      st.loadedFor = null;
    }
    render();
  }

  function select(id) {
    const editor = $("#iEditor");
    if (st.selectedId !== null && st.loadedFor === st.selectedId && editor.value !== "") {
      const original = st.pending.find((p) => p.id === st.selectedId);
      if (original && editor.value !== original.raw) st.drafts.set(st.selectedId, editor.value);
    }
    st.selectedId = id;
    st.loadedFor = null;
    render();
  }

  async function setEnabled(enabled) {
    try {
      const scope = $("#iScope").value;
      applySnapshot(await call("/api/intercept", { enabled, scope }));
      note(enabled ? "Intercept on: new requests will be held" : "Intercept off: held requests were released");
    } catch (err) {
      note(err.message, true);
      refresh();
    }
  }

  async function decide(action) {
    const item = st.pending.find((p) => p.id === st.selectedId);
    if (!item || st.busy) return;
    st.busy = true;
    const editor = $("#iEditor");
    const raw = editor.value;
    const body = action === "forward" ? { raw } : {};
    try {
      await call(`/api/intercept/${item.id}/${action}`, body);
      st.drafts.delete(item.id);
      note(action === "forward" ? "Forwarded" : "Dropped");
      st.selectedId = null;
      st.loadedFor = null;
    } catch (err) {
      note(err.message, true);
    } finally {
      st.busy = false;
      await refresh();
    }
  }

  // ----- events --------------------------------------------------------

  $("#iSwitch").addEventListener("change", (e) => setEnabled(e.currentTarget.checked));

  $("#iScope").addEventListener("change", async () => {
    try {
      applySnapshot(await call("/api/intercept", { scope: $("#iScope").value }));
      note(`Scope: ${$("#iScope").value || "all requests"}`);
    } catch (err) {
      note(err.message, true);
    }
  });

  $("#iForward").addEventListener("click", () => decide("forward"));
  $("#iDrop").addEventListener("click", () => decide("drop"));

  $("#iReset").addEventListener("click", () => {
    const item = st.pending.find((p) => p.id === st.selectedId);
    if (!item) return;
    st.drafts.delete(item.id);
    st.loadedFor = null;
    renderEditor();
  });

  $("#iEditor").addEventListener("input", (e) => {
    const item = st.pending.find((p) => p.id === st.selectedId);
    if (!item) return;
    if (e.currentTarget.value === item.raw) st.drafts.delete(item.id);
    else st.drafts.set(item.id, e.currentTarget.value);
    renderQueue();
  });

  // Ctrl/Cmd + Enter forwards from the editor.
  $("#iEditor").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      decide("forward");
    }
  });

  // Keep the badge and queue fresh even when the Intercept tab is not open.
  refresh();
  setInterval(refresh, 1200);
})();
