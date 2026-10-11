"use strict";
(async function () {
  const $ = id => document.getElementById(id);
  let meta = null, catalogue = null;

  function fillPeriods() {
    const periods = meta.intervals[$("interval").value];
    $("period").replaceChildren(...periods.map(p => el("option", { value: p, text: p })));
    if (periods.includes("1y") && $("interval").value === "1d") $("period").value = "1y";
    else if (periods.includes("5d")) $("period").value = periods.includes("1mo") ? "1mo" : "5d";
  }

  function strategyRow(s, name, defaults, kind) {
    const cb = el("input", { type: "checkbox", "data-kind": kind, "data-id": name, id: "s_" + kind + "_" + name });
    const row = el("div", { class: "strat" }, cb,
      el("label", { for: cb.id }, el("span", { text: s.name }), el("span", { class: "cat", text: s.category + (s.intraday_only ? " · intraday" : "") })));
    if (defaults && Object.keys(defaults).length) {
      const box = el("div", { class: "params" });
      for (const [k, v] of Object.entries(defaults)) {
        box.append(el("label", {}, k, el("input", { type: "number", step: "any", min: "0.0001", max: "1000", value: v, "data-param": k, "data-default": v })));
      }
      row.append(el("details", {}, el("summary", { text: "Parameters" }), box));
    }
    return row;
  }

  async function load() {
    try {
      [meta, catalogue] = await Promise.all([api("/api/meta"), api("/api/strategies")]);
      $("interval").replaceChildren(...Object.keys(meta.intervals).map(i => el("option", { value: i, text: i })));
      $("interval").value = "1d";
      fillPeriods();
      $("strategies").replaceChildren(...catalogue.builtin.map(s => {
        const row = strategyRow(s, s.id, s.params, "builtin");
        row.querySelector("label").append(el("span", { class: "muted", text: s.description }));
        return row;
      }));
      const customs = await api("/api/custom");
      if (customs.length) {
        $("customs").replaceChildren(...customs.map(c => strategyRow({ name: c.name, category: "Custom" }, c.name, null, "custom")));
      }
      notify("");
    } catch (e) { notify(e.message, "error"); }
  }

  function collect() {
    const builtin = [], params = {}, custom = [];
    document.querySelectorAll("input[type=checkbox]:checked").forEach(cb => {
      if (cb.dataset.kind === "custom") { custom.push(cb.dataset.id); return; }
      builtin.push(cb.dataset.id);
      const over = {};
      cb.closest(".strat").querySelectorAll("input[data-param]").forEach(inp => {
        if (inp.value !== "" && Number(inp.value) !== Number(inp.dataset.default)) over[inp.dataset.param] = Number(inp.value);
      });
      if (Object.keys(over).length) params[cb.dataset.id] = over;
    });
    return { builtin, params, custom };
  }

  function render(data) {
    $("resultpanel").hidden = false;
    $("resulttitle").textContent = `Results: ${data.matches} match${data.matches === 1 ? "" : "es"} of ${data.scanned} scanned (${data.interval}, ${data.period})`;
    const body = document.querySelector("#results tbody");
    const rows = data.results.map(r => {
      const sig = el("td", {});
      if (r.error) sig.append(el("span", { class: "muted", text: r.error }));
      else if (!r.hits.length) sig.append(el("span", { class: "muted", text: "No signal" }));
      r.hits.forEach(h => sig.append(el("div", { class: "hit" },
        el("span", { class: "badge " + h.signal, text: h.signal }), el("strong", { text: h.strategy }),
        el("div", { class: "why", text: h.reason }))));
      const sym = el("td", {}, el("strong", { text: r.symbol }), r.proxy ? el("span", { class: "tag", text: "proxy" }) : null);
      const chg = el("td", { class: "num " + (r.change_pct >= 0 ? "pos" : "neg"), text: r.change_pct == null ? "–" : (r.change_pct >= 0 ? "+" : "") + fmt(r.change_pct) });
      const link = el("td", {}, r.error ? "" : el("a", { href: "/profile?symbol=" + encodeURIComponent(r.symbol), text: "Profile" }));
      return el("tr", {}, sym, el("td", { class: "num", text: fmt(r.price) }), chg, sig, link);
    });
    body.replaceChildren(...rows);
    if (!data.results.length) body.append(el("tr", {}, el("td", { colspan: 5, class: "muted", text: "Nothing matched." })));
  }

  async function run() {
    const sel = collect();
    if (!sel.builtin.length && !sel.custom.length) { notify("Select at least one strategy.", "error"); return; }
    const raw = $("symbols").value.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
    const body = {
      interval: $("interval").value, period: $("period").value, strategies: sel.builtin, params: sel.params, custom: sel.custom,
      ...(raw.length ? { symbols: raw } : { universe: $("universe").value }),
      ...($("signal").value ? { signal: $("signal").value } : {}),
    };
    $("run").disabled = true; $("status").textContent = "Scanning… this can take up to a minute for large universes.";
    try {
      render(await api("/api/scan", { method: "POST", body: JSON.stringify(body) }));
      notify(""); $("status").textContent = "";
    } catch (e) { notify(e.message, "error"); $("status").textContent = ""; }
    finally { $("run").disabled = false; }
  }

  $("interval").addEventListener("change", fillPeriods);
  $("run").addEventListener("click", run);
  $("selall").addEventListener("click", () => document.querySelectorAll("#strategies input[type=checkbox]").forEach(c => (c.checked = true)));
  $("selnone").addEventListener("click", () => document.querySelectorAll("input[type=checkbox]").forEach(c => (c.checked = false)));
  document.addEventListener("keychange", load);
  load();
})();
