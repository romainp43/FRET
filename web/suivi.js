"use strict";
(function () {
  const { $, el, api, err } = window.FR;
  let timer = null;
  async function track(code) {
    clearTimeout(timer); err("track-error", "");
    try {
      const t = await api("/api/track/" + encodeURIComponent(code));
      const kids = [el("h3", {}, `${t.origin} → ${t.destination}`)];
      if (t.message) kids.push(el("p", { class: "muted" }, t.message));
      else kids.push(el("ul", { class: "timeline" }, ...t.events.map((ev) => el("li", { class: ev.done ? "done" : "" }, ev.label))));
      if (t.driver_position) {
        const when = new Date(t.driver_position.ts * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
        kids.push(el("p", {}, `Dernière position partagée par le chauffeur à ${when} : ${t.driver_position.lat.toFixed(3)}, ${t.driver_position.lon.toFixed(3)} (`,
          el("a", { href: `https://www.openstreetmap.org/?mlat=${t.driver_position.lat}&mlon=${t.driver_position.lon}#map=11/${t.driver_position.lat}/${t.driver_position.lon}`, target: "_blank", rel: "noopener noreferrer" }, "voir sur la carte"), ")"));
      }
      if (t.status === "confirmed") {
        kids.push(el("a", { class: "btn", href: "/api/doc/" + encodeURIComponent(code), target: "_blank", rel: "noopener" }, "Lettre de voiture"));
        kids.push(el("a", { class: "btn alt", href: "/reclamation.html" }, "Déclarer un problème"));
      }
      $("track-result").replaceChildren(...kids);
      if (t.events.some((ev) => !ev.done)) timer = setTimeout(() => track(code), 15000);
    } catch (e) { $("track-result").replaceChildren(); err("track-error", e.message); }
  }
  $("track-form").addEventListener("submit", (e) => { e.preventDefault(); track($("track-code").value.trim().toUpperCase()); });
  const q = new URLSearchParams(location.search).get("code") || location.hash.slice(1);
  if (q) { $("track-code").value = q.toUpperCase(); track(q.toUpperCase()); }
})();
