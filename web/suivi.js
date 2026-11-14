"use strict";
let timer = null;
async function track(code) {
  clearTimeout(timer);
  showError("track-error", "");
  try {
    const t = await api("/api/track/" + encodeURIComponent(code));
    $("track-result").replaceChildren(
      el("h3", {}, `${t.origin} → ${t.destination}`),
      t.message ? el("p", { class: "muted" }, t.message) : el("ul", { class: "timeline" },
        ...t.events.map((ev) => el("li", { class: ev.done ? "done" : "" }, ev.label,
          ev.at ? el("span", { class: "muted small" }, " — " + new Date(ev.at * 1000).toLocaleString("fr-FR")) : ""))),
      t.status === "confirmed" ? el("a", { class: "btn", href: "/api/doc/" + encodeURIComponent(code), target: "_blank", rel: "noopener" }, "Lettre de voiture") : "");
    if (t.message || t.events.some((ev) => !ev.done)) timer = setTimeout(() => track(code), 15000);
  } catch (err) { $("track-result").replaceChildren(); showError("track-error", err.message); }
}
$("track-form").addEventListener("submit", (e) => { e.preventDefault(); track($("track-code").value.trim().toUpperCase()); });
const given = (new URLSearchParams(location.search).get("code") || "").toUpperCase();
if (/^FR-[0-9A-F]{12}$/.test(given)) { $("track-code").value = given; track(given); }
