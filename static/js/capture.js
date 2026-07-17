// Mobiler Erfassungs-Flow (offline-first): GPS ermitteln, Fotos wählen und die Erfassung in
// der lokalen Outbox ablegen. Die Synchronisation mit der REST-API übernimmt die Outbox –
// online sofort, offline sobald wieder Verbindung besteht.
"use strict";

import { State, enqueue, getRefData, listEntries, reencode, sync } from "./pwa/outbox.js";

const root = document.getElementById("capture");
if (root) {
  init(root).catch((err) => console.error(err));
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

const notifyChanged = () => window.dispatchEvent(new Event("papa:outbox-changed"));

async function init(root) {
  const gpsThreshold = parseFloat(root.dataset.gpsThreshold) || 5;
  const detailTemplate = root.dataset.detailUrl; // endet auf /0/

  const gpsStatus = document.getElementById("gpsStatus");
  const gpsWarning = document.getElementById("gpsWarning");
  const projectSelect = document.getElementById("project");
  const sensorSelect = document.getElementById("sensor");
  const sensorFilter = document.getElementById("sensorFilter");
  const photoInput = document.getElementById("photos");
  const previews = document.getElementById("photoPreviews");
  const description = document.getElementById("description");
  const submitBtn = document.getElementById("submitBtn");
  const statusBox = document.getElementById("captureStatus");
  const outboxEl = document.getElementById("outbox");

  let bestFix = null;
  let photoFiles = [];

  // --- Auswahllisten aus dem Offline-Replikat füllen ---------------------
  await populateSelect(projectSelect, await getRefData("projects"), (p) => ({
    value: p.id,
    label: `${p.number} – ${p.name}`,
  }));
  await populateSelect(sensorSelect, await getRefData("sensors"), (s) => ({
    value: s.id,
    label: s.sensor_type ? `${s.dev_eui} · ${s.sensor_type}` : s.dev_eui,
    data: { eui: s.dev_eui },
  }));

  const updateSubmitState = () => {
    submitBtn.disabled = !(bestFix && photoFiles.length > 0);
  };

  // --- GPS ---------------------------------------------------------------
  const onPosition = (pos) => {
    const { latitude, longitude, accuracy } = pos.coords;
    if (!bestFix || accuracy < bestFix.accuracy) {
      bestFix = { latitude, longitude, accuracy, timestamp: pos.timestamp };
    }
    gpsStatus.innerHTML =
      `<strong>Genauigkeit:</strong> ±${Math.round(bestFix.accuracy)} m ` +
      `<span class="text-muted">(${bestFix.latitude.toFixed(6)}, ${bestFix.longitude.toFixed(6)})</span>`;
    if (bestFix.accuracy > gpsThreshold) {
      gpsWarning.textContent =
        `Die Genauigkeit (±${Math.round(bestFix.accuracy)} m) ist schlechter als der ` +
        `Grenzwert von ${gpsThreshold} m. Bitte möglichst im Freien erneut messen.`;
      gpsWarning.classList.remove("d-none");
    } else {
      gpsWarning.classList.add("d-none");
    }
    updateSubmitState();
  };
  const onPositionError = (err) => {
    gpsStatus.innerHTML =
      `<span class="text-danger">Standort nicht verfügbar: ${escapeHtml(err.message)}. ` +
      `Bitte den Standortzugriff erlauben.</span>`;
  };
  if ("geolocation" in navigator) {
    navigator.geolocation.watchPosition(onPosition, onPositionError, {
      enableHighAccuracy: true,
      maximumAge: 0,
      timeout: 20000,
    });
  } else {
    gpsStatus.innerHTML = '<span class="text-danger">Dieses Gerät unterstützt kein GPS.</span>';
  }

  // --- Sensor-Filter -----------------------------------------------------
  sensorFilter.addEventListener("input", () => {
    const term = sensorFilter.value.trim().toUpperCase().replace(/[\s:-]/g, "");
    for (const option of sensorSelect.options) {
      const eui = (option.dataset.eui || "").toUpperCase();
      option.hidden = term !== "" && !eui.includes(term);
    }
  });

  // --- Fotos -------------------------------------------------------------
  photoInput.addEventListener("change", () => {
    for (const file of photoInput.files) {
      if (!file.type.startsWith("image/")) {
        continue;
      }
      photoFiles.push(file);
      const img = document.createElement("img");
      img.style.width = "88px";
      img.style.height = "88px";
      img.style.objectFit = "cover";
      img.className = "rounded border";
      img.src = URL.createObjectURL(file);
      img.alt = file.name;
      previews.appendChild(img);
    }
    photoInput.value = "";
    updateSubmitState();
  });

  // --- Speichern (in die Outbox) ----------------------------------------
  const setStatus = (text, kind) => {
    statusBox.textContent = text;
    statusBox.className = `alert alert-${kind}`;
  };

  submitBtn.addEventListener("click", async () => {
    if (!bestFix || photoFiles.length === 0) {
      return;
    }
    if (!projectSelect.value || !sensorSelect.value) {
      setStatus("Bitte Projekt und Sensor wählen.", "danger");
      return;
    }
    submitBtn.disabled = true;
    setStatus("Fotos werden verarbeitet …", "info");
    try {
      const blobs = [];
      for (const file of photoFiles) {
        blobs.push(await reencode(file));
      }
      const entry = {
        client_uuid: crypto.randomUUID(),
        sensor_id: parseInt(sensorSelect.value, 10),
        project_id: parseInt(projectSelect.value, 10),
        latitude: bestFix.latitude.toFixed(6),
        longitude: bestFix.longitude.toFixed(6),
        accuracy_m: bestFix.accuracy,
        captured_at: new Date().toISOString(),
        gps_timestamp: new Date(bestFix.timestamp).toISOString(),
        description: description.value,
      };
      await enqueue(entry, blobs);

      // Formular zurücksetzen und Status anzeigen.
      photoFiles = [];
      previews.innerHTML = "";
      description.value = "";
      setStatus(
        navigator.onLine
          ? "Erfassung gespeichert. Wird synchronisiert …"
          : "Offline gespeichert. Wird bei Verbindung automatisch übertragen.",
        "success",
      );
      await renderOutbox(outboxEl, detailTemplate);
      sync(notifyChanged);
    } catch (err) {
      setStatus(`Fehler: ${err.message}`, "danger");
    } finally {
      submitBtn.disabled = false;
      updateSubmitState();
    }
  });

  window.addEventListener("papa:outbox-changed", () => renderOutbox(outboxEl, detailTemplate));
  await renderOutbox(outboxEl, detailTemplate);
}

async function populateSelect(select, items, mapper) {
  for (const item of items) {
    const { value, label, data } = mapper(item);
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    if (data) {
      Object.assign(option.dataset, data);
    }
    select.appendChild(option);
  }
}

const STATE_LABEL = {
  [State.PENDING]: ['<span class="badge text-bg-secondary">wartend</span>', ""],
  [State.INSTALLATION_SYNCED]: ['<span class="badge text-bg-info">wird synchronisiert</span>', ""],
  [State.DONE]: ['<span class="badge text-bg-success">erfolgreich</span>', ""],
  [State.ERROR]: ['<span class="badge text-bg-danger">Fehler</span>', ""],
};

async function renderOutbox(container, detailTemplate) {
  if (!container) {
    return;
  }
  const entries = await listEntries();
  if (entries.length === 0) {
    container.innerHTML = '<p class="text-muted mb-0">Noch keine Erfassungen auf diesem Gerät.</p>';
    return;
  }
  const rows = entries.map((entry) => {
    const [badge] = STATE_LABEL[entry.state] || ['<span class="badge text-bg-secondary">?</span>'];
    const when = new Date(entry.created_at).toLocaleString("de-CH");
    const photos = `${entry.synced_photos || 0}/${entry.photo_count} Fotos`;
    const detail =
      entry.state === "done" && entry.installation_id
        ? `<a href="${detailTemplate.replace(/0\/$/, `${entry.installation_id}/`)}" class="btn btn-sm btn-outline-primary">Details</a>`
        : "";
    const error = entry.error ? `<div class="text-danger small">${escapeHtml(entry.error)}</div>` : "";
    return (
      '<li class="list-group-item d-flex justify-content-between align-items-center">' +
      `<div><div>${badge} <span class="text-muted small">${escapeHtml(when)}</span></div>` +
      `<div class="small text-muted">${photos}</div>${error}</div>${detail}</li>`
    );
  });
  container.innerHTML = `<ul class="list-group">${rows.join("")}</ul>`;
}
