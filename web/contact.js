"use strict";
const subject = new URLSearchParams(location.search).get("sujet");
if (["rappel", "devis", "transporteur", "autre"].includes(subject)) $("k-topic").value = subject;
onSubmit("contact-form", "contact-error", async (form) => {
  await api("/api/contact", {
    topic: $("k-topic").value, name: $("k-name").value, company: $("k-company").value, email: $("k-email").value,
    phone: $("k-phone").value, message: $("k-message").value, website: form.querySelector("[name=website]").value,
  });
  $("contact-ok").classList.remove("hidden");
  form.querySelector("button[type=submit]").classList.add("hidden");
});
