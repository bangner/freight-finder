// ABC Freight page logic. No framework: one EventSource, one render function.
//
// The server decides what each visitor sees (it evaluates the LaunchDarkly
// flags). This script only renders the state it is sent. It never sees an SDK
// key and never decides a flag value on its own.

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const STORAGE_KEY = "abc-freight-visitor";

  let visitor = readStoredVisitor() || "guest";
  let source = null;
  let lastState = null;
  let feedbackToken = null;

  function readStoredVisitor() {
    try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
  }
  function storeVisitor(key) {
    try { localStorage.setItem(STORAGE_KEY, key); } catch { /* private mode: ignore */ }
  }

  // Build an element from a tag, a className and text. Text only: never innerHTML.
  function cell(text, className) {
    const td = document.createElement("td");
    td.textContent = text ?? "";
    if (className) td.className = className;
    return td;
  }
  function row(cells) {
    const tr = document.createElement("tr");
    cells.forEach((c) => tr.appendChild(c));
    return tr;
  }
  // One footer entry: "key: value" and, when known, the evaluation reason.
  function flagItem(text, reason) {
    const item = document.createElement("span");
    const code = document.createElement("code");
    code.textContent = text;
    item.appendChild(code);
    if (reason) {
      const why = document.createElement("span");
      why.className = "reason";
      why.textContent = reason;
      item.append(" ", why);
    }
    return item;
  }

  function setLive(state, text) {
    $("live").dataset.state = state;
    $("live-text").textContent = text;
  }

  function showPanel(panel, visible) {
    const wasHidden = panel.hidden;
    panel.hidden = !visible;
    if (visible && wasHidden && lastState !== null) {
      // Brief highlight so the audience notices a feature arriving live.
      panel.classList.remove("appear");
      void panel.offsetWidth;
      panel.classList.add("appear");
    }
  }

  function render(state) {
    $("greeting").textContent = state.visitor.key === "guest" ? "Track your loads" : `Welcome back, ${state.visitor.name}`;
    $("org-line").textContent = state.visitor.org_name;

    $("loads-body").replaceChildren(...state.loads.map((l) => row([
      cell(l.id), cell(`${l.origin} → ${l.destination}`), cell(l.status), cell(l.scheduled_arrival), cell(l.driver),
    ])));

    // Part 1: ETA predictions.
    const eta = $("eta-panel");
    if (state.eta) {
      $("eta-body").replaceChildren(...state.eta.map((p) => row([
        cell(p.load_id),
        cell(p.predicted_arrival),
        cell(p.delay_minutes > 0 ? `+${p.delay_minutes} min` : p.delay_minutes < 0 ? `${p.delay_minutes} min` : "—"),
        cell(p.risk, `risk-${p.risk}`),
        cell(p.reason),
      ])));
    } else {
      $("eta-error").hidden = true;
    }
    showPanel(eta, Boolean(state.eta));

    // Part 2: hours of service, US or Canadian rules.
    const hos = $("hos-panel");
    if (state.hos) {
      $("hos-rules").textContent = `Rules: ${state.hos.label}`;
      $("hos-body").replaceChildren(...state.hos.drivers.map((d) => row([
        cell(d.load_id), cell(d.driver), cell(d.drive_left), cell(d.window_left), cell(d.break_due_in ?? "n/a"),
        cell(d.status, d.status === "ok" ? "hos-ok" : d.status === "under 1 hour" ? "hos-warn" : "hos-out"),
      ])));
    }
    showPanel(hos, Boolean(state.hos));

    // AI Config: dispatcher assistant.
    const assistant = $("assistant-panel");
    const dryRun = state.assistant.enabled && state.assistant.dry_run;
    if (state.assistant.enabled) {
      $("assistant-model").textContent = `Model: ${state.assistant.model}${dryRun ? " (dry run)" : ""}`;
    }
    showPanel(assistant, state.assistant.enabled);

    // Footer: each value plus LaunchDarkly's reason for it, so you can see *why* this visitor got it.
    $("flag-values").replaceChildren(
      ...Object.entries(state.flags).map(([k, v]) => flagItem(`${k}: ${JSON.stringify(v)}`, state.reasons[k])),
      flagItem(`dispatcher-assistant: ${state.assistant.enabled ? state.assistant.model : "disabled"}`, dryRun ? "dry run" : ""),
    );

    lastState = state;
  }

  function connect() {
    if (source) source.close();
    setLive("connecting", "Connecting");
    // EventSource reconnects by itself after a drop; the server sends a full
    // snapshot on every (re)connect, so nothing is missed.
    source = new EventSource(`/events?visitor=${encodeURIComponent(visitor)}`);
    source.addEventListener("open", () => setLive("live", "Live"));
    source.addEventListener("error", () => setLive("offline", "Reconnecting"));
    source.addEventListener("state", (event) => {
      setLive("live", "Live");
      render(JSON.parse(event.data));
    });
  }

  async function loadVisitors() {
    const select = $("visitor-select");
    const visitors = await (await fetch("/api/visitors")).json();
    select.replaceChildren(...visitors.map((v) => {
      const option = document.createElement("option");
      option.value = v.key;
      option.textContent = v.key === "guest" ? "Guest (not signed in)" : `${v.name} · ${v.org_name} (${v.plan}, ${v.region})`;
      return option;
    }));
    if (!visitors.some((v) => v.key === visitor)) visitor = "guest";
    select.value = visitor;
    select.addEventListener("change", () => {
      visitor = select.value;
      storeVisitor(visitor);
      lastState = null;
      $("assistant-answer").hidden = true;
      connect();
    });
  }

  function postJson(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  // The "problem release": this button hits the buggy new code path.
  $("eta-refresh").addEventListener("click", async () => {
    const button = $("eta-refresh");
    button.disabled = true;
    try {
      const response = await fetch(`/api/eta/refresh?visitor=${encodeURIComponent(visitor)}`, { method: "POST" });
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))).detail || response.statusText;
        $("eta-error").textContent = `Prediction refresh failed: ${detail}`;
        $("eta-error").hidden = false;
      }
    } finally {
      button.disabled = false;
    }
  });

  // Experimentation: the conversion event, sent server-side to LaunchDarkly.
  $("book-load").addEventListener("click", async () => {
    await postJson("/api/track", { visitor, event: "book-load-clicked" });
    $("book-confirm").hidden = false;
    setTimeout(() => { $("book-confirm").hidden = true; }, 3000);
  });

  $("assistant-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("assistant-input");
    const question = input.value.trim();
    if (!question) return;
    const button = event.submitter;
    button.disabled = true;
    $("assistant-text").textContent = "Thinking…";
    $("assistant-answer").hidden = false;
    $("assistant-thanks").hidden = true;
    try {
      const response = await postJson("/api/assistant", { visitor, question });
      const data = await response.json();
      if (response.ok) {
        $("assistant-text").textContent = data.answer;
        feedbackToken = data.feedback_token;
      } else {
        $("assistant-text").textContent = data.detail || "The assistant is unavailable.";
        feedbackToken = null;
      }
      // Thumbs only for a real model answer: a dry run or an error has nothing to rate.
      document.querySelector("#assistant-answer .feedback").hidden = !feedbackToken;
    } finally {
      button.disabled = false;
    }
  });

  document.querySelectorAll(".feedback button").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!feedbackToken) return;
      await postJson("/api/assistant/feedback", {
        visitor, feedback_token: feedbackToken, positive: button.dataset.positive === "true",
      });
      feedbackToken = null;
      $("assistant-thanks").hidden = false;
    });
  });

  loadVisitors().finally(connect);
})();
