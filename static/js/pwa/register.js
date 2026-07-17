// PWA-Glue: Service Worker registrieren, Speicher persistent anfordern, Referenzdaten
// aktualisieren und die Outbox synchronisieren – beim Laden und sobald wieder online.
"use strict";

import { refreshRefData, sync } from "./outbox.js";

const notifyOutboxChanged = () => window.dispatchEvent(new Event("papa:outbox-changed"));

async function persistStorage() {
  if (navigator.storage && navigator.storage.persist) {
    try {
      await navigator.storage.persist();
    } catch {
      /* Persistenz ist optional. */
    }
  }
}

async function refreshAndSync() {
  if (!navigator.onLine) {
    return;
  }
  try {
    await refreshRefData();
  } catch {
    /* Offline oder Serverfehler: vorhandenes Replikat weiterverwenden. */
  }
  try {
    await sync(notifyOutboxChanged);
  } catch {
    /* Sync wird beim nächsten Trigger erneut versucht. */
  }
}

function showUpdateBanner(worker) {
  if (document.getElementById("pwaUpdate")) {
    return;
  }
  const bar = document.createElement("div");
  bar.id = "pwaUpdate";
  bar.className = "alert alert-info d-flex justify-content-between align-items-center m-0 rounded-0";
  bar.style.position = "sticky";
  bar.style.top = "0";
  bar.style.zIndex = "1080";
  bar.innerHTML =
    '<span>Eine neue Version ist verfügbar.</span>' +
    '<button type="button" class="btn btn-sm btn-primary">Aktualisieren</button>';
  bar.querySelector("button").addEventListener("click", () => {
    worker.postMessage({ type: "SKIP_WAITING" });
  });
  document.body.prepend(bar);
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  try {
    const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });

    // Auf eine wartende neue Version prüfen (Update-Banner).
    if (registration.waiting) {
      showUpdateBanner(registration.waiting);
    }
    registration.addEventListener("updatefound", () => {
      const worker = registration.installing;
      if (!worker) {
        return;
      }
      worker.addEventListener("statechange", () => {
        if (worker.state === "installed" && navigator.serviceWorker.controller) {
          showUpdateBanner(worker);
        }
      });
    });

    let reloading = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (!reloading) {
        reloading = true;
        window.location.reload();
      }
    });
  } catch {
    /* Ohne Service Worker funktioniert die App online weiterhin. */
  }
}

// Install-Aufforderung (Chromium): eigenen Button anbieten.
let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredPrompt = event;
  const button = document.getElementById("pwaInstall");
  if (button) {
    button.classList.remove("d-none");
    button.addEventListener("click", async () => {
      button.classList.add("d-none");
      deferredPrompt.prompt();
      deferredPrompt = null;
    });
  }
});

window.addEventListener("online", refreshAndSync);

persistStorage();
registerServiceWorker();
refreshAndSync();
