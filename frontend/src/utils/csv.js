// frontend/src/utils/csv.js

function toCsvValue(v) {
  const s = v == null ? "" : String(v);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function downloadCsv({ filename, header, rows }) {
  const lines = [];
  lines.push(header.map(toCsvValue).join(","));
  for (const r of rows) lines.push(r.map(toCsvValue).join(","));

  // \ufeff helps Excel open UTF-8 cleanly
  const csvText = "\ufeff" + lines.join("\n");

  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  URL.revokeObjectURL(url);
}