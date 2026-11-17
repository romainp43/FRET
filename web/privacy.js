"use strict";
(function () {
  const { $, api, err } = window.FR;
  $("stop-form").addEventListener("submit", async (e) => {
    e.preventDefault(); err("stop-error", ""); $("stop-msg").textContent = "";
    try { await api("/api/sms/stop", { phone: $("s-phone").value.trim(), website: document.querySelector("#stop-form [name=website]").value });
      $("stop-msg").textContent = "C'est fait : plus aucun SMS ne sera envoyé à ce numéro."; } catch (x) { err("stop-error", x.message); }
  });
})();
