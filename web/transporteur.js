"use strict";
const STEP_BUTTONS = { loaded: "Déclarer le chargement", transit: "Déclarer le départ", delivered: "Déclarer la livraison" };
const STEP_ORDER = ["loaded", "transit", "delivered"];
const DOSSIER = {
  pending_review: "Votre dossier est en cours de contrôle. Vous verrez les chargements dès sa validation.",
  prospect: "Votre dossier est en cours de contrôle. Vous verrez les chargements dès sa validation.",
  blocked: "Votre compte est suspendu. Contactez-nous.",
};

function describe(l) {
  const opts = l.options.map((o) => OPTION_LABELS[o] || o).join(", ");
  return `${MODES[l.mode] || l.mode}` + (l.pallets && l.mode !== "FTL" ? ` · ${l.pallets} palette(s)` : "")
    + ` · ${l.weight_kg} kg · enlèvement le ${frDate(l.pickup_date)}` + (opts ? ` · ${opts}` : "");
}

async function start() {
  const { account } = await api("/api/account/me");
  if (account && account.role === "shipper") { location.href = "/portail.html"; return; }
  if (!account) { $("auth").classList.remove("hidden"); return; }
  $("dash").classList.remove("hidden");
  $("logout").classList.remove("hidden");
  $("who").textContent = `${account.company} — ${account.name}`;
  await refresh();
}

async function refresh() {
  const open = await api("/api/carrier/loads");
  $("banner").replaceChildren(open.status === "verified" ? "" : el("div", { class: "ok-box" }, DOSSIER[open.status] || ""));
  $("loads").replaceChildren(...(open.loads.length ? open.loads.map(loadCard)
    : [el("div", { class: "card" }, el("p", { class: "muted" }, "Aucun chargement proposé pour le moment."))]));
  if (open.status !== "verified") return;
  const my = await api("/api/carrier/my");
  $("mine").replaceChildren(...(my.loads.length ? my.loads.map(myCard)
    : [el("div", { class: "card" }, el("p", { class: "muted" }, "Aucun transport attribué pour le moment."))]));
  $("payables").replaceChildren(...my.payables.map((p) => el("tr", {},
    el("td", {}, p.code), el("td", {}, eur(p.amount)), el("td", {}, frDate(p.due_on)),
    el("td", {}, p.status === "paid" ? "Réglé" : "À régler"))));
}

function loadCard(l) {
  const msg = el("div", {});
  const amount = el("input", { type: "number", min: "20", step: "1", "aria-label": "Votre prix HT", placeholder: "Votre prix HT" });
  const respond = async (value) => {
    try {
      const r = await api("/api/carrier/respond", { code: l.code, amount: value });
      if (r.decision === "accepted") { await refresh(); return; }
      const text = r.decision === "counter" ? `Nous pouvons monter à ${eur(r.counter_price)} HT au maximum.`
        : r.decision === "escalate" ? "Votre prix dépasse notre budget : un conseiller étudie votre proposition."
          : r.reason || "Proposition non retenue.";
      msg.replaceChildren(el("div", { class: "ok-box" }, text));
      if (r.decision === "counter") setTimeout(refresh, 2500);
    } catch (err) { msg.replaceChildren(el("div", { class: "err" }, err.message)); }
  };
  const accept = el("button", { type: "button" }, `Accepter à ${eur(l.price)} HT`);
  accept.addEventListener("click", () => respond(l.price));
  const propose = el("button", { type: "button", class: "ghost" }, "Proposer ce prix");
  propose.addEventListener("click", () => { const v = parseFloat(amount.value); if (v >= 20) respond(v); });
  return el("div", { class: "card" },
    el("h3", {}, `${l.origin} → ${l.destination}`),
    el("p", { class: "muted" }, describe(l) + (l.goods ? ` · ${l.goods}` : "")),
    l.offer === "countered" ? el("p", {}, "Nouvelle proposition de notre part :") : "",
    el("div", { class: "actions" }, accept, amount, propose), msg);
}

function myCard(l) {
  const next = STEP_ORDER.find((s) => !l.steps.includes(s));
  const msg = el("div", {});
  const box = el("div", { class: "card" },
    el("h3", {}, `${l.origin} → ${l.destination} — ${eur(l.price)} HT`),
    el("p", { class: "muted" }, `${l.code} · ${describe(l)}`),
    el("p", {}, `Enlèvement : ${l.pickup_address}`), el("p", {}, `Livraison : ${l.delivery_address}`),
    el("p", {}, `Marchandise : ${l.goods} — contact : ${l.contact}`));
  if (!next) { box.append(el("div", { class: "ok-box" }, "Livraison enregistrée. Règlement à 30 jours.")); return box; }
  const who = el("input", { placeholder: "Nom du réceptionnaire", "aria-label": "Nom du réceptionnaire" });
  const btn = el("button", { type: "button" }, STEP_BUTTONS[next]);
  btn.addEventListener("click", async () => {
    try {
      await api("/api/carrier/milestone", { code: l.code, step: next, received_by: who.value });
      await refresh();
    } catch (err) { msg.replaceChildren(el("div", { class: "err" }, err.message)); }
  });
  box.append(el("div", { class: "actions" }, next === "delivered" ? who : "", btn), msg);
  return box;
}

onSubmit("login-form", "login-error", async () => {
  await api("/api/account/login", { email: $("l-email").value, password: $("l-pw").value });
  location.reload();
});
onSubmit("apply-form", "apply-error", async (form) => {
  const modes = [];
  if ($("a-ftl").checked) modes.push("FTL");
  if ($("a-ltl").checked) modes.push("LTL");
  await api("/api/carrier/apply", {
    company: $("a-company").value, siret: $("a-siret").value, licence_no: $("a-licence").value,
    insurance_until: $("a-insurance").value, postcode: $("a-postcode").value.trim(), equipment: $("a-equipment").value,
    modes, europe: $("a-europe").checked, name: $("a-name").value, phone: $("a-phone").value,
    email: $("a-email").value, password: $("a-pw").value, website: form.querySelector("[name=website]").value,
  });
  location.reload();
});
$("logout").addEventListener("click", (e) => { e.preventDefault(); logout(); });
start().catch(() => $("auth").classList.remove("hidden"));
