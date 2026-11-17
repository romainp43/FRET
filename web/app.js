"use strict";
// Aucune donnée utilisateur n'est insérée via innerHTML : tout passe par textContent (anti-XSS).

const $ = (id) => document.getElementById(id);
const eur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n);
const LABELS = {
  transport_base: "Transport", supplement_international: "Supplément international", adr: "Matières dangereuses (ADR)",
  temperature: "Température dirigée", express: "Express", gazole: "Indexation gazole", hayon: "Hayon élévateur",
};
let lastQuote = null;

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => { if (k === "class") node.className = v; else node.setAttribute(k, v); });
  children.flat().forEach((c) => node.append(c));
  return node;
}

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const hint = Array.isArray(data.suggestions) && data.suggestions.length ? " Propositions : " + data.suggestions.join(" · ") : "";
    throw new Error((data.error || "Une erreur est survenue.") + hint);
  }
  return data;
}

function showError(id, msg) { const n = $(id); n.textContent = msg; n.classList.toggle("hidden", !msg); }

async function init() {
  const info = await api("/api/cities");
  const dl = $("cities");
  info.cities.forEach((c) => dl.append(el("option", { value: c })));
  $("places-hint").classList.toggle("hidden", info.coverage.complete);
  ["origin", "destination"].forEach((id) => {
    let t = null;
    $(id).addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(async () => {
        const q = $(id).value.trim();
        if (q.length < 2) return;
        try {
          const r = await api("/api/places?q=" + encodeURIComponent(q));
          dl.replaceChildren(...r.results.map((p) => el("option", { value: p.label }, p.postal ? p.postal : p.country)));
        } catch (e) { /* la saisie reste libre : le serveur valide */ }
      }, 180);
    });
  });
  const box = $("options");
  Object.entries(info.options).forEach(([key, label]) => {
    box.append(el("label", {}, el("input", { type: "checkbox", "data-opt": key }), label));
  });
  const today = new Date(); today.setDate(today.getDate() + 1);
  $("pickup").value = today.toISOString().slice(0, 10);
  $("pickup").min = new Date().toISOString().slice(0, 10);
  document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", syncMode));
  syncMode();
  const qm = location.hash.match(/^#devis=([A-Za-z0-9_-]{8,40})$/);
  if (qm) {
    try { const q = await api("/api/quote/" + qm[1]); lastQuote = q; renderQuote(q, {}); }
    catch (e) { showError("quote-error", "Ce devis a expiré ou est introuvable : refaites une demande."); }
  }
  const code = location.hash.replace("#", "");
  if (/^FR-[0-9A-F]{12}$/.test(code)) { $("track-code").value = code; track(code); }
}

function syncMode() {
  const ltl = document.querySelector("input[name=mode]:checked").value === "LTL";
  $("pallets-label").textContent = ltl ? "Palettes" : "Palettes (facultatif)";
  $("pallets").required = ltl;
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
  if ($("deliver-by").value) body.deliver_by = $("deliver-by").value;
  $("quote-btn").disabled = true;
  try {
    const q = await api("/api/quote", body);
    lastQuote = q;
    renderQuote(q, body);
  } catch (err) { showError("quote-error", err.message); }
  finally { $("quote-btn").disabled = false; }
});

function renderQuote(q, body) {
  const box = $("result");
  box.replaceChildren(
    el("h2", {}, `${q.origin || body.origin} → ${q.destination || body.destination}`),
    el("p", { class: "muted" }, `${q.mode === "FTL" ? "Camion complet" : "Palettes"} · ${q.distance_km} km · livraison estimée sous ${q.transit_days} jour(s)`),
    el("div", { class: "price" }, eur(q.price_ht), el("small", {}, " HT")),
    el("p", { class: "muted" }, q.vat > 0 ? `${eur(q.price_ttc)} TTC (TVA 20 %)` : "Transport international : TVA selon régime applicable (autoliquidation possible)."),
    el("table", { class: "lines" }, ...Object.entries(q.breakdown).map(([k, v]) => el("tr", {}, el("td", {}, LABELS[k] || k), el("td", {}, eur(v))))),
    q.earliest_delivery ? el("p", { class: "muted" }, `Livraison au plus tôt le ${q.earliest_delivery}.`) : "",
    ...(q.warnings || []).map((w) => el("p", { class: "warn" }, w)),
    el("p", { class: "muted" }, `Prix valable ${q.valid_hours} h.`),
  );
  $("book-card").classList.remove("hidden");
  $("match-card").classList.remove("hidden");
  $("match-msg").textContent = "";
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
    pickup_window: `${$("pw-start").value}-${$("pw-end").value}`,
    delivery_window: `${$("dw-start").value}-${$("dw-end").value}`,
    site_contact_name: $("sc-name").value, site_contact_phone: $("sc-phone").value,
    loading_notes: $("notes").value,
    goods_value_eur: $("goods-value").value ? parseFloat($("goods-value").value) : null,
    contact: { name: $("c-name").value, company: $("c-company").value, email: $("c-email").value, phone: $("c-phone").value },
  };
  $("book-btn").disabled = true;
  try {
    const r = await api("/api/book", body);
    if (!r.tracking_code) return;
    location.hash = r.tracking_code;
    $("track-code").value = r.tracking_code;
    $("book-card").replaceChildren(
      el("h2", {}, r.status === "confirmed" ? "Transport confirmé" : "Demande reçue"),
      el("div", { class: "ok-box" }, `Votre code de suivi : ${r.tracking_code}`),
      el("p", { class: "muted" }, "Conservez ce code : il vous permet de suivre l'envoi et de télécharger la lettre de voiture."),
    );
    track(r.tracking_code);
    $("suivi").scrollIntoView({ behavior: "smooth" });
  } catch (err) { showError("book-error", err.message); }
  finally { $("book-btn").disabled = false; }
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

// Cookies : uniquement des traceurs strictement nécessaires (exemptés). Ce panneau sert d'information et de point d'accès « Gérer mes cookies ».
$("cookie-manage").addEventListener("click", (e) => { e.preventDefault(); $("cookie-panel").classList.remove("hidden"); });
$("cookie-close").addEventListener("click", () => $("cookie-panel").classList.add("hidden"));

$("match-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("match-error", "");
  if (!lastQuote) return;
  $("match-btn").disabled = true;
  try {
    const r = await api("/api/ratematch", { quote_id: lastQuote.quote_id, competitor_price_ht: parseFloat($("m-price").value), reference: $("m-ref").value });
    $("match-msg").textContent = r.message;
    if (r.outcome === "matched" || r.outcome === "counter") { lastQuote = r.quote; renderQuote(r.quote, {}); $("match-msg").textContent = r.message; }
  } catch (err) { showError("match-error", err.message); }
  finally { $("match-btn").disabled = false; }
});
