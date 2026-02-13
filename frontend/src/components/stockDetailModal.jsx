// frontend/src/components/stockDetailModal.jsx
import React, { useMemo } from "react";
import { Modal, ModalHeader, ModalBody, Spinner } from "reactstrap";

function toNum(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtPct(v) {
  const n = toNum(v);
  if (n === null) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function fmtNum(v, digits = 4) {
  const n = toNum(v);
  if (n === null) return "—";
  return n.toFixed(digits);
}

function daysBetweenISO(a, b) {
  if (!a || !b) return null;
  const d1 = new Date(a);
  const d2 = new Date(b);
  if (Number.isNaN(d1.getTime()) || Number.isNaN(d2.getTime())) return null;
  const ms = Math.abs(d2.getTime() - d1.getTime());
  return ms / (1000 * 60 * 60 * 24);
}

function buildRiskBadges({ maxDrawdown, volAnnual }) {
  const badges = [];

  if (Number.isFinite(maxDrawdown)) {
    const dd = Math.abs(maxDrawdown);
    if (dd >= 0.5) badges.push({ text: "Very high drawdown", cls: "bg-danger" });
    else if (dd >= 0.3) badges.push({ text: "High drawdown", cls: "bg-warning text-dark" });
    else if (dd >= 0.15) badges.push({ text: "Moderate drawdown", cls: "bg-info text-dark" });
    else badges.push({ text: "Low drawdown", cls: "bg-success" });
  }

  if (Number.isFinite(volAnnual)) {
    if (volAnnual >= 0.5) badges.push({ text: "Very volatile", cls: "bg-danger" });
    else if (volAnnual >= 0.3) badges.push({ text: "Volatile", cls: "bg-warning text-dark" });
    else if (volAnnual >= 0.15) badges.push({ text: "Moderate vol", cls: "bg-info text-dark" });
    else badges.push({ text: "Lower vol", cls: "bg-success" });
  }

  return badges;
}

/**
 * Normalize whatever shape your hook/api returns into the actual details object.
 * Common shapes this handles:
 *  - { ...fields }
 *  - [ { ...fields } ]
 *  - { details: { ...fields } }
 *  - { data: { ...fields } } or { data: [ { ...fields } ] }
 */
function normalizeDetails(input) {
  if (!input) return null;

  let d = input;

  // axios sometimes returns {data: ...} but your hook likely already uses data,
  // still safe to handle:
  if (d && typeof d === "object" && "data" in d && (Array.isArray(d.data) || typeof d.data === "object")) {
    d = d.data;
  }

  if (Array.isArray(d)) d = d[0] || null;
  if (d && typeof d === "object" && "details" in d) d = d.details;

  if (Array.isArray(d)) d = d[0] || null;

  return d && typeof d === "object" ? d : null;
}

export default function StockDetailModal({
  isOpen,
  toggle,
  row,
  startDate,
  endDate,
  loading,
  error,
  details,
}) {
  const d = useMemo(() => normalizeDetails(details), [details]);

  const derived = useMemo(() => {
    if (!d) return { cagr: null, volAnnual: null, years: null, badges: [] };

    // prefer your backend keys, but tolerate alternates
    const periodReturn = toNum(d.return ?? d.period_return);
    const stddevDaily = toNum(d.stddev);

    const startIso = d.start_date ?? d.startDate ?? null;
    const endIso = d.end_date ?? d.endDate ?? null;

    const daySpan = daysBetweenISO(startIso, endIso);
    const years = daySpan != null ? daySpan / 365.25 : null;

    let cagr = null;
    if (periodReturn !== null && years && years > 0 && (1 + periodReturn) > 0) {
      cagr = Math.pow(1 + periodReturn, 1 / years) - 1;
    }

    let volAnnual = null;
    if (stddevDaily !== null) {
      volAnnual = stddevDaily * Math.sqrt(252);
    }

    const maxDrawdown = toNum(d.max_drawdown);
    const badges = buildRiskBadges({
      maxDrawdown: maxDrawdown ?? null,
      volAnnual: volAnnual ?? null,
    });

    return { cagr, volAnnual, years, badges };
  }, [d]);

  const title = row?.ticker ? `${row.ticker} • Detail` : "Stock Detail";

  // If you still see — after this change, d is null.
  // That would mean your hook isn't setting detailData at all.
  // But this normalization usually fixes it.

  return (
    <Modal isOpen={isOpen} toggle={toggle} size="lg" centered>
      <ModalHeader toggle={toggle}>{title}</ModalHeader>
      <ModalBody>
        {loading && (
          <div className="d-flex align-items-center gap-2">
            <Spinner size="sm" /> <span>Loading details…</span>
          </div>
        )}

        {!loading && error && (
          <div className="alert alert-danger mb-0" role="alert">
            {error}
          </div>
        )}

        {!loading && !error && d && (
          <div className="container-fluid px-0">
            <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
              <div>
                <div className="text-muted small">Range</div>
                <div className="fw-semibold">
                  {(d.start_date ?? "—")} → {(d.end_date ?? "—")} • {(d.trading_days ?? "—")} trading days
                </div>
              </div>

              <div className="d-flex flex-wrap gap-2">
                {derived.badges.map((b, idx) => (
                  <span key={idx} className={`badge ${b.cls}`}>
                    {b.text}
                  </span>
                ))}
              </div>
            </div>

            <div className="row g-3">
              <div className="col-12 col-md-6">
                <div className="card h-100">
                  <div className="card-body">
                    <div className="text-muted small mb-1">Performance</div>
                    <div className="d-flex justify-content-between">
                      <span>Return</span>
                      <span className="fw-semibold">{fmtPct(d.return ?? d.period_return)}</span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span>CAGR</span>
                      <span className="fw-semibold">{fmtPct(derived.cagr)}</span>
                    </div>
                    <hr />
                    <div className="d-flex justify-content-between">
                      <span>Start Adj Close</span>
                      <span>{d.start_adj_close ?? "—"}</span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span>End Adj Close</span>
                      <span>{d.end_adj_close ?? "—"}</span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span>Dollar Change</span>
                      <span>{d.dollar_change ?? "—"}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="col-12 col-md-6">
                <div className="card h-100">
                  <div className="card-body">
                    <div className="text-muted small mb-1">Risk</div>
                    <div className="d-flex justify-content-between">
                      <span>Daily Std Dev</span>
                      <span className="fw-semibold">{fmtNum(d.stddev, 6)}</span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span>Annualized Vol</span>
                      <span className="fw-semibold">{fmtPct(derived.volAnnual)}</span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span>Max Drawdown</span>
                      <span className="fw-semibold">{fmtPct(d.max_drawdown)}</span>
                    </div>

                    {(d.max_drawdown_start_date || d.max_drawdown_end_date) && (
                      <div className="text-muted small mt-2">
                        Peak: {d.max_drawdown_start_date ?? "—"} • Trough: {d.max_drawdown_end_date ?? "—"}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="col-12">
                <div className="card">
                  <div className="card-body">
                    <div className="text-muted small mb-2">Benchmark & Ratios</div>

                    <div className="row g-2">
                      <div className="col-12 col-md-4">
                        <div className="d-flex justify-content-between">
                          <span>Benchmark Return</span>
                          <span className="fw-semibold">{fmtPct(d.benchmark_return)}</span>
                        </div>
                        <div className="d-flex justify-content-between">
                          <span>Benchmark Std Dev</span>
                          <span className="fw-semibold">{fmtNum(d.benchmark_stddev, 6)}</span>
                        </div>
                      </div>

                      <div className="col-12 col-md-4">
                        <div className="d-flex justify-content-between">
                          <span>Ticker Sharpe</span>
                          <span className="fw-semibold">{fmtNum(d.ticker_sharpe, 3)}</span>
                        </div>
                        <div className="d-flex justify-content-between">
                          <span>Benchmark Sharpe</span>
                          <span className="fw-semibold">{fmtNum(d.benchmark_sharpe, 3)}</span>
                        </div>
                      </div>

                      <div className="col-12 col-md-4">
                        <div className="d-flex justify-content-between">
                          <span>Info Ratio</span>
                          <span className="fw-semibold">{fmtNum(d.information_ratio, 3)}</span>
                        </div>
                        <div className="d-flex justify-content-between">
                          <span>Alpha</span>
                          <span className="fw-semibold">{fmtPct(d.alpha)}</span>
                        </div>
                        {/*  */}
                        <div className="d-flex justify-content-between">
                          <span>Beta</span>
                          <span className="fw-semibold">{fmtNum(d.beta, 3)}</span>
                        </div>
                        <div className="d-flex justify-content-between">
                          <span>Correlation</span>
                          <span className="fw-semibold">{fmtNum(d.correlation, 3)}</span>
                        </div>
                        {/*  */}
                      </div>
                    </div>

                  </div>
                </div>
              </div>

              <div className="col-12">
                <div className="card">
                  <div className="card-body">
                    <div className="text-muted small mb-2">Best & Worst Day</div>
                    <div className="row g-2">
                      <div className="col-12 col-md-6">
                        <div className="d-flex justify-content-between">
                          <span>Best Day</span>
                          <span className="fw-semibold">
                            {d.best_day_date ?? "—"} • {fmtPct(d.best_day_return)}
                          </span>
                        </div>
                      </div>
                      <div className="col-12 col-md-6">
                        <div className="d-flex justify-content-between">
                          <span>Worst Day</span>
                          <span className="fw-semibold">
                            {d.worst_day_date ?? "—"} • {fmtPct(d.worst_day_return)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          </div>
        )}

        {!loading && !error && !d && (
          <div className="alert alert-warning mb-0" role="alert">
            Detail data wasn’t in the expected shape. (Normalization didn’t find an object.)
          </div>
        )}
      </ModalBody>
    </Modal>
  );
}
