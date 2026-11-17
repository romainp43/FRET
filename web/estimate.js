"use strict";
(function () {
  const { $, el, api, err } = window.FR;
  $("est-form").addEventListener("submit", async (e) => {
    e.preventDefault(); err("est-error", "");
    const eur = (v) => Math.round(v).toLocaleString("fr-FR") + " €";
    try {
      const r = await api("/api/indicative", { kind: $("e-kind").value, origin: $("e-o").value.trim(), destination: $("e-d").value.trim(),
        pallets: parseInt($("e-p").value, 10), weight_kg: parseFloat($("e-w").value) });
      $("est-result").replaceChildren(el("div", { class: "card" }, el("h2", {}, `${eur(r.price_ht_low)} à ${eur(r.price_ht_high)} HT`),
        el("p", {}, `Valeur centrale : ${eur(r.price_ht_mid)} HT · ${Math.round(r.distance_km)} km · environ ${r.transit_days} jour(s)`),
        ...r.notes.map((n) => el("p", { class: "muted small" }, n)), el("a", { class: "btn", href: "/contact.html" }, "Demander un devis ferme")));
    } catch (x) { $("est-result").replaceChildren(); err("est-error", x.message); }
  });
})();
