"use strict";
// Formulaires publics : candidature transporteur, contact, réclamation. Aucune donnée n'est stockée dans le navigateur.
(function () {
  const BOOL = ["accept_charter", "consent", "reserves_on_receipt"];
  const INT = ["fleet_size"];
  const NUM = ["insurance_cover_eur", "amount_eur"];
  const LISTS = ["equipment", "countries"];
  const ENDPOINT = { "carrier-form": "/api/carrier/apply", "contact-form": "/api/contact", "claim-form": "/api/claim" };

  function collect(form) {
    const out = {};
    new FormData(form).forEach((v, k) => { if (!LISTS.includes(k) && !BOOL.includes(k)) out[k] = String(v).trim(); });
    LISTS.forEach((k) => { if (form.querySelector(`[name="${k}"]`)) out[k] = Array.from(form.querySelectorAll(`[name="${k}"]:checked`)).map((i) => i.value); });
    BOOL.forEach((k) => { if (form.querySelector(`[name="${k}"]`)) out[k] = form.querySelector(`[name="${k}"]`).checked; });
    INT.forEach((k) => { if (k in out) out[k] = out[k] === "" ? null : parseInt(out[k], 10); });
    NUM.forEach((k) => { if (k in out) { if (out[k] === "") delete out[k]; else out[k] = parseFloat(out[k]); } });
    Object.keys(out).forEach((k) => { if (out[k] === "" ) delete out[k]; });
    return out;
  }

  function show(el, text) { el.textContent = text; el.classList.remove("hidden"); }

  function deadlines(box, d) {
    box.replaceChildren();
    const card = document.createElement("div");
    card.className = "card";
    const h = document.createElement("h2"); h.textContent = "Vos délais"; card.append(h);
    [["Protestation écrite avant le", d.written_reserve_before], ["Prescription de l'action", d.limitation_date]].forEach(([l, v]) => {
      const p = document.createElement("p"); const b = document.createElement("b"); b.textContent = v;
      p.append(l + " : ", b); card.append(p);
    });
    const r = document.createElement("p"); r.className = "muted small"; r.textContent = d.rule; card.append(r);
    box.append(card);
  }

  Object.keys(ENDPOINT).forEach((id) => {
    const form = document.getElementById(id);
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const msg = form.querySelector("#form-msg"), err = form.querySelector("#form-error"), btn = form.querySelector("button[type=submit]");
      err.classList.add("hidden"); msg.textContent = ""; btn.disabled = true;
      try {
        const res = await fetch(ENDPOINT[id], { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(collect(form)) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const extra = Array.isArray(data.problems) ? " À corriger : " + data.problems.join(" ; ") + "." : "";
          throw new Error((data.error || "Une erreur est survenue.") + extra);
        }
        msg.textContent = data.message || "Envoyé.";
        if (data.reference) msg.textContent += " Référence : " + data.reference + ".";
        if (data.deadlines) deadlines(document.getElementById("claim-deadlines"), data.deadlines);
        form.reset();
      } catch (ex) {
        show(err, ex.message);
      } finally {
        btn.disabled = false;
      }
    });
  });
})();
