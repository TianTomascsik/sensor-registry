// Progressive Enhancement ohne Inline-Handler (ermöglicht eine strikte CSP: script-src 'self').
// Ersetzt onclick/onsubmit/onchange-Attribute durch datengesteuerte Verhaltensweisen.
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  // Klickbare Tabellenzeilen: [data-href] navigiert, ohne innere Links/Buttons zu stören.
  for (const element of document.querySelectorAll("[data-href]")) {
    element.addEventListener("click", (event) => {
      if (event.target.closest("a, button, form, input, select, label")) {
        return;
      }
      window.location = element.dataset.href;
    });
  }

  // Bestätigung vor dem Absenden: form[data-confirm].
  for (const form of document.querySelectorAll("form[data-confirm]")) {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  }

  // Auswahl automatisch absenden: select[data-autosubmit].
  for (const select of document.querySelectorAll("select[data-autosubmit]")) {
    select.addEventListener("change", () => {
      const form = select.form;
      if (form) {
        form.submit();
      }
    });
  }
});
