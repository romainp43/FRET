"use strict";
const $ = (id) => document.getElementById(id);
const eur = (n) => (n == null ? "—" : new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n));

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
  if (!res.ok) throw new Error(data.error || "Erreur");
  return data;
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("login-error");
  err.classList.add("hidden");
  try {
    await api("/api/admin/login", { user: "admin", password: $("pw").value, totp: $("totp").value });
    $("pw").value = ""; $("totp").value = "";
    load();
  } catch (ex) { err.textContent = ex.message; err.classList.remove("hidden"); }
});

const STATUS = { confirmed: "Confirmée", sourcing: "Recherche transporteur", pending_human: "À traiter" };
const CSTATUS = { prospect: "Prospect", pending_review: "À contrôler", verified: "Vérifié", blocked: "Exclu" };
const when = (ts) => new Date(ts * 1000).toLocaleString("fr-FR");

async function load() {
  const [stats, list] = await Promise.all([api("/api/admin/stats"), api("/api/admin/bookings")]);
  $("login").classList.add("hidden");
  $("dash").classList.remove("hidden");
  const tile = (label, value) => el("div", { class: "tile" }, el("b", {}, String(value)), label);
  $("tiles").replaceChildren(
    tile("Réservations", stats.bookings), tile("Confirmées", stats.confirmed), tile("Recherche transporteur", stats.sourcing),
    tile("À traiter (humain)", stats.pending_human), tile("Transporteurs vérifiés", stats.carriers.verified || 0),
    tile("Chiffre d'affaires HT", eur(stats.revenue_ht)), tile("Marge brute HT", eur(stats.margin_ht)),
    tile("Intégrité du journal", stats.audit_intact ? "Intacte" : "ALTÉRÉE"));
  const mails = await api("/api/admin/outbox");
  $("outbox").replaceChildren(...mails.mails.map((m) =>
    el("tr", {}, el("td", {}, new Date(m.created_at * 1000).toLocaleString("fr-FR")), el("td", {}, m.to_addr), el("td", {}, m.subject), el("td", {}, m.status))));
  $("rows").replaceChildren(...list.bookings.map((b) => {
    const tr = el("tr", { class: "click" },
      el("td", {}, String(b.id)), el("td", {}, b.tracking_code), el("td", {}, b.route),
      el("td", {}, el("span", { class: "pill " + b.status }, STATUS[b.status] || b.status)),
      el("td", {}, b.carrier_name || "—"), el("td", {}, eur(b.customer_price_ht)), el("td", {}, eur(b.carrier_price)));
    tr.addEventListener("click", () => detail(b.id));
    return tr;
  }));
  await Promise.all([loadCarriers(), loadMoney()]);
  $("audit").replaceChildren(...stats.audit.map((a) =>
    el("tr", {}, el("td", {}, new Date(a.ts * 1000).toLocaleString("fr-FR")), el("td", {}, a.actor), el("td", {}, a.action), el("td", {}, a.detail || ""))));
}

