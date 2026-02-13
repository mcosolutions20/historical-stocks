import React, { useEffect, useState } from "react";
import {
  listPortfolios,
  createPortfolio,
  getPortfolio,
  updatePortfolio,
  deletePortfolio,
  getPortfolioValuation,
  getPortfolioPerformance,
  exportPortfolioPerformanceCsv,
  rebalancePortfolio,
  listTransactions,
  createTransaction,
  deleteTransaction,
  exportTransactionsCsv,
  importTransactionsCsv,
} from "../api";
import SimpleLineChart from "./SimpleLineChart";

export default function PortfolioManager({ userInfo }) {
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");

  const [portfolios, setPortfolios] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null); // includes derived holdings + txs
  const [valuation, setValuation] = useState(null);

  // Portfolio create/edit
  const [newName, setNewName] = useState("");
  const [newCash, setNewCash] = useState("0");
  const [editName, setEditName] = useState("");
  const [editCash, setEditCash] = useState("");

  // Performance
  const [perf, setPerf] = useState(null);
  const [perfStart, setPerfStart] = useState("2024-01-01");
  const [perfEnd, setPerfEnd] = useState("2026-01-31");
  const [benchmark, setBenchmark] = useState("SP500");

  // Rebalance
  const [targetsText, setTargetsText] = useState("AAPL=0.30\nMSFT=0.30\nSPY=0.40");
  const [rebalance, setRebalance] = useState(null);
  const [includeCashInTotal, setIncludeCashInTotal] = useState(true);

  // New transaction
  const [txTicker, setTxTicker] = useState("");
  const [txSide, setTxSide] = useState("BUY");
  const [txShares, setTxShares] = useState("");
  const [txPrice, setTxPrice] = useState("");
  const [useClosePrice, setUseClosePrice] = useState(true);
  const [csvFile, setCsvFile] = useState(null);
  const [txDate, setTxDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [txNotes, setTxNotes] = useState("");

  const canUse = !!userInfo?.is_verified;

  function flash(msg, ms = 2200) {
    setToast(msg);
    setTimeout(() => setToast(""), ms);
  }

  function fmtMoney(x) {
    const n = Number(x);
    if (!Number.isFinite(n)) return "-";
    return `$${n.toFixed(2)}`;
  }

  function fmtPct(x) {
    const n = Number(x);
    if (!Number.isFinite(n)) return "-";
    return `${(n * 100).toFixed(2)}%`;
  }

  async function refreshList() {
    const res = await listPortfolios();
    setPortfolios(res.portfolios || []);
  }

  async function refreshSelected(id) {
    const res = await getPortfolio(id);
    setSelected(res);
    setEditName(res?.portfolio?.name || "");
    setEditCash(String(res?.portfolio?.cash_balance ?? 0));
  }

  async function refreshValuation(id) {
    const res = await getPortfolioValuation(id);
    setValuation(res);
  }

  async function refreshTransactions(id) {
    const res = await listTransactions(id);
    // keep selected in sync (so holdings derived display stays current)
    await refreshSelected(id);
    return res;
  }

  useEffect(() => {
    if (!canUse) return;
    refreshList().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse]);

  async function handleCreate() {
    const name = newName.trim();
    const cash = Number(newCash);
    if (name.length < 2) return flash("Name too short.");
    if (!Number.isFinite(cash) || cash < 0) return flash("Cash must be >= 0.");

    try {
      setLoading(true);
      const res = await createPortfolio(name, cash);
      setNewName("");
      setNewCash("0");
      await refreshList();

      const id = res?.portfolio?.id;
      if (id) {
        setSelectedId(id);
        setSelected(null);
        setValuation(null);
        setPerf(null);
        setRebalance(null);
        await refreshSelected(id);
        await refreshValuation(id);
      }
      flash("Portfolio created.");
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to create portfolio.", 3000);
    } finally {
      setLoading(false);
    }
  }

  async function handleSelect(id) {
    setSelectedId(id);
    setSelected(null);
    setValuation(null);
    setPerf(null);
    setRebalance(null);

    try {
      setLoading(true);
      await refreshSelected(id);
      await refreshValuation(id);
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to load portfolio.", 3000);
    } finally {
      setLoading(false);
    }
  }

  async function handleSavePortfolio() {
    if (!selectedId) return;

    const name = editName.trim();
    const cash = Number(editCash);
    if (name.length < 2) return flash("Name too short.");
    if (!Number.isFinite(cash) || cash < 0) return flash("Cash must be >= 0.");

    try {
      setLoading(true);
      await updatePortfolio(selectedId, { name, cash_balance: cash });
      await refreshList();
      await refreshSelected(selectedId);
      await refreshValuation(selectedId);
      flash("Portfolio saved.");
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to save portfolio.", 3000);
    } finally {
      setLoading(false);
    }
  }

  async function handleDeletePortfolio() {
    if (!selectedId) return;
    if (!confirm("Delete this portfolio? Transactions will also be deleted.")) return;

    try {
      setLoading(true);
      await deletePortfolio(selectedId);
      setSelectedId(null);
      setSelected(null);
      setValuation(null);
      setPerf(null);
      setRebalance(null);
      await refreshList();
      flash("Portfolio deleted.");
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to delete portfolio.", 3000);
    } finally {
      setLoading(false);
    }
  }

  async function handleAddTransaction() {
    if (!selectedId) return;

    const ticker = txTicker.trim().toUpperCase();
    const side = txSide;
    const shares = Number(txShares);
    const trade_date = txDate;

    // If "Use close price" is enabled, we send price=null and backend auto-fills from your DB.
    const price = useClosePrice ? null : Number(txPrice);

    if (!ticker) return flash("Ticker required.");
    if (!Number.isFinite(shares) || shares <= 0) return flash("Shares must be > 0.");
    if (!trade_date) return flash("Trade date required.");
    if (!useClosePrice && (!Number.isFinite(price) || price <= 0)) return flash("Price must be > 0.");

    try {
      setLoading(true);
      await createTransaction(selectedId, {
        ticker,
        side,
        shares,
        price,
        trade_date,
        notes: txNotes.trim() || null,
      });

      setTxTicker("");
      setTxShares("");
      setTxPrice("");
      setTxNotes("");

      await refreshSelected(selectedId);
      await refreshValuation(selectedId);
      setPerf(null);
      setRebalance(null);

      flash("Transaction added.");
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to add transaction.", 3500);
    } finally {
      setLoading(false);
    }
  }


  async function handleExportTransactionsCsv() {
    if (!selectedId) return;
    try {
      setLoading(true);
      const res = await exportTransactionsCsv(selectedId);
      const blob = new Blob([res.data], { type: "text/csv" });

      // Try to pull filename from Content-Disposition
      const cd = res.headers?.["content-disposition"] || "";
      const match = cd.match(/filename="([^"]+)"/);
      const filename = match?.[1] || `portfolio_${selectedId}_transactions.csv`;

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      flash("CSV exported.");
    } catch (e) {
      flash("Failed to export CSV.", 3500);
    } finally {
      setLoading(false);
    }
  }

  async function handleImportTransactionsCsv() {
    if (!selectedId) return;
    if (!csvFile) return flash("Choose a CSV file first.");

    try {
      setLoading(true);
      await importTransactionsCsv(selectedId, csvFile);
      setCsvFile(null);

      await refreshSelected(selectedId);
      await refreshValuation(selectedId);
      setPerf(null);
      setRebalance(null);

      flash("CSV imported.");
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail?.errors) {
        flash(`CSV import failed (see console).`, 4000);
        console.error("CSV import errors:", detail);
      } else {
        flash(detail?.message || detail || "CSV import failed.", 4000);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteTx(tx) {
    if (!confirm(`Delete transaction #${tx.id}?`)) return;
    try {
      setLoading(true);
      await deleteTransaction(tx.id);
      await refreshSelected(selectedId);
      await refreshValuation(selectedId);
      setPerf(null);
      setRebalance(null);
      flash("Transaction deleted.");
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to delete transaction.", 3500);
    } finally {
      setLoading(false);
    }
  }

  function parseTargetsText(txt) {
    const lines = (txt || "")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);

    const targets = [];
    for (const line of lines) {
      const parts = line.split("=");
      if (parts.length !== 2) continue;
      const ticker = parts[0].trim().toUpperCase();
      const w = Number(parts[1].trim());
      if (!ticker) continue;
      if (!Number.isFinite(w)) continue;
      targets.push({ ticker, weight: w });
    }
    return targets;
  }

  async function handleRunPerformance() {
    if (!selectedId) return;
    try {
      setLoading(true);
      const res = await getPortfolioPerformance(selectedId, { start: perfStart, end: perfEnd, benchmark });
      setPerf(res);
      flash("Performance loaded.");
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to load performance.", 3500);
    } finally {
      setLoading(false);
    }
  }

  async function handleExportPerformanceCsv() {
    if (!selectedId) return;
    try {
      setLoading(true);
      const res = await exportPortfolioPerformanceCsv(selectedId, {
        start: perfStart,
        end: perfEnd,
        benchmark,
      });
      const blob = new Blob([res.data], { type: "text/csv" });

      const cd = res.headers?.["content-disposition"] || "";
      const match = cd.match(/filename="([^"]+)"/);
      const filename = match?.[1] || `portfolio_${selectedId}_performance_${perfStart}_${perfEnd}.csv`;

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      flash("Performance CSV exported.");
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to export performance CSV.", 3500);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunRebalance() {
    if (!selectedId) return;

    const targets = parseTargetsText(targetsText);
    if (targets.length === 0) return flash("Add targets like AAPL=0.25");

    try {
      setLoading(true);
      const res = await rebalancePortfolio(selectedId, { targets, include_cash_in_total: includeCashInTotal });
      setRebalance(res);
      flash("Rebalance calculated.");
    } catch (e) {
      flash(e?.response?.data?.detail || "Failed to rebalance.", 3500);
    } finally {
      setLoading(false);
    }
  }

  if (!canUse) {
    return (
      <div className="container mt-3">
        <div className="alert alert-secondary mb-0">Verify your email to use Portfolio features.</div>
      </div>
    );
  }

  return (
    <div className="container mt-3">
      {toast && <div className="alert alert-info py-2">{toast}</div>}

      <div className="card shadow-sm">
        <div className="card-body">
          <div className="d-flex justify-content-between align-items-center mb-2">
            <div className="fw-semibold">Portfolios</div>
            <button className="btn btn-sm btn-outline-secondary" onClick={refreshList} disabled={loading}>
              Refresh
            </button>
          </div>

          {/* Create */}
          <div className="row g-2 mb-3">
            <div className="col-md-6">
              <input className="form-control" placeholder="New portfolio name" value={newName} onChange={(e) => setNewName(e.target.value)} />
            </div>
            <div className="col-md-4">
              <input className="form-control" placeholder="Starting cash (e.g. 5000)" value={newCash} onChange={(e) => setNewCash(e.target.value)} />
            </div>
            <div className="col-md-2">
              <button className="btn btn-primary w-100" onClick={handleCreate} disabled={loading}>
                Create
              </button>
            </div>
          </div>

          <div className="row g-3">
            {/* list */}
            <div className="col-md-4">
              <div className="list-group">
                {portfolios.map((p) => (
                  <button
                    key={p.id}
                    className={`list-group-item list-group-item-action ${p.id === selectedId ? "active" : ""}`}
                    onClick={() => handleSelect(p.id)}
                    disabled={loading}
                  >
                    <div className="d-flex justify-content-between">
                      <span>{p.name}</span>
                      <span className="small">{fmtMoney(p.cash_balance)}</span>
                    </div>
                  </button>
                ))}
                {portfolios.length === 0 && <div className="text-muted small">No portfolios yet.</div>}
              </div>
            </div>

            {/* detail */}
            <div className="col-md-8">
              {!selected ? (
                <div className="text-muted">Select a portfolio to view transactions and analytics.</div>
              ) : (
                <>
                  {/* Portfolio Settings */}
                  <div className="card mb-3">
                    <div className="card-body">
                      <div className="fw-semibold mb-2">Portfolio Settings</div>
                      <div className="row g-2">
                        <div className="col-md-6">
                          <label className="form-label">Name</label>
                          <input className="form-control" value={editName} onChange={(e) => setEditName(e.target.value)} />
                        </div>
                        <div className="col-md-4">
                          <label className="form-label">Starting Cash</label>
                          <input className="form-control" value={editCash} onChange={(e) => setEditCash(e.target.value)} />
                        </div>
                        <div className="col-md-2 d-flex align-items-end">
                          <button className="btn btn-primary w-100" onClick={handleSavePortfolio} disabled={loading}>
                            Save
                          </button>
                        </div>
                        <div className="col-12">
                          <button className="btn btn-outline-danger" onClick={handleDeletePortfolio} disabled={loading}>
                            Delete Portfolio
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Valuation */}
                  <div className="card mb-3">
                    <div className="card-body">
                      <div className="d-flex justify-content-between align-items-center">
                        <div className="fw-semibold">Valuation, Allocation, Unrealized P/L</div>
                        <button className="btn btn-sm btn-outline-secondary" disabled={loading} onClick={() => refreshValuation(selectedId)}>
                          Refresh
                        </button>
                      </div>

                      {!valuation ? (
                        <div className="text-muted mt-2">No valuation loaded.</div>
                      ) : (
                        <>
                          <div className="row mt-2">
                            <div className="col-md-3">
                              <div className="small text-muted">Holdings Value</div>
                              <div className="fw-semibold">{fmtMoney(valuation.totals.holdings_value)}</div>
                            </div>
                            <div className="col-md-3">
                              <div className="small text-muted">Cash (current)</div>
                              <div className="fw-semibold">{fmtMoney(valuation.totals.cash_current)}</div>
                            </div>
                            <div className="col-md-3">
                              <div className="small text-muted">Total Value</div>
                              <div className="fw-semibold">{fmtMoney(valuation.totals.total_value)}</div>
                            </div>
                            <div className="col-md-3">
                              <div className="small text-muted">Unrealized P/L</div>
                              <div className="fw-semibold">
                                {valuation.totals.unrealized_pl_total === null ? "-" : fmtMoney(valuation.totals.unrealized_pl_total)}
                                <span className="text-muted ms-2">
                                  {valuation.totals.unrealized_pl_pct_on_cost === null ? "" : `(${fmtPct(valuation.totals.unrealized_pl_pct_on_cost)})`}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className="table-responsive mt-3">
                            <table className="table table-sm align-middle">
                              <thead>
                                <tr>
                                  <th>Ticker</th>
                                  <th className="text-end">Shares</th>
                                  <th className="text-end">Avg Cost</th>
                                  <th className="text-end">Last Price</th>
                                  <th className="text-end">Market Value</th>
                                  <th className="text-end">Weight</th>
                                  <th className="text-end">Unrealized</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(valuation.positions || []).map((p) => (
                                  <tr key={p.ticker}>
                                    <td>{p.ticker}</td>
                                    <td className="text-end">{p.shares.toFixed(4)}</td>
                                    <td className="text-end">{fmtMoney(p.avg_cost)}</td>
                                    <td className="text-end">{p.last_price === null ? "-" : fmtMoney(p.last_price)}</td>
                                    <td className="text-end">{fmtMoney(p.market_value)}</td>
                                    <td className="text-end">{fmtPct(p.weight)}</td>
                                    <td className="text-end">
                                      {p.unrealized_pl === null ? "-" : fmtMoney(p.unrealized_pl)}
                                      <span className="text-muted ms-2">{p.unrealized_pl_pct === null ? "" : `(${fmtPct(p.unrealized_pl_pct)})`}</span>
                                    </td>
                                  </tr>
                                ))}
                                {(valuation.positions || []).length === 0 && (
                                  <tr>
                                    <td colSpan="7" className="text-muted">
                                      No positions yet. Add transactions below.
                                    </td>
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Performance */}
                  <div className="card mb-3">
                    <div className="card-body">
                      <div className="fw-semibold mb-2">Performance (Portfolio vs SP500 Dataset Index)</div>

                      <div className="row g-2 mb-2">
                        <div className="col-md-3">
                          <label className="form-label">Start</label>
                          <input className="form-control" value={perfStart} onChange={(e) => setPerfStart(e.target.value)} />
                        </div>
                        <div className="col-md-3">
                          <label className="form-label">End</label>
                          <input className="form-control" value={perfEnd} onChange={(e) => setPerfEnd(e.target.value)} />
                        </div>
                        <div className="col-md-3">
                          <label className="form-label">Benchmark</label>
                          <input className="form-control" value={benchmark} onChange={(e) => setBenchmark(e.target.value.toUpperCase())} />
                          <div className="form-text">Use SP500 to compare against the full dataset index.</div>
                        </div>
                        <div className="col-md-3 d-flex align-items-end">
                          <div className="d-grid gap-2 w-100">
                            <button className="btn btn-outline-primary" onClick={handleRunPerformance} disabled={loading}>
                              Load Performance
                            </button>
                            <button className="btn btn-outline-secondary" onClick={handleExportPerformanceCsv} disabled={loading || !perf}>
                              Export Performance CSV
                            </button>
                          </div>
                        </div>
                      </div>

                      {!perf ? (
                        <div className="text-muted small">Load performance to see chart and series.</div>
                      ) : (
                        <SimpleLineChart data={perf.series} height={180} />
                      )}
                    </div>
                  </div>

                  {/* Rebalance */}
                  <div className="card mb-3">
                    <div className="card-body">
                      <div className="fw-semibold mb-2">Rebalance Helper</div>

                      <div className="row g-2">
                        <div className="col-md-8">
                          <label className="form-label">Targets (one per line)</label>
                          <textarea className="form-control" rows="5" value={targetsText} onChange={(e) => setTargetsText(e.target.value)} />
                          <div className="form-text">Format: AAPL=0.25 (weights sum ≤ 1.0)</div>
                        </div>
                        <div className="col-md-4">
                          <label className="form-label">Options</label>
                          <div className="form-check mb-2">
                            <input className="form-check-input" type="checkbox" checked={includeCashInTotal} onChange={(e) => setIncludeCashInTotal(e.target.checked)} id="cashOpt" />
                            <label className="form-check-label" htmlFor="cashOpt">
                              Include cash in total
                            </label>
                          </div>
                          <button className="btn btn-outline-primary w-100" onClick={handleRunRebalance} disabled={loading}>
                            Calculate Rebalance
                          </button>
                        </div>
                      </div>

                      {rebalance && (
                        <div className="table-responsive mt-3">
                          <table className="table table-sm align-middle">
                            <thead>
                              <tr>
                                <th>Ticker</th>
                                <th className="text-end">Current %</th>
                                <th className="text-end">Target %</th>
                                <th className="text-end">Delta $</th>
                                <th className="text-end">Delta Shares</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rebalance.suggestions.map((s) => (
                                <tr key={s.ticker}>
                                  <td>{s.ticker}</td>
                                  <td className="text-end">{fmtPct(s.current_weight)}</td>
                                  <td className="text-end">{fmtPct(s.target_weight)}</td>
                                  <td className="text-end">{fmtMoney(s.delta_value)}</td>
                                  <td className="text-end">{s.delta_shares === null ? "-" : Number(s.delta_shares).toFixed(4)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <div className="text-muted small">{rebalance.note}</div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Transactions */}
                  <div className="card mb-3">
                    <div className="card-body">
                      <div className="fw-semibold mb-2">Transactions</div>

                      <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
                          <button className="btn btn-sm btn-outline-secondary" onClick={handleExportTransactionsCsv} disabled={!selectedId || loading}>
                            Export CSV
                          </button>

                          <div className="d-flex align-items-center gap-2">
                            <input
                              type="file"
                              accept=".csv"
                              className="form-control form-control-sm"
                              style={{ maxWidth: 260 }}
                              onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                              disabled={!selectedId || loading}
                            />
                            <button className="btn btn-sm btn-outline-primary" onClick={handleImportTransactionsCsv} disabled={!selectedId || loading || !csvFile}>
                              Import CSV
                            </button>
                          </div>

                          <span className="text-muted small">
                            Columns: ticker, side, shares, price(optional), trade_date, notes(optional)
                          </span>
                        </div>

                        <div className="row g-2 align-items-end">
                        <div className="col-md-2">
                          <label className="form-label">Ticker</label>
                          <input className="form-control" value={txTicker} onChange={(e) => setTxTicker(e.target.value)} placeholder="AAPL" />
                        </div>
                        <div className="col-md-2">
                          <label className="form-label">Side</label>
                          <select className="form-select" value={txSide} onChange={(e) => setTxSide(e.target.value)}>
                            <option value="BUY">BUY</option>
                            <option value="SELL">SELL</option>
                          </select>
                        </div>
                        <div className="col-md-2">
                          <label className="form-label">Shares</label>
                          <input className="form-control" value={txShares} onChange={(e) => setTxShares(e.target.value)} placeholder="10" />
                        </div>
                        <div className="col-md-2">
                          <label className="form-label d-flex justify-content-between align-items-center">
                            <span>Price</span>
                            <span className="form-check form-check-inline m-0">
                              <input
                                className="form-check-input"
                                type="checkbox"
                                checked={useClosePrice}
                                onChange={(e) => setUseClosePrice(e.target.checked)}
                                id="useClosePrice"
                              />
                              <label className="form-check-label small" htmlFor="useClosePrice">Use close</label>
                            </span>
                          </label>
                          <input
                            className="form-control"
                            value={txPrice}
                            onChange={(e) => setTxPrice(e.target.value)}
                            placeholder={useClosePrice ? "(auto from DB)" : "195.12"}
                            disabled={useClosePrice}
                          />
                        </div>
                        <div className="col-md-2">
                          <label className="form-label">Date</label>
                          <input className="form-control" type="date" value={txDate} onChange={(e) => setTxDate(e.target.value)} />
                        </div>
                        <div className="col-md-2">
                          <button className="btn btn-primary w-100" onClick={handleAddTransaction} disabled={loading}>
                            Add
                          </button>
                        </div>

                        <div className="col-12">
                          <label className="form-label">Notes (optional)</label>
                          <input className="form-control" value={txNotes} onChange={(e) => setTxNotes(e.target.value)} placeholder="Optional notes" />
                        </div>
                      </div>

                      <div className="table-responsive mt-3">
                        <table className="table table-sm align-middle">
                          <thead>
                            <tr>
                              <th>ID</th>
                              <th>Date</th>
                              <th>Ticker</th>
                              <th>Side</th>
                              <th className="text-end">Shares</th>
                              <th className="text-end">Price</th>
                              <th className="text-end">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(selected.transactions || []).map((t) => (
                              <tr key={t.id}>
                                <td>{t.id}</td>
                                <td>{String(t.trade_date).slice(0, 10)}</td>
                                <td>{t.ticker}</td>
                                <td>{t.side}</td>
                                <td className="text-end">{Number(t.shares).toFixed(4)}</td>
                                <td className="text-end">{fmtMoney(t.price)}</td>
                                <td className="text-end">
                                  <button className="btn btn-sm btn-outline-danger" disabled={loading} onClick={() => handleDeleteTx(t)}>
                                    Delete
                                  </button>
                                </td>
                              </tr>
                            ))}
                            {(selected.transactions || []).length === 0 && (
                              <tr>
                                <td colSpan="7" className="text-muted">
                                  No transactions yet.
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>

                      <div className="text-muted small">
                        Holdings are derived from transactions (avg-cost). Sells that exceed owned shares are blocked.
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}