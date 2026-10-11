"use strict";
/* Shared helpers. DOM is built with textContent only (no innerHTML) to prevent XSS. */
const KEY_STORE = "scanner.apikey";

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null) node.append(c.nodeType ? c : document.createTextNode(String(c)));
  return node;
}

function svgEl(tag, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  return node;
}

function getKey() { try { return sessionStorage.getItem(KEY_STORE) || ""; } catch { return ""; } }
function setKey(v) { try { sessionStorage.setItem(KEY_STORE, v); } catch { /* storage blocked */ } }

function notify(message, kind) {
  const box = document.getElementById("notice");
  if (!box) return;
  box.textContent = message || "";
  box.className = "notice" + (kind ? " " + kind : "");
  box.hidden = !message;
}

async function api(path, options = {}) {
  const headers = { "X-API-Key": getKey() };
  if (options.body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...options, headers, credentials: "omit" });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error body */ }
  if (!res.ok) {
    let msg = data && data.detail ? data.detail : res.statusText;
    if (Array.isArray(msg)) msg = msg.map(e => (e.loc || []).slice(-1) + ": " + e.msg).join("; ");
    if (res.status === 401) msg = "Invalid or missing API key. Enter it at the top right.";
    if (res.status === 429) msg = "Too many requests; please wait a moment.";
    throw new Error(msg);
  }
  return data;
}

function fmt(n, d = 2) { return n == null || Number.isNaN(n) ? "–" : Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }); }

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("apikey");
  const form = document.getElementById("keyform");
  if (input && getKey()) input.value = getKey();
  if (form) form.addEventListener("submit", e => {
    e.preventDefault();
    setKey(input.value.trim());
    notify("API key set for this browser tab.", "ok");
    document.dispatchEvent(new CustomEvent("keychange"));
  });
});