async function detail(id) {
  const b = await api("/api/admin/booking/" + id);
  const log = b.agent_log;
  const box = $("detail");
  box.classList.remove("hidden");
  box.replaceChildren(
    el("h2", {}, `Réservation ${b.tracking_code}`),
    el("p", {}, `${b.customer.name} (${b.customer.company}) — ${b.customer.email} — ${b.customer.phone}`),
    el("h3", {}, "Agent de conformité — transporteurs écartés"),
    ...(log.rejected_by_compliance.length ? log.rejected_by_compliance.map((r) => el("p", {}, `${r.carrier} : ${r.reasons.join(" ; ")}`)) : [el("p", { class: "muted" }, "Aucun.")]),
    el("h3", {}, "Agent de comparaison — classement"),
    ...log.ranking.map((r, i) => el("p", {}, `${i + 1}. ${r.carrier} — score ${r.score} — ${r.why}`)),
    el("h3", {}, "Agent de négociation"),
    ...log.negotiations.flatMap((n) => [
      el("p", {}, el("b", {}, n.carrier), ` — ${n.accepted ? `accord à ${eur(n.price)} (marge ${eur(n.margin_eur)}, ${n.margin_pct} %)` : "pas d'accord, escalade humaine"} — plafond ${eur(n.ceiling)}`),
      ...n.transcript.map((m) => el("div", { class: "chat" }, el("div", { class: m.role }, `${m.role} : ${m.text}`))),
    ]),
  );
  if (log.inbound) box.append(el("h3", {}, "Réponses de transporteurs"), ...log.inbound.map((i) =>
    el("p", {}, `${i.carrier} : ${eur(i.amount)} (plafond ${eur(i.ceiling)}, canal ${i.channel || "e-mail"})`)));
  if (b.status !== "confirmed") {
    const cid = el("input", { type: "number", placeholder: "N° du transporteur", "aria-label": "N° du transporteur" });
    const amt = el("input", { type: "number", placeholder: "Prix d'achat HT", "aria-label": "Prix d'achat HT" });
    const go = el("button", { type: "button" }, "Attribuer");
    const out = el("div", {});
    go.addEventListener("click", async () => {
      try {
        const r = await api("/api/admin/assign", { code: b.tracking_code, carrier_id: parseInt(cid.value, 10), amount: parseFloat(amt.value) });
        if (r.decision === "accepted") { await load(); detail(id); return; }
        out.replaceChildren(el("div", { class: "err" }, r.reason || (r.decision === "counter" ? `Au-dessus du plafond d'achat (${eur(r.counter_price)}).` : "Non attribué.")));
      } catch (ex) { out.replaceChildren(el("div", { class: "err" }, ex.message)); }
    });
    box.append(el("h3", {}, "Attribution manuelle"),
      el("p", { class: "muted" }, "Le transporteur doit être vérifié et le prix rester sous le plafond qui garantit la marge minimale."),
      el("div", { class: "inline-form" }, cid, amt, go), out);
  }
  if (b.status === "confirmed") {
    const btn = el("button", { class: "ghost" }, "Générer la facture");
    btn.addEventListener("click", () => invoice(b.id, box));
    box.append(btn);
  }
  box.scrollIntoView({ behavior: "smooth" });
}

async function invoice(id, box) {
  const f = await api("/api/admin/invoice/" + id);
  const old = document.getElementById("invoice-view");
  if (old) old.remove();
  const s = f.seller;
  box.append(el("div", { id: "invoice-view", class: "card" },
    el("h3", {}, `Facture ${f.number} du ${f.issued_on}`),
    el("p", {}, `${s.name} — ${s.legal_form} — ${s.address} — SIRET ${s.siret} — TVA ${s.vat_number}`),
    el("p", {}, `Client : ${f.buyer.name} (${f.buyer.company})`),
    el("p", {}, f.line),
    el("p", {}, `Total HT ${eur(f.total_ht)} — TVA ${(f.vat_rate * 100).toFixed(0)} % ${eur(f.vat)} — Total TTC ${eur(f.total_ttc)}`),
    f.vat_note ? el("p", { class: "muted" }, f.vat_note) : "",
    el("p", {}, `Échéance : ${f.due_on}`),
    ...f.legal.map((t) => el("p", { class: "muted" }, t))));
}

async function loadCarriers() {
  const q = new URLSearchParams({ status: $("c-status").value, q: $("c-search").value.trim() });
  const d = await api("/api/admin/carriers?" + q);
  const c = d.counts;
  $("carrier-counts").textContent = `${c.verified || 0} vérifié(s) · ${c.pending_review || 0} dossier(s) à contrôler · ${c.prospect || 0} prospect(s) · ${c.blocked || 0} exclu(s)`
    + (d.demo ? " · réseau de démonstration ACTIF (sociétés fictives)" : "");
  $("carriers").replaceChildren(...d.carriers.map((r) => {
    const tr = el("tr", { class: "click" },
      el("td", {}, String(r.id)), el("td", {}, r.name), el("td", {}, r.base_place),
      el("td", {}, r.km_base == null ? "—" : `${Math.round(r.km_base)} km`), el("td", {}, r.licence_no || "—"),
      el("td", {}, r.insurance_until || "—"), el("td", {}, [r.email, r.phone].filter(Boolean).join(" · ") || "—"),
      el("td", {}, el("span", { class: "pill " + r.status }, CSTATUS[r.status] || r.status)));
    tr.addEventListener("click", () => editCarrier(r));
    return tr;
  }));
}

