// frontend/src/utils/format.js

// ---------- numbers ----------
export function numOrNull(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function fmtNumber(v, decimals = 4) {
  const n = numOrNull(v);
  if (n == null) return "—";
  return n.toFixed(decimals);
}

export function fmtMoney(v, decimals = 2) {
  const n = numOrNull(v);
  if (n == null) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

// backend returns FRACTIONS (0.10 = 10%)
export function fmtPercentFromFraction(v, decimals = 2) {
  const n = numOrNull(v);
  if (n == null) return "—";
  return `${(n * 100).toFixed(decimals)}%`;
}

export function signClass(n) {
  if (n == null) return "text-muted";
  if (n > 0) return "text-success";
  if (n < 0) return "text-danger";
  return "text-muted";
}

// ---------- dates ----------
export function fmtDate(d) {
  // Date object -> YYYY-MM-DD
  return d?.toISOString?.().slice(0, 10) ?? "";
}

export function fmtIsoDate(s) {
  // expects "YYYY-MM-DD" from backend
  if (!s) return "—";
  return String(s);
}
