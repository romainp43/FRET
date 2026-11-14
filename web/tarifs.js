"use strict";
onSubmit("rates-form", "rates-error", async () => {
  const origin = $("r-o").value.trim(), destination = $("r-d").value.trim();
  const r = await api("/api/rates", { origin, destination });
  $("rates-out").replaceChildren(
    el("h2", {}, `${r.origin} → ${r.destination} · ${Math.round(r.distance_km)} km`),
    ...r.rates.map((x) => {
      const go = new URLSearchParams({ depart: origin, arrivee: destination, mode: x.mode });
      return el("div", { class: "card rate" },
        el("div", {}, el("h3", {}, x.label),
          el("p", { class: "muted" }, `${x.pallets ? x.pallets + " palette(s), " : "Jusqu'à 33 palettes, "}${x.weight_kg} kg · ${x.transit_days} jour(s) · ${eur(x.per_km)} / km`)),
        el("div", { class: "rate-price" }, el("div", { class: "price" }, eur(x.price_ht), el("small", {}, " HT")),
          el("a", { class: "btn", href: "/?" + go }, "Réserver")));
    }));
});