function editCarrier(r) {
  const box = $("carrier-edit");
  const field = (label, id, value, type = "text") => el("div", {}, el("label", { for: id }, label), el("input", { id, type, value: value || "" }));
  const checks = el("input", { type: "checkbox", id: "e-checks" });
  const out = el("div", {});
  const save = async (status) => {
    try {
      await api("/api/admin/carrier/update", {
        id: r.id, status, checks_done: checks.checked, licence_no: $("e-licence").value, insurance_until: $("e-insurance").value,
        email: $("e-email").value, phone: $("e-phone").value, note: $("e-note").value,
      });
      box.classList.add("hidden");
      await loadCarriers();
    } catch (ex) { out.replaceChildren(el("div", { class: "err" }, ex.message)); }
  };
  const btn = (label, status, cls) => { const b = el("button", { type: "button", class: cls || "" }, label); b.addEventListener("click", () => save(status)); return b; };
  box.classList.remove("hidden");
  box.replaceChildren(
    el("h2", {}, `${r.name} (n° ${r.id})`),
    el("p", { class: "muted" }, `SIRET ${r.siret || "—"} · base ${r.base_place} · ${r.modes}${r.europe ? " · international" : ""} · ${r.equipment || "matériel non renseigné"}`),
    el("div", { class: "inline-form" }, field("N° de licence", "e-licence", r.licence_no), field("Assurance valable jusqu'au", "e-insurance", r.insurance_until, "date"),
      field("E-mail", "e-email", r.email, "email"), field("Téléphone", "e-phone", r.phone), field("Note interne", "e-note", r.note)),
    el("label", { class: "checks" }, checks, " J'ai contrôlé les pièces : licence, attestation d'assurance, Kbis, attestation de vigilance URSSAF"),
    el("div", { class: "actions" }, btn("Valider le transporteur", "verified"), btn("Enregistrer sans changer le statut", undefined, "ghost"), btn("Exclure", "blocked", "ghost")), out);
  box.scrollIntoView({ behavior: "smooth" });
}

async function loadMoney() {
  const d = await api("/api/admin/payables");
  $("payables").replaceChildren(...d.payables.map((p) => {
    const pay = el("button", { type: "button", class: "ghost" }, "Marquer réglé");
    pay.addEventListener("click", async () => { await api("/api/admin/payable/pay", { id: p.id }); loadMoney(); });
    return el("tr", {}, el("td", {}, p.tracking_code), el("td", {}, p.carrier_name || "—"), el("td", {}, eur(p.amount)),
      el("td", {}, p.due_on), el("td", {}, p.status === "paid" ? "Réglé" : pay));
  }));
  $("matches").replaceChildren(...d.price_matches.map((m) => el("tr", {},
    el("td", {}, when(m.created_at)), el("td", {}, `${m.company} — ${m.email}`), el("td", {}, `Devis ${m.quote_id}`), el("td", {}, `Prix concurrent : ${eur(m.competitor_price)}`))));
  $("inbound-quotes").replaceChildren(...d.inbound_quotes.map((q) => el("tr", {},
    el("td", {}, when(q.received_at)), el("td", {}, q.from_addr), el("td", {}, q.status), el("td", {}, q.quote_id || "—"))));
}

$("c-refresh").addEventListener("click", () => loadCarriers());
$("c-status").addEventListener("change", () => loadCarriers());
$("c-import").addEventListener("click", async () => {
  const out = $("c-msg");
  try {
    const r = await api("/api/admin/prospects/import", { radius_km: parseFloat($("c-radius").value) });
    out.replaceChildren(el("div", { class: "ok-box" }, `${r.added} prospect(s) ajouté(s) sur ${r.read} dans le rayon. Aucun n'est vérifié : contrôlez les pièces avant de valider.`));
    $("c-status").value = "prospect";
    await loadCarriers();
  } catch (ex) { out.replaceChildren(el("div", { class: "err" }, ex.message)); }
});
$("intake-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("intake-out");
  try {
    const r = await api("/api/admin/intake", { from: $("i-from").value, text: $("i-text").value });
    const text = r.status === "quoted" ? `Devis envoyé : ${eur(r.price_ht)} HT (${r.fields.origin} → ${r.fields.destination}, ${r.fields.mode}).`
      + (r.assumptions.length ? ` Hypothèses : ${r.assumptions.join(" ; ")}.` : "")
      : r.status === "missing" ? `Informations manquantes, l'agent les a demandées : ${r.missing.join(", ")}.` : `Transmis à un humain : ${r.reason}`;
    out.replaceChildren(el("div", { class: "ok-box" }, text));
    await load();
  } catch (ex) { out.replaceChildren(el("div", { class: "err" }, ex.message)); }
});

load().catch(() => {});   // session déjà valide ? sinon on reste sur le formulaire de connexion
