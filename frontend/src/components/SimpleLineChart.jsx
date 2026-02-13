import React from "react";

function toPoints(data, key, w, h, pad) {
  const xs = data.map((_, i) => i);
  const ys = data.map((d) => (d[key] === null || d[key] === undefined ? null : Number(d[key])));

  const valid = ys.filter((v) => v !== null && Number.isFinite(v));
  const yMin = Math.min(...valid);
  const yMax = Math.max(...valid);
  const xMax = Math.max(...xs);

  function xScale(i) {
    if (xMax === 0) return pad;
    return pad + (i / xMax) * (w - 2 * pad);
  }

  function yScale(v) {
    if (yMax === yMin) return h / 2;
    return pad + (1 - (v - yMin) / (yMax - yMin)) * (h - 2 * pad);
  }

  const pts = data
    .map((d, i) => {
      const v = d[key];
      if (v === null || v === undefined) return null;
      const nv = Number(v);
      if (!Number.isFinite(nv)) return null;
      return [xScale(i), yScale(nv)];
    })
    .filter(Boolean);

  const dStr = pts.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  return { path: dStr, yMin, yMax };
}

export default function SimpleLineChart({ data, height = 160 }) {
  const w = 900;
  const h = height;
  const pad = 12;

  if (!data || data.length < 2) {
    return <div className="text-muted small">Not enough data to chart.</div>;
  }

  const p = toPoints(data, "portfolio_index", w, h, pad);
  const b = toPoints(data, "benchmark_index", w, h, pad);

  return (
    <div className="border rounded p-2">
      <div className="d-flex justify-content-between align-items-center mb-1">
        <div className="small text-muted">Index (start=100)</div>
        <div className="small">
          <span className="me-3">
            <span style={{ display: "inline-block", width: 10, height: 10, background: "black" }} /> Portfolio
          </span>
          <span>
            <span style={{ display: "inline-block", width: 10, height: 2, background: "black", marginBottom: 3 }} /> Benchmark
          </span>
        </div>
      </div>

      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h}>
        {/* portfolio */}
        <path d={p.path} fill="none" stroke="black" strokeWidth="2" />
        {/* benchmark (dashed) */}
        <path d={b.path} fill="none" stroke="black" strokeWidth="2" strokeDasharray="6 4" />
      </svg>
    </div>
  );
}
