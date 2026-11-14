/* Live-page behaviour. The server-rendered pages remain complete without this file. */
(() => {
  "use strict";

  const main = document.querySelector("main");
  const dot = document.querySelector(".live-dot");
  const banner = document.querySelector(".banner");
  let timer = null;
  let refreshing = false;

  function clock(date) {
    return [date.getHours(), date.getMinutes(), date.getSeconds()]
      .map((part) => String(part).padStart(2, "0")).join(":");
  }

  function live() {
    if (dot) {
      dot.dataset.state = "live";
      dot.textContent = `Live, updated ${clock(new Date())}`;
    }
    if (banner) banner.hidden = true;
  }

  function indicator(state, text) {
    if (dot) {
      dot.dataset.state = state;
      dot.textContent = text;
    }
  }

  function lost() {
    indicator("lost", "Can't reach factory web");
    if (banner) banner.hidden = false;
  }

  function editing() {
    const active = document.activeElement;
    return Boolean(active && active.matches("input, textarea, select, [contenteditable=true]"));
  }

  function formatTimes(root = document) {
    root.querySelectorAll("time[datetime]").forEach((time) => {
      const date = new Date(time.getAttribute("datetime"));
      if (!Number.isNaN(date.getTime())) time.title = date.toLocaleString();
    });
  }

  function setupCopy(root = document) {
    root.querySelectorAll("button.copy").forEach((button) => {
      button.hidden = false;
      if (button.dataset.copyReady) return;
      button.dataset.copyReady = "true";
      button.addEventListener("click", async () => {
        const cmd = button.closest(".cmd");
        const code = cmd && cmd.querySelector("code");
        if (!code) return;
        const original = button.textContent;
        try {
          await navigator.clipboard.writeText(code.textContent);
          button.textContent = "Copied";
        } catch (_) {
          button.textContent = "Copy failed";
        }
        window.setTimeout(() => { button.textContent = original; }, 1500);
      });
    });
  }

  function setupPreview() {
    const preview = document.querySelector("[data-preview]");
    const code = preview && preview.querySelector("code");
    const form = preview && preview.closest("form");
    if (!preview || !code || !form) return;

    const flags = {
      max_cost: "--max-cost",
      parallel: "--parallel",
      max_attempts: "--max-attempts",
      flow: "--flow",
    };
    const managed = new Set(Object.values(flags));
    const initial = code.textContent.trim().split(/\s+/);
    const firstFlag = initial.findIndex((part) => managed.has(part));
    const prefix = firstFlag < 0 ? initial : initial.slice(0, firstFlag);
    const flow = form.elements.namedItem("flow");
    const initialFlow = flow ? flow.value : "";
    const hadFlow = initial.includes("--flow");

    function update() {
      const parts = [...prefix];
      ["max_cost", "parallel", "max_attempts"].forEach((name) => {
        const field = form.elements.namedItem(name);
        if (field && field.value !== "") parts.push(flags[name], field.value);
      });
      if (flow && flow.value && (hadFlow || flow.value !== initialFlow)) {
        parts.push("--flow", flow.value);
      }
      const quiet = form.elements.namedItem("quiet");
      if (quiet && quiet.checked) parts.push("--quiet");
      code.textContent = parts.join(" ");
    }

    form.addEventListener("input", update);
    form.addEventListener("change", update);
    update();
  }

  function followLogs(root = document) {
    root.querySelectorAll("pre[data-follow]").forEach((pre) => {
      pre.scrollTop = pre.scrollHeight;
    });
  }

  function snapshot() {
    const details = new Map();
    main.querySelectorAll("details[id]").forEach((detail) => {
      details.set(detail.id, detail.open);
    });
    const logs = [...main.querySelectorAll("pre[data-follow]")].map((pre) => ({
      position: pre.scrollTop,
      following: pre.scrollHeight - pre.clientHeight - pre.scrollTop <= 2,
    }));
    return {details, logs};
  }

  function restore(state) {
    main.querySelectorAll("details[id]").forEach((detail) => {
      if (state.details.has(detail.id)) detail.open = state.details.get(detail.id);
    });
    [...main.querySelectorAll("pre[data-follow]")].forEach((pre, index) => {
      const old = state.logs[index];
      if (!old || old.following) pre.scrollTop = pre.scrollHeight;
      else pre.scrollTop = old.position;
    });
  }

  function schedule(seconds) {
    window.clearTimeout(timer);
    if (!document.hidden) timer = window.setTimeout(() => refresh(seconds), seconds * 1000);
  }

  async function refresh(seconds) {
    if (refreshing || document.hidden || editing()) {
      schedule(seconds);
      return;
    }
    refreshing = true;
    try {
      const response = await fetch(location.href, {cache: "no-store"});
      if (!response.ok) throw new Error("refresh failed");
      const source = await response.text();
      const page = new DOMParser().parseFromString(source, "text/html");
      const replacement = page.querySelector("main");
      if (!replacement) throw new Error("missing main");
      if (document.hidden) {
        indicator("paused", "Paused");
        return;
      }
      live();
      if (editing()) return;
      const state = snapshot();
      main.replaceChildren(...replacement.childNodes);
      restore(state);
      formatTimes(main);
      setupCopy(main);
    } catch (_) {
      if (document.hidden) indicator("paused", "Paused");
      else lost();
    } finally {
      refreshing = false;
      schedule(seconds);
    }
  }

  formatTimes();
  setupCopy();
  setupPreview();
  followLogs();
  if (document.hidden) indicator("paused", "Paused");
  else live();

  if (main && main.dataset.refresh) {
    const seconds = Number.parseFloat(main.dataset.refresh);
    if (Number.isFinite(seconds) && seconds > 0) {
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
          window.clearTimeout(timer);
          indicator("paused", "Paused");
        } else {
          live();
          refresh(seconds);
        }
      });
      schedule(seconds);
    }
  }
})();
