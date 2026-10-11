"use strict";
(async function () {
  const $ = id => document.getElementById(id);
  const FIELDS = ["close", "open", "high", "low", "volume"];
  const INDS = ["sma", "ema", "rsi", "atr", "adx", "plus_di", "minus_di", "roc", "stoch_k", "stoch_d", "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_mid", "bb_lower", "supertrend", "donchian_high", "donchian_low", "highest_high", "lowest_low", "vwap", "obv", "volume_sma"];
  const NO_PERIOD = ["vwap", "obv", "macd", "macd_signal", "macd_hist"];
  const OPS = [[">", ">"], ["<", "<"], [">=", "≥"], ["<=", "≤"], ["crosses_above", "crosses above"], ["crosses_below", "crosses below"]];
  let templates = [];

  const opt = (v, t) => el("option", { value: v, text: t || v });

  function operandEditor(init) {
    const kind = el("select", { "aria-label": "Operand type" }, opt("field", "Price"), opt("ind", "Indicator"), opt("value", "Number"));
    const field = el("select", { "aria-label": "Price field" }, ...FIELDS.map(f => opt(f)));
    const ind = el("select", { "aria-label": "Indicator" }, ...INDS.map(i => opt(i)));
    const period = el("input", { type: "number", class: "num", min: 1, max: 400, value: 14, "aria-label": "Period" });
    const value = el("input", { type: "number", class: "num", step: "any", value: 0, "aria-label": "Number" });
    const mult = el("input", { type: "number", class: "num", step: "any", value: 1, title: "Multiplier", "aria-label": "Multiplier" });
    const shift = el("input", { type: "number", class: "num", min: 0, max: 20, value: 0, title: "Bars back", "aria-label": "Bars back" });
    const box = el("div", { class: "operand" }, kind, field, ind, period, value, el("span", { class: "muted", text: "×" }), mult, el("span", { class: "muted", text: "ago" }), shift);
    const sync = () => {
      field.hidden = kind.value !== "field"; ind.hidden = kind.value !== "ind"; value.hidden = kind.value !== "value";
      period.hidden = kind.value !== "ind" || NO_PERIOD.includes(ind.value);
    };
    [kind, ind].forEach(n => n.addEventListener("change", sync));
    if (init) {
      if (init.field) { kind.value = "field"; field.value = init.field; }
      else if (init.ind) { kind.value = "ind"; ind.value = init.ind; period.value = init.period || 14; }
      else if (init.value !== undefined) { kind.value = "value"; value.value = init.value; }
      mult.value = init.mult ?? 1; shift.value = init.shift ?? 0;
    }
    sync();
    box.read = () => {
      const o = kind.value === "field" ? { field: field.value } : kind.value === "ind"
        ? { ind: ind.value, ...(NO_PERIOD.includes(ind.value) ? {} : { period: Number(period.value) }) } : { value: Number(value.value) };
      if (Number(mult.value) !== 1) o.mult = Number(mult.value);
      if (Number(shift.value) > 0) o.shift = Number(shift.value);
      return o;
    };
    return box;
  }

  function condRow(container, init) {
    const left = operandEditor(init && init.left);
    const op = el("select", { "aria-label": "Comparison" }, ...OPS.map(([v, t]) => opt(v, t)));
    const right = operandEditor(init && init.right || { value: 0 });
    if (init) op.value = init.op;
    const row = el("div", { class: "cond" }, left, op, right,
      el("button", { type: "button", class: "remove ghost", "aria-label": "Remove condition", text: "✕", onclick: () => row.remove() }));
    row.read = () => ({ left: left.read(), op: op.value, right: right.read() });
    container.append(row);
  }

  const readGroup = (containerId, modeId) => {
    const conds = [...$(containerId).children].map(r => r.read());
    return conds.length ? { [$(modeId).value]: conds } : null;
  };

  function definition() {
    const d = { name: $("name").value.trim(), description: $("desc").value.trim() };
    const buy = readGroup("buyconds", "buymode"), sell = readGroup("sellconds", "sellmode");
    if (buy) d.buy = buy; if (sell) d.sell = sell;
    return d;
  }

  function loadDef(d) {
    $("name").value = d.name || ""; $("desc").value = d.description || "";
    for (const side of ["buy", "sell"]) {
      $(side + "conds").replaceChildren();
      const g = d[side];
      if (!g) continue;
      const mode = g.any && g.any.length && !(g.all && g.all.length) ? "any" : "all";
      $(side + "mode").value = mode;
      (g[mode] || []).forEach(c => condRow($(side + "conds"), c));
    }
    $("json").value = JSON.stringify(d, null, 2);
  }

  async function refreshSaved() {
    try {
      const items = await api("/api/custom");
      $("saved").replaceChildren(...(items.length ? items.map(s => el("div", { class: "saved" },
        el("div", {}, el("strong", { text: s.name }), el("div", { class: "muted", text: s.description || "" })),
        el("div", {},
          el("button", { type: "button", class: "ghost", text: "Edit", onclick: () => loadDef(s) }), " ",
          el("button", { type: "button", class: "ghost remove", text: "Delete", onclick: async () => {
            if (!confirm("Delete strategy '" + s.name + "'?")) return;
            try { await api("/api/custom/" + encodeURIComponent(s.name), { method: "DELETE" }); refreshSaved(); }
            catch (e) { notify(e.message, "error"); }
          } })))) : [el("p", { class: "muted", text: "No saved strategies yet." })]));
    } catch (e) { $("saved").replaceChildren(el("p", { class: "muted", text: e.message })); }
  }

  async function init() {
    try {
      const [cat, meta] = await Promise.all([api("/api/strategies"), api("/api/meta")]);
      templates = cat.templates;
      $("template").replaceChildren(opt("", "Load a template…"), ...templates.map((t, i) => opt(i, t.name)));
      $("testint").replaceChildren(...["1d", "60m", "15m", "5m"].filter(i => meta.intervals[i]).map(i => opt(i)));
      refreshSaved();
    } catch (e) { notify(e.message, "error"); }
  }

  $("addbuy").addEventListener("click", () => condRow($("buyconds")));
  $("addsell").addEventListener("click", () => condRow($("sellconds")));
  $("template").addEventListener("change", e => { if (e.target.value !== "") loadDef(templates[Number(e.target.value)]); });
  $("importjson").addEventListener("click", () => {
    try { loadDef(JSON.parse($("json").value)); notify("Loaded from JSON.", "ok"); } catch { notify("Invalid JSON.", "error"); }
  });
  $("save").addEventListener("click", async () => {
    const d = definition(); $("json").value = JSON.stringify(d, null, 2);
    try { await api("/api/custom", { method: "POST", body: JSON.stringify(d) }); notify("Saved '" + d.name + "'.", "ok"); refreshSaved(); }
    catch (e) { notify(e.message, "error"); }
  });
  $("test").addEventListener("click", async () => {
    const d = definition(); $("json").value = JSON.stringify(d, null, 2);
    const p = new URLSearchParams({ symbol: $("testsym").value.trim().toUpperCase(), interval: $("testint").value, period: $("testint").value === "1d" ? "1y" : "1mo" });
    try {
      const r = await api("/api/custom/test?" + p, { method: "POST", body: JSON.stringify(d) });
      $("testout").hidden = false;
      $("testout").textContent = `${r.symbol} @ ${r.as_of}\nSignal: ${r.signal}\n${r.reason || "No rule satisfied on the latest bar."}\nClose: ${r.metrics.close}`;
      notify("");
    } catch (e) { notify(e.message, "error"); }
  });
  document.addEventListener("keychange", init);
  condRow($("buyconds")); condRow($("sellconds"));
  init();
})();
