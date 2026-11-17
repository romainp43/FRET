"use strict";
// Aides communes aux pages secondaires : appels JSON, construction DOM sans innerHTML (pas d'injection possible).
window.FR = (function () {
  const $ = (id) => document.getElementById(id);
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, v));
    kids.flat().forEach((k) => n.append(k instanceof Node ? k : document.createTextNode(String(k))));
    return n;
  }
  async function api(path, body, method) {
    const res = await fetch(path, { method: method || (body === undefined ? "GET" : "POST"),
      headers: { "Content-Type": "application/json", "X-Requested-With": "fretrau" }, body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Une erreur est survenue.");
    return data;
  }
  function err(id, text) { const e = $(id); e.textContent = text || ""; e.classList.toggle("hidden", !text); }
  return { $, el, api, err };
})();
