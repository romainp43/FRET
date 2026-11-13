"use strict";
// Aucune donnée utilisateur n'est insérée via innerHTML : tout passe par textContent (anti-XSS).

const $ = (id) => document.getElementById(id);
const eur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n);
const LABELS = {
  transport_base: "Transport", supplement_international: "Supplément international", adr: "Matières dangereuses (ADR)",
  temperature: "Température dirigée", express: "Express", gazole: "Indexation gazole", hayon: "Hayon élévateur",
  plateau: "Plateau",
};
const MODES = { FTL: "Camion complet", PTL: "Lot partiel", LTL: "Palettes" };
let lastQuote = null;

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => { if (k === "class") node.className = v; else node.setAttribute(k, v); });
  children.flat().forEach((c) => node.append(c));
  return node;
}

async function api(path, body) {
  // L'en-tête X-Requested-With rattache la réservation au compte client connecté, s'il y en a un.
  const opts = { headers: { "X-Requested-With": "fretrau", "Content-Type": "application/json" }, credentials: "same-origin" };
  if (body !== undefined) { opts.method = "POST"; opts.body = JSON.stringify(body); }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(data.error || "Une erreur est survenue."); e.status = res.status; throw e; }
  return data;
}

function showError(id, msg) { const n = $(id); n.textContent = msg; n.classList.toggle("hidden", !msg); }

async function init() {
  const info = await api("/api/cities");
  const dl = $("cities");
  info.cities.forEach((c) => dl.append(el("option", { value: c })));
  const box = $("options");
  Object.entries(info.options).forEach(([key, label]) => {
    box.append(el("label", {}, el("input", { type: "checkbox", "data-opt": key }), label));
  });
  const today = new Date(); today.setDate(today.getDate() + 1);
  $("pickup").value = today.toISOString().slice(0, 10);
  $("pickup").min = new Date().toISOString().slice(0, 10);
  document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", syncMode));
  syncMode();
  if (info.quote_email) { $("mail-quote-addr").textContent = info.quote_email; $("mail-quote").classList.remove("hidden"); }
  const linked = new URLSearchParams(location.search).get("devis");
  if (linked) {                                   // lien reçu dans un devis envoyé par e-mail
    try {
      const q = await api("/api/quote/" + encodeURIComponent(linked));
      if (q.booked) showError("quote-error", "Ce devis a déjà été réservé.");
      else { lastQuote = q; renderQuote(q); }
    } catch (err) { showError("quote-error", err.message); }
  }
  const code = location.hash.replace("#", "");
  if (/^FR-[0-9A-F]{12}$/.test(code)) { $("track-code").value = code; track(code); }
}

function syncMode() {
  const mode = document.querySelector("input[name=mode]:checked").value;
  $("pallets-label").textContent = mode === "FTL" ? "Palettes (facultatif)" : mode === "PTL" ? "Palettes (4 à 20)" : "Palettes";
  $("pallets").required = mode !== "FTL";
}

$("quote-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("quote-error", "");
  const mode = document.querySelector("input[name=mode]:checked").value;
  const options = {};
  document.querySelectorAll("[data-opt]").forEach((c) => { options[c.dataset.opt] = c.checked; });
  const pallets = $("pallets").value ? parseInt($("pallets").value, 10) : null;
  const body = {
    origin: $("origin").value.trim(), destination: $("destination").value.trim(), mode, pallets,
    weight_kg: parseFloat($("weight").value), pickup_date: $("pickup").value, options,
  };
  $("quote-btn").disabled = true;
  try {
    const q = await api("/api/quote", body);
    lastQuote = q;
    renderQuote(q);
  } catch (err) { showError("quote-error", err.message); }
  finally { $("quote-btn").disabled = false; }
});

