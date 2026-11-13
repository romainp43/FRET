"use strict";
// Fonctions partagées par les espaces client et transporteur.
// Aucune donnée n'est insérée via innerHTML : tout passe par textContent (anti-XSS).
const $ = (id) => document.getElementById(id);
const eur = (n) => (n == null ? "—" : new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n));
const frDate = (iso) => (iso ? new Date(iso + "T12:00:00").toLocaleDateString("fr-FR") : "—");
const MODES = { FTL: "Camion complet", PTL: "Lot partiel", LTL: "Palettes" };
const OPTION_LABELS = { adr: "ADR", tail_lift: "Hayon", temperature: "Température dirigée", urgent: "Express", flatbed: "Plateau" };

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => { if (k === "class") node.className = v; else node.setAttribute(k, v); });
  children.flat().forEach((c) => node.append(c));
  return node;
}

async function api(path, body) {
  const opts = { headers: { "X-Requested-With": "fretrau", "Content-Type": "application/json" }, credentials: "same-origin" };
  if (body !== undefined) { opts.method = "POST"; opts.body = JSON.stringify(body); }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(data.error || "Une erreur est survenue."); e.status = res.status; throw e; }
  return data;
}

function showError(id, msg) { const n = $(id); n.textContent = msg || ""; n.classList.toggle("hidden", !msg); }

function onSubmit(formId, errorId, handler) {
  $(formId).addEventListener("submit", async (e) => {
    e.preventDefault();
    showError(errorId, "");
    const btn = e.target.querySelector("button[type=submit]");
    if (btn) btn.disabled = true;
    try { await handler(e.target); } catch (err) { showError(errorId, err.message); }
    finally { if (btn) btn.disabled = false; }
  });
}

async function logout() { await api("/api/account/logout", {}); location.reload(); }
