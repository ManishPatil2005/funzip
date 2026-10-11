"use strict";
(async function () {
  const $ = id => document.getElementById(id);
  const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
  let current = null;

  function draw(rep) {
    const p = rep.profile, rows = p.rows, tick = p.tick;
    const rowH = 15, cw = 9.2, left = 74, top = 16;
    const maxCount = Math.max(...rows.map(r => r.count));
    const chartW = left + maxCount * cw + 150, chartH = top + rows.length * rowH + 18;
    const top_price = rows[0].price + tick;
    const y = price => top + ((top_price - price) / tick) * rowH;
    const svg = svgEl("svg", { class: "tpo", viewBox: `0 0 ${chartW} ${chartH}`, role: "img",
      "aria-label": `Market Profile for ${rep.symbol} on ${p.date}` });
    const title = svgEl("title", {});
    title.textContent = `Market Profile ${rep.symbol} ${p.date}: POC ${p.poc}, value area ${p.val} to ${p.vah}`;
    svg.append(title);

    const add = (tag, attrs, text) => { const n = svgEl(tag, attrs); if (text != null) n.textContent = text; svg.append(n); return n; };
    // value area band + POC box
    add("rect", { class: "vaband", x: left - 6, y: y(p.vah), width: chartW - left + 6, height: y(p.val) - y(p.vah) });
    add("rect", { class: "pocbox", x: left - 4, y: y(p.poc + tick), width: maxCount * cw + 10, height: rowH });
    // single-print bars (interior) and tail markers
    p.single_prints.forEach(([lo, hi]) => add("rect", { class: "spbar", x: left - 9, y: y(hi), width: 3, height: y(lo) - y(hi) }));
    // price labels and letters
    rows.forEach((r, i) => {
      const yy = top + i * rowH + rowH - 4;
      if (rows.length <= 70 || i % 2 === 0) add("text", { class: "px", x: 4, y: yy }, r.price.toFixed(tick < 0.1 ? 2 : tick < 1 ? 2 : 1));
      [...r.letters].forEach((ch, j) => add("text", { class: "l" + (LETTERS.indexOf(ch) % 10), x: left + j * cw, y: yy }, ch));
    });
    const xr = left + maxCount * cw + 10;
    // right-hand labels and reference lines
    const inRange = v => v >= p.low - tick && v <= top_price;
    const line = (price, cls, label, lblCls, dx = 0) => {
      if (!inRange(price)) return;
      add("line", { class: cls, x1: left - 6, x2: chartW - 4, y1: y(price), y2: y(price) });
      add("text", { class: "lbl " + lblCls, x: xr + dx, y: y(price) - 2 }, `${label} ${price.toFixed(2)}`);
    };
    line(p.ib.high, "ibline", "IB hi", "iblbl");
    line(p.ib.low, "ibline", "IB lo", "iblbl");
    if (rep.prior) {
      line(rep.prior.vah, "priline", "pVAH", "prilbl");
      line(rep.prior.val, "priline", "pVAL", "prilbl");
      line(rep.prior.poc, "priline", "pPOC", "prilbl");
    }
    add("text", { class: "lbl pocl", x: xr, y: y(p.poc + tick) + rowH - 4 }, `POC ${p.poc.toFixed(2)}`);
    add("text", { class: "lbl", x: xr, y: y(p.vah) + 10 }, `VAH ${p.vah.toFixed(2)}`);
    add("text", { class: "lbl", x: xr, y: y(p.val) - 3 }, `VAL ${p.val.toFixed(2)}`);
    add("text", { class: "lbl openm", x: left - 36, y: y(p.open) + 4 }, "O ▸");
    add("text", { class: "lbl closem", x: xr + 90, y: y(p.close) + 4 }, `◂ C ${p.close.toFixed(2)}`);
    $("chart").replaceChildren(svg);
    $("charttitle").textContent = `${rep.symbol} · ${p.date} · tick ${tick} · ${p.periods.length}/${p.periods_expected} periods${p.complete ? "" : " (session in progress)"}`;
  }

  function side(rep) {
    const p = rep.profile, b = rep.bias;
    $("biascard").replaceChildren(el("div", { class: "biascard" },
      el("div", { class: "biasbig " + b.signal, text: b.signal }),
      el("div", {}, el("div", { text: `Score ${b.score > 0 ? "+" : ""}${b.score}` }),
        el("div", { class: "muted small", text: "Buy at +3 or more; sell at −3 or less" }))));
    const facts = [
      ["Open type", `${p.open_type.type}${p.open_type.direction !== "flat" ? " (" + p.open_type.direction + ")" : ""}`],
      ["Day type", p.day_type], ["Shape", p.shape],
      ["Open location", rep.open_location || "–"], ["Value vs prior", rep.value_relationship || "–"],
      ["POC", p.poc.toFixed(2)], ["Value area", `${p.val.toFixed(2)} – ${p.vah.toFixed(2)}`],
      ["Initial balance", `${p.ib.low.toFixed(2)} – ${p.ib.high.toFixed(2)}`],
      ["IB extension", `▲ ${p.ib.ext_up.toFixed(2)}  ▼ ${p.ib.ext_down.toFixed(2)}`],
      ["High / Low", `${p.high_structure} / ${p.low_structure}`],
    ];
    const r80 = rep.rule_80;
    if (r80 && r80.applicable) facts.push(["80% rule", r80.triggered ? `Triggered (${r80.trigger_period}) → ${r80.target.toFixed(2)}` : `Watching → ${r80.target.toFixed(2)}`]);
    $("facts").replaceChildren(...facts.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })]));
    $("reasons").replaceChildren(...b.reasons.map(r => el("li", {}, el("span", { class: "pts " + (r.points > 0 ? "pos" : r.points < 0 ? "neg" : "muted"), text: (r.points > 0 ? "+" : "") + r.points + " " }), r.why)));
    const lv = b.levels;
    $("levels").replaceChildren(lv ? el("div", { class: "lvl" },
      ...[["Entry", lv.entry], ["Stop", lv.stop], ["Target 1", lv.target1], ["Target 2", lv.target2]].map(([k, v]) => el("div", {}, el("span", { text: k }), fmt(v))),
      el("div", {}, el("span", { text: "R:R to T1" }), lv.risk_reward_t1 == null ? "–" : lv.risk_reward_t1))
      : el("p", { class: "muted", text: "No directional setup: score is inside the neutral band." }));
    $("notes").replaceChildren(...b.notes.map(n => el("li", { text: n })));
    const body = document.querySelector("#history tbody");
    body.replaceChildren(...[...rep.history].reverse().map(h => el("tr", {},
      el("td", { text: h.date }), el("td", { text: h.day_type }), el("td", { text: h.shape }),
      ...[h.val, h.poc, h.vah, h.high, h.low].map(v => el("td", { class: "num", text: fmt(v) })))));
  }

  async function load(date) {
    $("status").textContent = "Loading…";
    const q = new URLSearchParams({ interval: $("interval").value, period: $("period").value, period_minutes: "30" });
    if (date) q.set("date", date);
    try {
      const sym = encodeURIComponent($("symbol").value.trim().toUpperCase());
      const rep = await api(`/api/profile/${sym}?${q}`);
      current = rep; $("view").hidden = false;
      draw(rep); side(rep);
      const dates = [...rep.history.map(h => h.date), rep.profile.date];
      const sel = $("date");
      if (!date) sel.replaceChildren(el("option", { value: "", text: "Latest" }), ...[...dates].reverse().map(d => el("option", { value: d, text: d })));
      $("status").textContent = ""; notify("");
    } catch (e) { $("status").textContent = ""; notify(e.message, "error"); }
  }

  $("pform").addEventListener("submit", e => { e.preventDefault(); load($("date").value || ""); });
  $("date").addEventListener("change", () => load($("date").value));
  $("symbol").addEventListener("change", () => { $("date").replaceChildren(el("option", { value: "", text: "Latest" })); });
  document.addEventListener("keychange", () => load(""));

  const qs = new URLSearchParams(location.search).get("symbol");
  if (qs && /^[A-Za-z0-9&:\-]{1,30}$/.test(qs)) $("symbol").value = qs.toUpperCase();
  try {
    const list = await api("/api/instruments");
    $("symlist").replaceChildren(...list.map(i => el("option", { value: i.symbol, label: `${i.name} (${i.exchange})` })));
  } catch { /* key not set yet */ }
  if (getKey() || qs) load("");
})();