function renderQuote(q) {
  const box = $("result");
  const lower = el("input", { type: "number", min: "20", step: "1", placeholder: "Prix HT reçu ailleurs", "aria-label": "Prix HT reçu ailleurs" });
  const lowerBtn = el("button", { type: "button", class: "ghost" }, "Demander un alignement");
  const lowerMsg = el("div", {});
  lowerBtn.addEventListener("click", async () => {
    try {
      await api("/api/my/price-match", { quote_id: q.quote_id, competitor_price: parseFloat(lower.value) });
      lowerMsg.replaceChildren(el("div", { class: "ok-box" }, "Demande transmise : un conseiller vous répond par e-mail."));
    } catch (err) {
      lowerMsg.replaceChildren(el("div", { class: "err" }, err.status === 401 ? "Connectez-vous à votre espace client pour demander un alignement." : err.message));
    }
  });
  box.replaceChildren(
    el("h2", {}, `${q.origin} → ${q.destination}`),
    el("p", { class: "muted" }, `${MODES[q.mode] || q.mode} · ${q.distance_km} km · enlèvement le ${new Date(q.pickup_date + "T12:00:00").toLocaleDateString("fr-FR")} · livraison estimée sous ${q.transit_days} jour(s)`),
    el("div", { class: "price" }, eur(q.price_ht), el("small", {}, " HT")),
    el("p", { class: "muted" }, q.vat > 0 ? `${eur(q.price_ttc)} TTC (TVA 20 %)` : "Transport international : TVA selon régime applicable (autoliquidation possible)."),
    el("table", { class: "lines" }, ...Object.entries(q.breakdown).map(([k, v]) => el("tr", {}, el("td", {}, LABELS[k] || k), el("td", {}, eur(v))))),
    el("p", { class: "muted" }, `Prix valable ${q.valid_hours} h. Le prix réservé est le prix facturé, tant que l'envoi reste conforme à votre demande.`),
    el("p", { class: "muted" }, "Vous avez reçu un prix inférieur pour le même envoi ?"),
    el("div", { class: "actions" }, lower, lowerBtn), lowerMsg,
  );
  $("book-card").classList.remove("hidden");
  $("result-section").hidden = false;
  $("result-section").scrollIntoView({ behavior: "smooth" });
}

$("book-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("book-error", "");
  if (!lastQuote) return;
  const body = {
    quote_id: lastQuote.quote_id, accept_cgv: $("cgv").checked,
    website: document.querySelector("[name=website]").value,
    pickup_address: $("pickup-address").value, delivery_address: $("delivery-address").value, goods: $("goods").value,
    contact: { name: $("c-name").value, company: $("c-company").value, email: $("c-email").value, phone: $("c-phone").value },
  };
  $("book-btn").disabled = true;
  try {
    const r = await api("/api/book", body);
    if (!r.tracking_code) return;
    location.hash = r.tracking_code;
    $("track-code").value = r.tracking_code;
    $("book-card").replaceChildren(
      el("h2", {}, r.status === "confirmed" ? "Transport confirmé" : r.status === "sourcing" ? "Réservation enregistrée" : "Demande reçue"),
      el("div", { class: "ok-box" }, `Votre code de suivi : ${r.tracking_code}`),
      el("p", { class: "muted" }, "Conservez ce code : il vous permet de suivre l'envoi et de télécharger la lettre de voiture."),
    );
    track(r.tracking_code);
    $("suivi").scrollIntoView({ behavior: "smooth" });
  } catch (err) { showError("book-error", err.message); }
  finally { const btn = $("book-btn"); if (btn) btn.disabled = false; }
});

let timer = null;
async function track(code) {
  clearTimeout(timer);
  showError("track-error", "");
  try {
    const t = await api("/api/track/" + encodeURIComponent(code));
    const out = $("track-result");
    out.replaceChildren(
      el("h3", {}, `${t.origin} → ${t.destination}`),
      t.message ? el("p", { class: "muted" }, t.message) : el("ul", { class: "timeline" },
        ...t.events.map((ev) => el("li", { class: ev.done ? "done" : "" }, ev.label))),
      t.status === "confirmed" ? el("a", { class: "btn", href: "/api/doc/" + encodeURIComponent(code), target: "_blank", rel: "noopener" }, "Lettre de voiture") : "",
    );
    if (t.events.some((ev) => !ev.done)) timer = setTimeout(() => track(code), 5000);
  } catch (err) { $("track-result").replaceChildren(); showError("track-error", err.message); }
}

$("track-form").addEventListener("submit", (e) => {
  e.preventDefault();
  track($("track-code").value.trim().toUpperCase());
});

init().catch(() => showError("quote-error", "Service momentanément indisponible."));
