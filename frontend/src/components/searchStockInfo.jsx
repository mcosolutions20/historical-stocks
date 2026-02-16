// frontend/src/components/searchStockInfo.jsx
import React from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import {
  ButtonDropdown,
  DropdownToggle,
  DropdownMenu,
  DropdownItem,
} from "reactstrap";

import StockDetailModal from "./stockDetailModal";
import ResultsTable from "./ResultsTable";

import useStockMeta from "../hooks/useStockMeta";
import useStockDetails from "../hooks/useStockDetails";
import useSorting from "../hooks/useSorting";
import useSearchState from "../hooks/useSearchState";
import { createCheckoutSession } from "../api";

const STORAGE_KEY = "historical-stocks:savedSetup";

function SearchStock({ userInfo, planInfo, onAuthChanged }) {
  const { meta, dbMinDate, dbMaxDate } = useStockMeta();
  const s = useSearchState({ dbMinDate, dbMaxDate, storageKey: STORAGE_KEY });

  const { sortKey, sortDir, sortedRows, handleHeaderSort } = useSorting({
    rows: s.rows,
    mode: s.mode,
  });

  const {
    detailOpen,
    detailRow,
    detailLoading,
    detailError,
    detailData,
    openDetail,
    closeDetail,
  } = useStockDetails({ startDate: s.startDate, endDate: s.endDate });

  async function handleSubmit(e) {
    e.preventDefault();
    await s.submitSearch();
    onAuthChanged?.();
  }

  async function handleUpgrade() {
    try {
      const res = await createCheckoutSession();

      // Stripe path
      if (res?.url) {
        window.location.href = res.url;
        return;
      }

      // Dev bypass path
      if (res?.dev_upgraded) {
        alert("Dev mode: upgraded to PRO for 24h window (Stripe bypass).");
        onAuthChanged?.();
        await s.submitSearch(); // auto-retry after upgrading
        return;
      }

      alert("Upgrade is not available right now (no checkout URL returned).");
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;

      if (status === 501 && detail?.code === "billing_not_configured") {
        alert(
          `Billing not configured in this environment.\n\n${detail.message}\n\nTip: set DEV_BILLING_BYPASS=true in .env.docker to test PRO features without Stripe.`
        );
        return;
      }

      const msg =
        detail?.message ||
        detail?.detail ||
        err?.response?.data?.detail ||
        err?.message ||
        "Upgrade failed.";

      alert(String(msg));
    }
  }

  return (
    <div className="container py-4">
      {/* Usage banner (single banner) */}
      {s.usage && (
        <div className="alert alert-info d-flex justify-content-between align-items-center">
          <div>
            <strong>{s.usage.plan.toUpperCase()}</strong> plan —{" "}
            {s.usage.searches_used} / {s.usage.limit} searches used
          </div>
          {s.needsUpgrade && (
            <div className="d-flex flex-column align-items-end gap-1">
              <button className="btn btn-sm btn-warning" onClick={handleUpgrade}>
                Upgrade (demo checkout)
              </button>

              <div className="text-end" style={{ fontSize: 12, opacity: 0.85 }}>
                This site uses Stripe <strong>test mode</strong> (no real charges). Use card{" "}
                <code>4242 4242 4242 4242</code>.
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0 ms-2"
                  onClick={() => {
                    navigator.clipboard?.writeText("4242424242424242");
                    alert("Copied test card number: 4242 4242 4242 4242");
                  }}
                >
                  Copy
                </button>
              </div>
            </div>
          )}

        </div>
      )}

      {/* Header */}
      <div className="mb-4 text-center">
        <h2 className="mb-1">{s.title}</h2>
        <div className="text-muted">
          Search historical S&amp;P 500 performance by date range.
        </div>

        {meta?.min_date && meta?.max_date && (
          <div className="text-muted small mt-1">
            Data: <strong>{meta.min_date}</strong> →{" "}
            <strong>{meta.max_date}</strong> • {meta.tickers} tickers •{" "}
            {Number(meta.rows).toLocaleString()} rows
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <form onSubmit={handleSubmit} className="row g-3 align-items-end">
            <div className="col-12 col-md-3">
              <label className="form-label">Start</label>
              <DatePicker
                className="form-control"
                selected={s.startDate}
                onChange={(d) => s.setStartDate(d)}
                dateFormat="yyyy-MM-dd"
              />
            </div>

            <div className="col-12 col-md-3">
              <label className="form-label">End</label>
              <DatePicker
                className="form-control"
                selected={s.endDate}
                onChange={(d) => s.setEndDate(d)}
                dateFormat="yyyy-MM-dd"
              />
            </div>

            <div className="col-12 col-md-3">
              <label className="form-label">Mode</label>
              <select
                className="form-select"
                value={s.mode}
                onChange={(e) => s.setMode(e.target.value)}
              >
                <option value="">Select…</option>
                <option value="stock">Single ticker</option>
                <option value="top">Top performers</option>
                <option value="bottom">Worst performers</option>
              </select>
            </div>

            {s.showTicker && (
              <div className="col-12 col-md-3">
                <label className="form-label">Ticker</label>
                <input
                  className="form-control"
                  placeholder="AAPL"
                  value={s.ticker}
                  onChange={(e) => s.setTicker(e.target.value.toUpperCase())}
                />
              </div>
            )}

            {s.showQuantity && (
              <div className="col-12 col-md-3">
                <label className="form-label">Count</label>
                <input
                  className="form-control"
                  type="number"
                  min={1}
                  max={200}
                  value={s.quantity}
                  onChange={(e) => s.setQuantity(Number(e.target.value))}
                />
              </div>
            )}

            {/* Presets restored */}
            <div className="col-12 col-md-3">
              <ButtonDropdown
                isOpen={s.dropdownOpen}
                toggle={s.togglePresetDropdown}
              >
                <DropdownToggle caret className="btn btn-outline-secondary w-100">
                  Presets
                </DropdownToggle>
                <DropdownMenu>
                  <DropdownItem onClick={() => s.setPreset("1W")}>Last week</DropdownItem>
                  <DropdownItem onClick={() => s.setPreset("1M")}>Last month</DropdownItem>
                  <DropdownItem onClick={() => s.setPreset("3M")}>Last 3 months</DropdownItem>
                  <DropdownItem onClick={() => s.setPreset("6M")}>Last 6 months</DropdownItem>
                  <DropdownItem onClick={() => s.setPreset("YTD")}>Year to date</DropdownItem>
                  <DropdownItem onClick={() => s.setPreset("1Y")}>Last year</DropdownItem>
                </DropdownMenu>
              </ButtonDropdown>

              {s.activePreset && (
                <div className="text-muted small mt-1">Preset: {s.activePreset}</div>
              )}
            </div>

            <div className="col-12 col-md-3 d-grid">
              <button className="btn btn-primary" type="submit" disabled={s.loading}>
                {s.loading ? "Searching..." : "Search"}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Results */}
      <div className="card shadow-sm">
        <div className="card-body p-0">
          <ResultsTable
            loading={s.loading}
            error={s.error}
            rows={sortedRows}
            sortKey={sortKey}
            sortDir={sortDir}
            onSort={handleHeaderSort}
            onRowClick={openDetail}
          />
        </div>
      </div>

      {/* Detail modal (props restored to match your modal component) */}
      <StockDetailModal
        isOpen={detailOpen}
        toggle={closeDetail}
        row={detailRow}
        startDate={s.startDate}
        endDate={s.endDate}
        loading={detailLoading}
        error={detailError}
        details={detailData}
      />
    </div>
  );
}

export default SearchStock;