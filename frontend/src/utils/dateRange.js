// frontend/src/utils/dateRange.js

export function startOfYear(d) {
  return new Date(d.getFullYear(), 0, 1);
}

export function addDays(d, days) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + days);
  return copy;
}

export function clampDate(d, minDate, maxDate) {
  let out = d;
  if (minDate && out < minDate) out = minDate;
  if (maxDate && out > maxDate) out = maxDate;
  return out;
}

// Returns { start, end } for a preset.
// Prefers dbMaxDate for "end" if available.
export function presetToRange(preset, dbMinDate, dbMaxDate) {
  const end = dbMaxDate ?? new Date();
  let start = end;

  switch (preset) {
    case "1W":
      start = addDays(end, -7);
      break;
    case "1M":
      start = addDays(end, -30);
      break;
    case "3M":
      start = addDays(end, -90);
      break;
    case "6M":
      start = addDays(end, -180);
      break;
    case "YTD":
      start = startOfYear(end);
      break;
    case "1Y":
      start = addDays(end, -365);
      break;
    default:
      return null;
  }

  // clamp to DB bounds if present
  start = clampDate(start, dbMinDate, dbMaxDate);
  return { start, end };
}
