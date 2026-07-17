// Service Worker der Sensor-Dokumentation (serverseitig gerendert).
// Strategie: gehashte Static-Dateien cache-first, Navigationen network-first mit Fallback
// auf die zwischengespeicherte App-Shell, API-Aufrufe niemals cachen.
"use strict";

const CACHE = "papa-{{ cache_version }}";
const PRECACHE_ASSETS = {{ precache_assets_json|safe }};
const PRECACHE_PAGES = {{ precache_pages_json|safe }};
const API_PREFIX = "{{ api_prefix }}";
const MEDIA_PREFIX = "{{ media_prefix }}";

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      await cache.addAll(PRECACHE_ASSETS);
      // App-Seiten „best effort“ vorab cachen (Authentifizierung/Redirect kann fehlschlagen).
      await Promise.all(PRECACHE_PAGES.map((url) => cache.add(url).catch(() => {})));
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => key.startsWith("papa-") && key !== CACHE).map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return; // externe Ressourcen (z. B. OSM-Kacheln) unverändert dem Netz überlassen
  }
  if (url.pathname.startsWith(API_PREFIX)) {
    return; // API-Aufrufe niemals cachen
  }
  if (request.mode === "navigate") {
    event.respondWith(handleNavigate(request));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (url.pathname.startsWith(MEDIA_PREFIX)) {
    event.respondWith(networkFirst(request));
    return;
  }
  event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
});

async function handleNavigate(request) {
  try {
    const response = await fetchWithTimeout(request, 3500);
    // Redirects (z. B. 302 zur Anmeldung) nicht cachen, sonst wird die Shell „vergiftet“.
    if (response.ok && !response.redirected) {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request, { ignoreVary: true });
    if (cached) {
      return cached;
    }
    const shell = await caches.match(PRECACHE_PAGES[0], { ignoreVary: true });
    if (shell) {
      return shell;
    }
    return new Response(
      "<h1>Offline</h1><p>Diese Seite ist offline nicht verfügbar.</p>",
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } },
    );
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(CACHE);
    cache.put(request, response.clone());
  }
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    throw err;
  }
}

function fetchWithTimeout(request, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), ms);
    fetch(request).then(
      (response) => {
        clearTimeout(timer);
        resolve(response);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}
