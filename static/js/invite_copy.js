// Kopiert den Einladungslink in die Zwischenablage (Anzeige-Seite der Einladung).
(() => {
  "use strict";
  const button = document.getElementById("copyBtn");
  const input = document.getElementById("inviteUrl");
  if (!button || !input) {
    return;
  }

  const flash = (text) => {
    const original = button.innerHTML;
    button.innerHTML = text;
    window.setTimeout(() => {
      button.innerHTML = original;
    }, 1500);
  };

  button.addEventListener("click", async () => {
    const url = button.dataset.url || input.value;
    try {
      await navigator.clipboard.writeText(url);
      flash('<i class="bi bi-check-lg"></i> Kopiert');
    } catch {
      // Fallback ohne Clipboard-API (z. B. ohne HTTPS): Feld markieren.
      input.focus();
      input.select();
    }
  });
})();
