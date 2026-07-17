// Offline-Outbox: Referenzdaten zwischenspeichern, Fotos clientseitig re-kodieren,
// Erfassungen lokal ablegen und idempotent gegen die REST-API synchronisieren.
"use strict";

import { get, getAll, put } from "./idb.js";

const REFDATA = "refdata";
const OUTBOX = "outbox";
const PHOTOS = "photos";

const CREATE_URL = "/api/v1/installations/";
const REFDATA_URL = "/api/v1/refdata/";
const photoUrl = (installationUuid) => `/api/v1/installations/${installationUuid}/photos/`;

// Outbox-Zustände: pending → installation_synced → done | error (Netzfehler bleiben pending).
export const State = Object.freeze({
  PENDING: "pending",
  INSTALLATION_SYNCED: "installation_synced",
  DONE: "done",
  ERROR: "error",
});

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : "";
}

// --- Referenzdaten (Projekte/Sensoren) ---------------------------------------------

export async function refreshRefData() {
  const response = await fetch(REFDATA_URL, {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`Referenzdaten HTTP ${response.status}`);
  }
  const data = await response.json();
  await put(REFDATA, { key: "projects", items: data.projects });
  await put(REFDATA, { key: "sensors", items: data.sensors });
  return data;
}

export async function getRefData(key) {
  const record = await get(REFDATA, key);
  return record ? record.items : [];
}

// --- Foto-Neukodierung (Canvas; korrigiert die EXIF-Ausrichtung) -------------------

export async function reencode(file, maxPx = 2560, quality = 0.85) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, maxPx / Math.max(bitmap.width, bitmap.height));
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.getContext("2d").drawImage(bitmap, 0, 0, width, height);
  if (bitmap.close) {
    bitmap.close();
  }
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), "image/jpeg", quality));
}

// --- Erfassung ablegen -------------------------------------------------------------

export async function enqueue(entry, photoBlobs) {
  const record = {
    ...entry,
    state: State.PENDING,
    error: "",
    installation_id: null,
    photo_count: photoBlobs.length,
    synced_photos: 0,
    created_at: Date.now(),
  };
  await put(OUTBOX, record);
  let order = 0;
  for (const blob of photoBlobs) {
    await put(PHOTOS, {
      client_uuid: crypto.randomUUID(),
      installation_uuid: entry.client_uuid,
      blob,
      order: order,
      state: State.PENDING,
    });
    order += 1;
  }
  return record;
}

export async function listEntries() {
  const entries = await getAll(OUTBOX);
  return entries.sort((a, b) => b.created_at - a.created_at);
}

// --- Synchronisation ---------------------------------------------------------------

function payloadFor(entry) {
  return {
    client_uuid: entry.client_uuid,
    sensor_id: entry.sensor_id,
    project_id: entry.project_id,
    latitude: entry.latitude,
    longitude: entry.longitude,
    accuracy_m: entry.accuracy_m,
    captured_at: entry.captured_at,
    gps_timestamp: entry.gps_timestamp,
    description: entry.description,
  };
}

async function describeError(response) {
  try {
    const data = await response.json();
    return data.detail || Object.values(data).flat().join(" ") || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

async function photosFor(installationUuid) {
  const all = await getAll(PHOTOS);
  return all.filter((p) => p.installation_uuid === installationUuid);
}

/**
 * Synchronisiert alle offenen Outbox-Einträge. `onChange` wird bei Zustandsänderungen
 * aufgerufen (für die Statusanzeige). Netz-/Serverfehler lassen Einträge „pending“ für einen
 * späteren Versuch; 4xx-Validierungsfehler markieren sie dauerhaft als „error“.
 */
export async function sync(onChange = () => {}) {
  if (!navigator.onLine) {
    return;
  }
  const run = async () => {
    for (const entry of await getAll(OUTBOX)) {
      if (entry.state === State.DONE || entry.state === State.ERROR) {
        continue;
      }
      await syncEntry(entry, onChange);
    }
  };
  // Web Locks verhindern parallele Syncs (mehrere Tabs / gleichzeitige Trigger).
  if (navigator.locks && navigator.locks.request) {
    await navigator.locks.request("papa-sync", { ifAvailable: true }, async (lock) => {
      if (lock) {
        await run();
      }
    });
  } else {
    await run();
  }
  onChange();
}

async function syncEntry(entry, onChange) {
  const csrftoken = getCookie("csrftoken");

  // 1. Installation anlegen (idempotent über client_uuid).
  if (!entry.installation_id) {
    let response;
    try {
      response = await fetch(CREATE_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken },
        body: JSON.stringify(payloadFor(entry)),
      });
    } catch {
      return; // Netzfehler → Eintrag bleibt pending, späterer Versuch
    }
    if (response.status === 401 || response.status === 403) {
      await fail(entry, "Gerät nicht mehr angemeldet oder gesperrt.");
      onChange();
      return;
    }
    if (response.status >= 400 && response.status < 500) {
      await fail(entry, await describeError(response));
      onChange();
      return;
    }
    if (!response.ok) {
      return; // 5xx → später erneut
    }
    const installation = await response.json();
    entry.installation_id = installation.id;
    entry.state = State.INSTALLATION_SYNCED;
    await put(OUTBOX, entry);
    onChange();
  }

  // 2. Fotos einzeln hochladen (granulare Teilerfolge).
  for (const photo of await photosFor(entry.client_uuid)) {
    if (photo.state === State.DONE) {
      continue;
    }
    const form = new FormData();
    form.append("image", photo.blob, "foto.jpg");
    form.append("client_uuid", photo.client_uuid);
    form.append("order", String(photo.order));
    let response;
    try {
      response = await fetch(photoUrl(entry.client_uuid), {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrftoken },
        body: form,
      });
    } catch {
      return; // Netzfehler → später erneut
    }
    if (response.status === 401 || response.status === 403) {
      await fail(entry, "Gerät nicht mehr angemeldet oder gesperrt.");
      onChange();
      return;
    }
    if (response.status >= 400 && response.status < 500) {
      photo.state = State.ERROR;
      await put(PHOTOS, photo);
      continue; // fehlerhaftes Foto überspringen
    }
    if (!response.ok) {
      return; // 5xx → später erneut
    }
    photo.state = State.DONE;
    await put(PHOTOS, photo);
    entry.synced_photos = (entry.synced_photos || 0) + 1;
    await put(OUTBOX, entry);
    onChange();
  }

  // 3. Abschluss, wenn kein Foto mehr offen ist.
  const open = (await photosFor(entry.client_uuid)).filter(
    (p) => p.state !== State.DONE && p.state !== State.ERROR,
  );
  if (open.length === 0) {
    entry.state = State.DONE;
    await put(OUTBOX, entry);
    onChange();
  }
}

async function fail(entry, message) {
  entry.state = State.ERROR;
  entry.error = message;
  await put(OUTBOX, entry);
}
