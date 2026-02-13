// frontend/src/utils/storage.js

export function safeJsonParse(str, fallback) {
  try {
    return JSON.parse(str);
  } catch {
    return fallback;
  }
}

export function saveSetup(key, payload) {
  localStorage.setItem(key, JSON.stringify(payload));
}

export function loadSetup(key) {
  const raw = localStorage.getItem(key);
  if (!raw) return null;
  return safeJsonParse(raw, null);
}

export function clearSetup(key) {
  localStorage.removeItem(key);
}