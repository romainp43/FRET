"use strict";
// Le jeton est dans le fragment d'URL (#...) : il n'est donc jamais envoyé dans l'adresse d'une requête ni écrit dans les journaux du serveur.
(function () {
  const { $, api, err } = window.FR;
  const token = location.hash.slice(1);
  let watchId = null, last = 0;
  const status = (t) => { $("drv-status").textContent = t; };
  function stop() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null; $("drv-stop").classList.add("hidden"); $("drv-start").classList.remove("hidden");
  }
  async function send(pos) {
    if (Date.now() - last < 20000) return;
    last = Date.now();
    try {
      await api("/api/driver/position", { token, lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy });
      status("Position partagée (" + new Date().toLocaleTimeString("fr-FR") + "). Gardez cette page ouverte.");
    } catch (e) { err("drv-error", e.message); if (/invalide|expiré/i.test(e.message)) stop(); }
  }
  $("drv-start").addEventListener("click", async () => {
    err("drv-error", "");
    if (!navigator.geolocation) return err("drv-error", "Ce téléphone ne permet pas le partage de position.");
    try { await api("/api/driver/consent", { token }); } catch (e) { return err("drv-error", e.message); }
    watchId = navigator.geolocation.watchPosition(send, (e) => err("drv-error", "Position indisponible : " + e.message), { enableHighAccuracy: true, maximumAge: 10000 });
    $("drv-start").classList.add("hidden"); $("drv-stop").classList.remove("hidden"); status("Partage actif…");
  });
  $("drv-stop").addEventListener("click", async () => {
    stop(); try { await api("/api/driver/stop", { token }); } catch (e) { /* lien déjà fermé */ }
    status("Partage arrêté. Merci !");
  });
  if (!token) { status("Lien incomplet."); return; }
  status("Prêt. Appuyez sur le bouton pour accepter le partage de votre position pendant cette livraison.");
  $("drv-start").classList.remove("hidden");
})();
