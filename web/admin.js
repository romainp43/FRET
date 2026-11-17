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
    await api("/api/admin/login", { user: $("user").value.trim(), password: $("pw").value, totp: $("totp").value });
    $("pw").value = ""; $("totp").value = "";
    load();
  } catch (ex) { err.textContent = ex.message; err.classList.remove("hidden"); }
});

let ROLE = "";
const optional = (p) => api(p).catch(() => null);   // une section interdite au rôle courant est simplement masquée

async function load() {
  const me = await api("/api/admin/me");
  ROLE = me.role;
  const [stats, list] = await Promise.all([api("/api/admin/stats"), api("/api/admin/bookings")]);
  $("login").classList.add("hidden");
  $("dash").classList.remove("hidden");
  const tile = (label, value) => el("div", { class: "tile" }, el("b", {}, String(value)), label);
  $("tiles").replaceChildren(
    tile("Réservations", stats.bookings), tile("Confirmées", stats.confirmed), tile("À traiter (humain)", stats.pending_human),
    tile("Chiffre d'affaires HT", eur(stats.revenue_ht)), tile("Marge brute HT", eur(stats.margin_ht)),
    tile("Intégrité du journal", stats.audit_intact ? "Intacte" : "ALTÉRÉE"),
    tile("Communes disponibles", stats.places_complete ? String(stats.places) : `${stats.places} (référentiel complet NON installé)`));
  const mails = (await optional("/api/admin/outbox")) || { mails: [] };
  $("outbox").replaceChildren(...mails.mails.map((m) =>
    el("tr", {}, el("td", {}, new Date(m.created_at * 1000).toLocaleString("fr-FR")), el("td", {}, m.to_addr), el("td", {}, m.subject), el("td", {}, m.status))));
  $("rows").replaceChildren(...list.bookings.map((b) => {
    const tr = el("tr", { class: "click" },
      el("td", {}, String(b.id)), el("td", {}, b.tracking_code), el("td", {}, b.route),
      el("td", {}, el("span", { class: "pill " + b.status }, b.status === "confirmed" ? "Confirmée" : "À traiter")),
      el("td", {}, b.carrier_name || "—"), el("td", {}, eur(b.customer_price_ht)), el("td", {}, eur(b.carrier_price)));
    tr.addEventListener("click", () => detail(b.id));
    return tr;
  }));
  const pay = (ROLE === "admin" || ROLE === "finance") ? await optional("/api/admin/payables") : null;
  $("payables-box").classList.toggle("hidden", !pay);
  if (pay) {
    $("payables-total").textContent = `À payer (HT) : ${eur(pay.total_due_ht)} — paiement dû à la confirmation de livraison, sous 30 jours maximum.`;
    $("payables").replaceChildren(...pay.payables.map((p) => {
      const input = el("input", { placeholder: "Référence du virement", maxlength: "80" });
      const btn = el("button", { class: "ghost" }, "Marquer payé");
      btn.addEventListener("click", async () => {
        try { await api("/api/admin/payables/pay", { id: p.id, reference: input.value }); load(); }
        catch (e) { btn.textContent = e.message; }
      });
      return el("tr", {}, el("td", {}, String(p.id)), el("td", {}, p.carrier_name || ""), el("td", {}, eur(p.amount_ht)),
        el("td", {}, "échéance " + p.due_on), el("td", {}, p.status === "paid" ? `payé (${p.payment_ref})` : el("span", {}, input, btn)));
    }));
  }
  await loadOutcomes();
  await loadLeads();
  $("audit").replaceChildren(...stats.audit.map((a) =>
    el("tr", {}, el("td", {}, new Date(a.ts * 1000).toLocaleString("fr-FR")), el("td", {}, a.actor), el("td", {}, a.action), el("td", {}, a.detail || ""))));
}

