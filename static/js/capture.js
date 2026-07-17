// Mobiler Erfassungs-Flow: GPS ermitteln, Fotos wählen und die Installation samt Fotos
// idempotent über die REST-API speichern. Läuft als natives ES-Modul (kein Build-Schritt).
"use strict";

const root = document.getElementById("capture");
if (root) {
  init(root);
}

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : "";
}

function init(root) {
  const createUrl = root.dataset.createUrl;
  const photoUrlTemplate = root.dataset.photoUrl; // enthält Platzhalter-UUID
  const detailUrlTemplate = root.dataset.detailUrl; // endet auf /0/
  const gpsThreshold = parseFloat(root.dataset.gpsThreshold) || 5;

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

  let bestFix = null;
  let photos = [];

  // --- GPS ---------------------------------------------------------------
  const updateSubmitState = () => {
    submitBtn.disabled = !(bestFix && photos.length > 0);
  };

  const onPosition = (pos) => {
    const { latitude, longitude, accuracy } = pos.coords;
    // Beste (genaueste) Messung behalten.
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
      `<span class="text-danger">Standort nicht verfügbar: ${err.message}. ` +
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
      const entry = { file, clientUuid: crypto.randomUUID() };
      photos.push(entry);
      const img = document.createElement("img");
      img.style.width = "88px";
      img.style.height = "88px";
      img.style.objectFit = "cover";
      img.className = "rounded border";
      img.src = URL.createObjectURL(file);
      img.alt = file.name;
      previews.appendChild(img);
    }
    photoInput.value = ""; // erneutes Wählen desselben Fotos erlauben
    updateSubmitState();
  });

  // --- Speichern ---------------------------------------------------------
  const setStatus = (text, kind) => {
    statusBox.textContent = text;
    statusBox.className = `alert alert-${kind}`;
  };

  submitBtn.addEventListener("click", async () => {
    if (!bestFix || photos.length === 0) {
      return;
    }
    if (!projectSelect.value || !sensorSelect.value) {
      setStatus("Bitte Projekt und Sensor wählen.", "danger");
      return;
    }

    submitBtn.disabled = true;
    setStatus("Installation wird gespeichert …", "info");
    const csrftoken = getCookie("csrftoken");
    const installationUuid = crypto.randomUUID();

    try {
      const createResponse = await fetch(createUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken },
        body: JSON.stringify({
          client_uuid: installationUuid,
          sensor_id: parseInt(sensorSelect.value, 10),
          project_id: parseInt(projectSelect.value, 10),
          latitude: bestFix.latitude.toFixed(6),
          longitude: bestFix.longitude.toFixed(6),
          accuracy_m: bestFix.accuracy,
          captured_at: new Date().toISOString(),
          gps_timestamp: new Date(bestFix.timestamp).toISOString(),
          description: description.value,
        }),
      });
      if (!createResponse.ok) {
        throw new Error(await describeError(createResponse));
      }
      const installation = await createResponse.json();

      // Fotos einzeln hochladen (granulare Teilerfolge).
      const photoUrl = photoUrlTemplate.replace(
        "00000000-0000-0000-0000-000000000000",
        installationUuid,
      );
      let done = 0;
      for (const entry of photos) {
        setStatus(`Foto ${done + 1} von ${photos.length} wird hochgeladen …`, "info");
        const form = new FormData();
        form.append("image", entry.file);
        form.append("client_uuid", entry.clientUuid);
        form.append("order", String(done));
        const photoResponse = await fetch(photoUrl, {
          method: "POST",
          headers: { "X-CSRFToken": csrftoken },
          body: form,
        });
        if (!photoResponse.ok) {
          throw new Error(await describeError(photoResponse));
        }
        done += 1;
      }

      setStatus("Gespeichert. Weiterleitung …", "success");
      window.location.href = detailUrlTemplate.replace(/0\/$/, `${installation.id}/`);
    } catch (err) {
      setStatus(`Fehler beim Speichern: ${err.message}`, "danger");
      submitBtn.disabled = false;
    }
  });
}

async function describeError(response) {
  try {
    const data = await response.json();
    if (data.detail) {
      return data.detail;
    }
    return Object.values(data).flat().join(" ");
  } catch {
    return `HTTP ${response.status}`;
  }
}
