"use strict";
(function () {
  const { $, el, api, err } = window.FR;
  async function list() {
    const r = await api("/api/account/bookings");
    const rows = r.bookings.map((b) => el("tr", {}, el("td", {}, el("a", { href: "/suivi.html?code=" + encodeURIComponent(b.tracking_code) }, b.tracking_code)),
      el("td", {}, `${b.origin} → ${b.destination}`), el("td", {}, b.pickup_date || ""), el("td", {}, b.status === "confirmed" ? "Confirmé" : "En traitement"),
      el("td", {}, `${Number(b.price_ht).toFixed(2)} € HT`)));
    $("acct-list").replaceChildren(r.bookings.length ? el("table", { class: "data" }, el("thead", {}, el("tr", {}, ...["Code", "Trajet", "Enlèvement", "Statut", "Prix"].map((h) => el("th", {}, h)))), el("tbody", {}, ...rows))
      : el("p", { class: "muted" }, "Aucun envoi trouvé."));
  }
  $("acct-form").addEventListener("submit", async (e) => {
    e.preventDefault(); err("acct-error", "");
    try { await api("/api/account/request", { email: $("a-email").value.trim() });
      $("acct-msg").textContent = "Si cette adresse a déjà réservé chez nous, un code vient de lui être envoyé (valable 10 minutes).";
      $("acct-code-box").classList.remove("hidden"); } catch (x) { err("acct-error", x.message); }
  });
  $("acct-verify").addEventListener("click", async () => {
    err("acct-error", "");
    try { await api("/api/account/verify", { email: $("a-email").value.trim(), code: $("a-code").value.trim() }); await list(); $("acct-form").classList.add("hidden"); }
    catch (x) { err("acct-error", x.message); }
  });
  list().then(() => $("acct-form").classList.add("hidden")).catch(() => {});
})();
