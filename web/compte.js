"use strict";
const params = new URLSearchParams(location.search);
const say = (msg) => { $("c-status").textContent = msg; $("c-status").classList.remove("hidden"); };
// Le jeton quitte la barre d'adresse dès qu'il est lu : il ne reste ni dans l'historique ni dans un lien copié.
const take = (name) => { const t = params.get(name); if (t) history.replaceState(null, "", "/compte"); return t; };

async function start() {
  const verify = take("verifier"), reset = take("reinitialiser");
  if (verify) {
    try { await api("/api/account/verify", { token: verify }); say("Adresse e-mail confirmée. Merci."); }
    catch (err) { showError("c-error", err.message); }
  }
  if (reset) {
    $("reset-form").classList.remove("hidden");
    onSubmit("reset-form", "reset-error", async () => {
      await api("/api/account/reset", { token: reset, password: $("n-pw").value });
      $("reset-form").classList.add("hidden");
      say("Mot de passe modifié. Vous pouvez vous connecter depuis votre espace.");
    });
    return;
  }
  const { account } = await api("/api/account/me");
  if (!account) { $("forgot-form").classList.remove("hidden"); return; }
  $("settings").classList.remove("hidden");
  $("s-email").textContent = account.email + (account.email_verified ? " — confirmée" : " — non confirmée");
  $("s-resend").classList.toggle("hidden", account.email_verified);
  $("s-export").href = "/api/account/export";
}

$("s-resend").addEventListener("click", async () => { await api("/api/account/resend", {}); say("Lien envoyé : consultez votre boîte e-mail."); });
$("s-export").addEventListener("click", async (e) => {
  e.preventDefault();                                   // l'en-tête anti-CSRF est obligatoire : on passe par fetch
  const res = await fetch("/api/account/export", { headers: { "X-Requested-With": "fretrau" }, credentials: "same-origin" });
  if (!res.ok) return showError("c-error", "Export impossible, reconnectez-vous.");
  const url = URL.createObjectURL(await res.blob());
  const a = el("a", { href: url, download: "mes-donnees-fretrau.json" });
  document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
});
onSubmit("forgot-form", "forgot-error", async () => {
  await api("/api/account/forgot", { email: $("f-email").value });
  $("forgot-form").classList.add("hidden");
  say("Si un compte existe pour cette adresse, un lien vient d'y être envoyé.");
});
onSubmit("pw-form", "pw-error", async () => {
  await api("/api/account/password", { current: $("p-current").value, password: $("p-new").value });
  $("p-current").value = ""; $("p-new").value = "";
  say("Mot de passe modifié. Les autres appareils ont été déconnectés.");
});
onSubmit("delete-form", "delete-error", async () => {
  await api("/api/account/delete", { password: $("d-pw").value });
  location.href = "/";
});
start().catch((err) => showError("c-error", err.message));
