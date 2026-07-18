// Kartenansicht der Installationen: lädt aktive Installationen aus der API und stellt sie
// als geclusterte Marker mit Popups dar (Leaflet + markercluster, self-hosted).
"use strict";

const el = document.getElementById("map");
if (el && window.L) {
  render(el, window.L);
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

async function render(el, L) {
  const status = document.getElementById("mapStatus");
  const detailTemplate = el.dataset.detailUrl; // endet auf /0/

  const icon = L.icon({
    iconUrl: el.dataset.markerIcon,
    iconRetinaUrl: el.dataset.markerIcon2x,
    shadowUrl: el.dataset.markerShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41],
  });

  // Karte ohne Fixzentrum initialisieren; Auto-Zoom erfolgt über die Marker-Grenzen.
  const map = L.map(el).setView([46.8, 8.2], 7);
  // Tile-Quelle ist konfigurierbar (Dev: OpenStreetMap, Prod: eigener Server/Provider mit
  // Key) und kommt aus den Server-Einstellungen über Datenattribute.
  const tileUrl = el.dataset.tileUrl || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  L.tileLayer(tileUrl, {
    attribution: el.dataset.tileAttribution || "&copy; OpenStreetMap-Mitwirkende",
    maxZoom: parseInt(el.dataset.tileMaxZoom, 10) || 19,
    // Die App setzt global Referrer-Policy "same-origin" (Härtung). Cross-Origin-Kacheln
    // gingen damit refererlos an den Tile-Server – OSMs Nutzungsrichtlinie blockt das mit
    // HTTP 403. Pro Kachel-<img> senden wir daher zumindest den Origin als Referer; die
    // globale Policy für alle übrigen Anfragen bleibt unverändert.
    referrerPolicy: "strict-origin-when-cross-origin",
  }).addTo(map);

  let installations;
  try {
    const response = await fetch(el.dataset.url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    installations = await response.json();
  } catch (err) {
    status.textContent = `Installationen konnten nicht geladen werden: ${err.message}`;
    return;
  }

  const cluster = L.markerClusterGroup();
  const bounds = [];
  for (const inst of installations) {
    const lat = inst.latitude;
    const lng = inst.longitude;
    if (typeof lat !== "number" || typeof lng !== "number") {
      continue;
    }
    const marker = L.marker([lat, lng], { icon });
    marker.bindPopup(buildPopup(inst, detailTemplate));
    cluster.addLayer(marker);
    bounds.push([lat, lng]);
  }
  map.addLayer(cluster);

  if (bounds.length > 0) {
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
    status.textContent = `${bounds.length} Installation(en) auf der Karte.`;
  } else {
    status.textContent = "Keine aktiven Installationen vorhanden.";
  }
}

function buildPopup(inst, detailTemplate) {
  const detailUrl = detailTemplate.replace(/0\/$/, `${inst.id}/`);
  const date = inst.received_at ? new Date(inst.received_at).toLocaleDateString("de-CH") : "";
  const photo = inst.thumbnail_url
    ? `<img src="${escapeHtml(inst.thumbnail_url)}" alt="Foto" loading="lazy">`
    : "";
  return (
    `<div class="map-popup">${photo}` +
    `<div><strong>${escapeHtml(inst.dev_eui)}</strong></div>` +
    `<div>${escapeHtml(inst.description) || "<em>ohne Beschreibung</em>"}</div>` +
    `<div class="text-muted small mt-1">${escapeHtml(inst.installer_name)} · ${escapeHtml(date)}</div>` +
    `<a href="${detailUrl}" class="btn btn-sm btn-primary mt-2">Details</a>` +
    `</div>`
  );
}
