"use strict";
const STATUS = { confirmed: "Confirmée", sourcing: "Recherche du transporteur", pending_human: "En cours de traitement" };

async function start() {
  const { account } = await api("/api/account/me");
  if (account && account.role === "carrier") { location.href = "/transporteur.html"; return; }
  if (!account) { $("auth").classList.remove("hidden"); return; }
  $("dash").classList.remove("hidden");
  $("logout").classList.remove("hidden");
  $("who").textContent = `${account.name} — ${account.company}`;
  const { bookings } = await api("/api/my/bookings");
  $("empty").classList.toggle("hidden", bookings.length > 0);
  $("list").replaceChildren(...bookings.map(card));
}

function card(b) {
  const box = el("div", { class: "card" },
    el("div", { class: "page-head" },
      el("div", {}, el("h2", {}, `${b.origin} → ${b.destination}`),
        el("p", { class: "muted" }, `${b.tracking_code} · ${MODES[b.mode] || b.mode} · enlèvement le ${frDate(b.pickup_date)} · ${eur(b.price_ht)} HT`)),
      el("span", { class: "pill " + b.status }, STATUS[b.status] || b.status)),
    b.message ? el("p", { class: "muted" }, b.message)
      : el("ul", { class: "timeline" }, ...b.events.map((ev) => el("li", { class: ev.done ? "done" : "" }, ev.label))));
  if (b.status === "confirmed") {
    const out = el("div", {});
    const inv = el("button", { class: "ghost", type: "button" }, "Voir la facture");
    inv.addEventListener("click", async () => {
      try {
        const f = await api("/api/my/invoice/" + encodeURIComponent(b.tracking_code));
        out.replaceChildren(el("div", { class: "ok-box" },
          `Facture ${f.number} du ${frDate(f.issued_on)} — ${eur(f.total_ht)} HT, ${eur(f.total_ttc)} TTC — échéance ${frDate(f.due_on)}`));
      } catch (err) { out.replaceChildren(el("div", { class: "err" }, err.message)); }
    });
    box.append(el("p", { class: "muted" }, `Transporteur : ${b.carrier}`),
      el("div", { class: "actions" },
        el("a", { class: "btn", href: "/api/doc/" + encodeURIComponent(b.tracking_code), target: "_blank", rel: "noopener" }, "Lettre de voiture"), inv), out);
  }
  return box;
}

onSubmit("login-form", "login-error", async () => {
  await api("/api/account/login", { email: $("l-email").value, password: $("l-pw").value });
  location.reload();
});
onSubmit("signup-form", "signup-error", async (form) => {
  await api("/api/account/signup", {
    name: $("s-name").value, company: $("s-company").value, email: $("s-email").value, phone: $("s-phone").value,
    password: $("s-pw").value, website: form.querySelector("[name=website]").value,
  });
  location.reload();
});
$("logout").addEventListener("click", (e) => { e.preventDefault(); logout(); });
start().catch(() => $("auth").classList.remove("hidden"));