async function detail(id) {
  let b;
  try { b = await api("/api/admin/booking/" + id); } catch (e) { const d = $("detail"); d.classList.remove("hidden"); d.replaceChildren(el("p", { class: "err" }, e.message)); return; }
  const log = b.agent_log;
  const box = $("detail");
  box.classList.remove("hidden");
  box.replaceChildren(
    el("h2", {}, `Réservation ${b.tracking_code}`),
    el("p", {}, `${b.customer.name} (${b.customer.company}) — ${b.customer.email} — ${b.customer.phone}`),
    el("h3", {}, "Agent de conformité — transporteurs écartés"),
    ...(log.rejected_by_compliance.length ? log.rejected_by_compliance.map((r) => el("p", {}, `${r.carrier} : ${r.reasons.join(" ; ")}`)) : [el("p", { class: "muted" }, "Aucun.")]),
    ...(log.alerts && log.alerts.length ? [el("h3", {}, "Alertes"), ...log.alerts.map((a) => el("p", { class: "warn" }, a))] : []),
    ...(log.cost_crosscheck && log.cost_crosscheck.applicable ? [el("h3", {}, "Second avis de coût (bottom-up)"),
      el("p", {}, `Marché ${eur(log.cost_crosscheck.market_eur)} · reconstitué ${eur(log.cost_crosscheck.bottom_up_eur)} · rapport ${log.cost_crosscheck.ratio}`)] : []),
    ...(log.rejected_by_risk && log.rejected_by_risk.length ? [el("h3", {}, "Agent de risque — transporteurs écartés"),
      ...log.rejected_by_risk.map((r) => el("p", {}, `${r.carrier} : ${r.reasons.join(" ; ")}`))] : []),
    el("h3", {}, "Agent de comparaison — classement"),
    ...log.ranking.map((r, i) => el("p", {}, `${i + 1}. ${r.carrier} — score ${r.score} — ${r.why}`)),
    ...(log.decision ? [el("h3", {}, "Agent de décision — offres comparées"),
      ...log.decision.candidates.map((c) => el("p", {}, `${c.carrier} — ${c.accepted ? `offre ${eur(c.price)}, coût attendu ${eur(c.expected_cost)}` : "pas d'accord"}${c.carrier === log.decision.chosen ? " ← retenu" : ""}`)),
      log.robustness ? el("p", { class: "muted" }, `Stabilité du classement sous 4 pondérations : ${Math.round(log.robustness.stability * 100)} %${log.robustness.fragile ? " (choix fragile)" : ""}`) : ""] : []),
    el("h3", {}, "Agent de négociation"),
    ...log.negotiations.flatMap((n) => [
      el("p", {}, el("b", {}, n.carrier), ` — ${n.accepted ? `accord à ${eur(n.price)} (marge ${eur(n.margin_eur)}, ${n.margin_pct} %)` : "pas d'accord, escalade humaine"} — plafond ${eur(n.ceiling)}`),
      ...n.transcript.map((m) => el("div", { class: "chat" }, el("div", { class: m.role }, `${m.role} : ${m.text}`))),
    ]),
  );
  if (b.status === "confirmed" && (ROLE === "admin" || ROLE === "finance")) {
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

load().catch(() => {});   // session déjà valide ? sinon on reste sur le formulaire de connexion

const when = (t) => new Date(t * 1000).toLocaleString("fr-FR");

function actions(buttons) {
  return el("div", {}, ...buttons.map(([label, fn]) => {
    const b = el("button", { class: "ghost" }, label);
    b.addEventListener("click", async () => { try { await fn(); loadLeads(); } catch (e) { b.textContent = e.message; } });
    return b;
  }));
}

async function loadLeads() {
  const [apps, claims, contacts, chain] = await Promise.all([
    optional("/api/admin/carriers"), optional("/api/admin/claims"), optional("/api/admin/contacts"), optional("/api/admin/chaining")]);
  const rfqs = await optional("/api/admin/rfq");
  $("leads-box").classList.toggle("hidden", !(apps || claims || contacts || chain || rfqs));
  if (rfqs) {
    const c = rfqs.calibration;
    $("rfq-list").replaceChildren(
      el("p", { class: "muted small" }, c.n ? `Prix réels reçus : ${c.n} (rapport médian prix réel / estimation : ${c.median_ratio}). ${c.reliable ? "" : c.note}` : "Aucune réponse chiffrée pour l'instant."),
      ...rfqs.rfqs.map((r) => el("p", {}, `${r.ref} — ${r.lane.origin} → ${r.lane.destination} : ${r.targets} sollicités, ${r.replies.length} réponse(s), meilleur prix ${eur(r.best)} (estimation du modèle ${eur(r.estimate_eur)}) — ${r.status === "draft" ? "brouillon" : "envoyée"}`)));
  }
  const empty = (t) => el("p", { class: "muted" }, t);
  if (apps) {
    $("applications").replaceChildren(...(apps.applications.length ? apps.applications.map((a) => {
      const d = a.data, note = el("input", { placeholder: "Note : ce que vous avez vérifié (SIREN, licence, assurance, VIES)", maxlength: "300" });
      return el("div", { class: "card" },
        el("b", {}, `#${a.id} ${d.company} (${d.country})`), ` — ${a.status} — ${when(a.created_at)}`,
        el("p", {}, `${d.contact_name} · ${d.email} · ${d.phone} · ${d.fleet_size} véhicule(s) · ${d.equipment.join(", ")} · garantie ${eur(d.insurance_cover_eur)} jusqu'au ${d.insurance_until}`),
        el("p", { class: "muted small" }, "Contrôles de forme : " + a.checks.map((c) => (c.ok ? "✓ " : "✗ ") + c.label).join(" · ")),
        el("p", { class: "muted small" }, "À vérifier à la main : existence de l'entreprise (Sirene/registre), licence, TVA active (VIES), attestation d'assurance."),
        note,
        actions([["Approuver", () => api("/api/admin/carriers/decision", { id: a.id, status: "approved", note: note.value })],
                 ["Demander un complément", () => api("/api/admin/carriers/decision", { id: a.id, status: "more_info", note: note.value })],
                 ["Refuser", () => api("/api/admin/carriers/decision", { id: a.id, status: "rejected", note: note.value })]]));
    }) : [empty("Aucune candidature.")]));
  }
  if (claims) {
    $("claims").replaceChildren(...(claims.claims.length ? claims.claims.map((c) => el("div", { class: "card" },
      el("b", {}, `#${c.id} ${c.tracking_code}`), ` — ${c.data.kind} — ${c.status} — ${when(c.created_at)}`,
      el("p", {}, c.data.description),
      el("p", { class: "muted small" }, `Livré le ${c.data.delivered_on} · protestation avant le ${c.deadlines.written_reserve_before} · prescription ${c.deadlines.limitation_date} · réserves sur récépissé : ${c.data.reserves_on_receipt ? "oui" : "non"}${c.data.amount_eur ? " · " + eur(c.data.amount_eur) : ""}`),
      actions([["Transmise au transporteur", () => api("/api/admin/claims/status", { id: c.id, status: "filed_with_carrier" })],
               ["Réglée", () => api("/api/admin/claims/status", { id: c.id, status: "settled" })],
               ["Refusée", () => api("/api/admin/claims/status", { id: c.id, status: "rejected" })]]))) : [empty("Aucune réclamation.")]));
  }
  if (contacts) {
    $("contacts").replaceChildren(...(contacts.contacts.length ? contacts.contacts.map((c) => el("div", { class: "card" },
      el("b", {}, `#${c.id} ${c.data.name}`), ` — ${c.data.topic} — ${c.status} — ${when(c.created_at)}`,
      el("p", {}, `${c.data.email} ${c.data.phone || ""} ${c.data.slot ? "· rappel : " + c.data.slot : ""}`), el("p", {}, c.data.message),
      actions([["Traitée", () => api("/api/admin/contacts/status", { id: c.id, status: "done" })]]))) : [empty("Aucune demande.")]));
  }
  if (chain) {
    $("chaining").replaceChildren(...(chain.suggestions.length ? chain.suggestions.map((s) => el("p", {},
      `${s.first} puis ${s.second} : ${s.route} — écart ${s.gap_km} km, environ ${s.saved_empty_km} km à vide évités (≈ ${eur(s.estimated_saving_eur)}, à confirmer avec le transporteur).`))
      : [empty("Aucun enchaînement détecté entre les réservations confirmées.")]));
  }
}

$("rfq-draft").addEventListener("click", async () => {
  try {
    const d = await api("/api/admin/rfq/draft", { quote_id: $("rfq-quote").value.trim() });
    const box = $("rfq-preview");
    box.replaceChildren(el("h3", {}, `Demande ${d.ref} : ${d.targets.length} transporteur(s) sélectionné(s)`),
      el("p", { class: "muted small" }, d.targets.map((t) => `${t.name} (${t.city}, ${t.distance_km} km)`).join(" ; ") || "Aucun transporteur contactable : ajoutez des e-mails dans l'annuaire."),
      el("pre", {}, `${d.subject}\n\n${d.body}`),
      el("p", { class: "muted small" }, `${d.skipped.length} écarté(s) : ${d.skipped.slice(0, 8).map((s) => s.reason).join(" ; ")}`));
    if (d.targets.length) {
      const b = el("button", { type: "button" }, "Envoyer cette demande");
      b.addEventListener("click", async () => { b.disabled = true; try { const r = await api("/api/admin/rfq/send", { id: d.id }); box.replaceChildren(el("p", { class: "ok-box" }, `${r.sent} demande(s) envoyée(s).`)); loadLeads(); } catch (e) { box.append(el("div", { class: "err" }, e.message)); b.disabled = false; } });
      box.append(b);
    }
  } catch (e) { $("rfq-preview").replaceChildren(el("div", { class: "err" }, e.message)); }
});


async function loadOutcomes() {
  const rep = await optional("/api/admin/outcomes");
  $("outcomes-box").classList.toggle("hidden", !rep);
  if (!rep) return;
  const pct = (v) => (v === null || v === undefined ? "—" : `${String(v).replace(".", ",")} %`);
  const rows = [
    el("p", {}, `${rep.count} transport(s) enregistré(s). Marge réalisée : ${eur(rep.realized_margin_ht)} (${pct(rep.realized_margin_pct)}) · écart coût réel / prix négocié : ${pct(rep.cost_vs_negotiated_pct)} · ponctualité : ${rep.on_time_rate === null ? "—" : Math.round(rep.on_time_rate * 100) + " %"}`),
  ];
  if (rep.indicative_only) rows.push(el("p", { class: "warn" }, `Moins de ${rep.min_sample} transports : chiffres indicatifs, ne recalez rien sur cette base.`));
  if (rep.carriers.length) {
    rows.push(el("table", { class: "data" }, el("tbody", {}, ...rep.carriers.map((c) =>
      el("tr", {}, el("td", {}, c.carrier || "—"), el("td", {}, `${c.count} transport(s)`), el("td", {}, `ponctualité ${Math.round(c.on_time_rate * 100)} %`),
        el("td", {}, c.indicative_only ? "indicatif (moins de 5)" : ""))))));
  }
  $("oc-report").replaceChildren(...rows);
}

document.addEventListener("DOMContentLoaded", () => {
  const f = $("outcome-form");
  if (!f) return;
  f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("oc-msg").textContent = "";
    try {
      await api("/api/admin/outcome", { tracking_code: $("oc-code").value.trim(), actual_cost_ht: parseFloat($("oc-cost").value),
        on_time: $("oc-ontime").value === "1", note: $("oc-note").value });
      $("oc-msg").textContent = "Résultat enregistré.";
      f.reset();
      loadOutcomes();
    } catch (e) { $("oc-msg").textContent = e.message; }
  });
});
