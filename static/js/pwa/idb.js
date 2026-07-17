// Minimaler IndexedDB-Zugriff für das Offline-Replikat und die Outbox (natives ES-Modul).
"use strict";

const DB_NAME = "papa";
const DB_VERSION = 1;

let dbPromise = null;

export function openDB() {
  if (dbPromise) {
    return dbPromise;
  }
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("refdata")) {
        db.createObjectStore("refdata", { keyPath: "key" });
      }
      if (!db.objectStoreNames.contains("outbox")) {
        db.createObjectStore("outbox", { keyPath: "client_uuid" });
      }
      if (!db.objectStoreNames.contains("photos")) {
        const store = db.createObjectStore("photos", { keyPath: "client_uuid" });
        store.createIndex("by_installation", "installation_uuid", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return dbPromise;
}

function asPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function put(store, value) {
  const db = await openDB();
  return asPromise(db.transaction(store, "readwrite").objectStore(store).put(value));
}

export async function get(store, key) {
  const db = await openDB();
  return asPromise(db.transaction(store, "readonly").objectStore(store).get(key));
}

export async function getAll(store) {
  const db = await openDB();
  return asPromise(db.transaction(store, "readonly").objectStore(store).getAll());
}

export async function remove(store, key) {
  const db = await openDB();
  return asPromise(db.transaction(store, "readwrite").objectStore(store).delete(key));
}
