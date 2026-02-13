// frontend/src/hooks/useSearchState.js
import { useMemo, useState } from "react";
import {
  fetchOutliers,
  fetchStock,
  fetchOutliersSecure,
  fetchStockSecure,
  isAuthed,
} from "../api";
import { presetToRange } from "../utils/dateRange";
import { fmtDate } from "../utils/format";
import { downloadCsv } from "../utils/csv";
import { saveSetup, loadSetup, clearSetup } from "../utils/storage";

const MODES = {
  STOCK: "stock",
  TOP: "top",
  BOTTOM: "bottom",
  INITIAL: "",
};

export default function useSearchState({ dbMinDate, dbMaxDate, storageKey }) {
  // --- date range ---
  const [startDate, setStartDate] = useState(new Date("2025-01-02"));
  const [endDate, setEndDate] = useState(new Date("2025-01-11"));

  // --- query inputs ---
  const [mode, setMode] = useState(MODES.INITIAL);
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState(10);

  // --- results + request status ---
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // --- usage status (from secure endpoints) ---
  const [usage, setUsage] = useState(null);
  const [needsUpgrade, setNeedsUpgrade] = useState(false);

  // --- ui controls ---
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [activePreset, setActivePreset] = useState(null);

  // --- save/load status msg ---
  const [statusMsg, setStatusMsg] = useState("");

  const hasMode = mode !== MODES.INITIAL;
  const showTicker = mode === MODES.STOCK;
  const showQuantity = mode === MODES.TOP || mode === MODES.BOTTOM;

  const title = useMemo(() => {
    if (mode === MODES.STOCK) return "Single Stock";
    if (mode === MODES.TOP) return "Top Performing Stocks";
    if (mode === MODES.BOTTOM) return "Worst Performing Stocks";
    return "Historical Stocks";
  }, [mode]);

  const modeBadge = useMemo(() => {
    if (mode === MODES.STOCK) return { text: "Single", cls: "bg-secondary" };
    if (mode === MODES.TOP) return { text: "Top", cls: "bg-success" };
    if (mode === MODES.BOTTOM) return { text: "Bottom", cls: "bg-danger" };
    return null;
  }, [mode]);

  function togglePresetDropdown() {
    setDropdownOpen((v) => !v);
  }

  function setPreset(preset) {
    const r = presetToRange(preset, dbMinDate, dbMaxDate);
    if (!r) return;
    setStartDate(r.start);
    setEndDate(r.end);
    setActivePreset(preset);
  }

  async function submitSearch() {
    setError("");
    setRows([]);
    setNeedsUpgrade(false);

    if (!hasMode) {
      setError("Choose an action to begin.");
      return;
    }

    if (startDate > endDate) {
      setError("Start date must be before end date.");
      return;
    }

    if (showTicker && !ticker.trim()) {
      setError("Enter a stock ticker (ex: AAPL).");
      return;
    }

    setLoading(true);
    try {
      const authed = isAuthed();

      if (mode === MODES.STOCK) {
        if (authed) {
          const res = await fetchStockSecure({ startDate, endDate, ticker });
          setUsage(res.usage || null);
          setRows(res.data || []);
        } else {
          const data = await fetchStock({ startDate, endDate, ticker });
          setRows(data || []);
        }
      } else {
        if (authed) {
          const res = await fetchOutliersSecure({
            startDate,
            endDate,
            performance: mode,
            quantity,
          });
          setUsage(res.usage || null);
          setRows(res.data || []);
        } else {
          const data = await fetchOutliers({
            startDate,
            endDate,
            performance: mode,
            quantity,
          });
          setRows(data || []);
        }
      }

      if (!rows || rows.length === 0) {
        // if backend gave no rows
        // (we'll rely on updated state below; keep this minimal)
      }
    } catch (err) {
      // Upgrade gating: backend uses 402 when limit reached
      const status = err?.response?.status;
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message ||
        "Request failed.";

      if (status === 402) {
        setNeedsUpgrade(true);
      }

      setError(String(msg));
    } finally {
      setLoading(false);
    }
  }

  function exportCsv(sortedRows) {
    if (!sortedRows?.length) return;

    const start = fmtDate(startDate);
    const end = fmtDate(endDate);
    const modeLabel = mode || "results";
    const filename = `${modeLabel}_${start}_to_${end}.csv`;

    const header = ["rank", "ticker", "stddev", "return"];
    const dataRows = sortedRows.map((s, i) => [i + 1, s.ticker, s.stddev, s.return]);

    downloadCsv({ filename, header, rows: dataRows });
  }

  function buildSetupPayload(extra) {
    return {
      startDate: startDate?.toISOString(),
      endDate: endDate?.toISOString(),
      mode,
      ticker,
      quantity,
      activePreset,
      ...(extra || {}),
    };
  }

  function saveCurrentSetup(extra) {
    saveSetup(storageKey, buildSetupPayload(extra));
    setStatusMsg("Setup saved.");
    setTimeout(() => setStatusMsg(""), 1500);
  }

  function loadSavedSetup(setters) {
    const saved = loadSetup(storageKey);
    if (!saved) {
      setStatusMsg("No saved setup found.");
      setTimeout(() => setStatusMsg(""), 1500);
      return;
    }

    if (saved.startDate) setStartDate(new Date(saved.startDate));
    if (saved.endDate) setEndDate(new Date(saved.endDate));
    if (saved.mode) setMode(saved.mode);
    if (typeof saved.ticker === "string") setTicker(saved.ticker);
    if (saved.quantity != null) setQuantity(saved.quantity);
    if (saved.activePreset !== undefined) setActivePreset(saved.activePreset);

    if (setters?.setSortKey && saved.sortKey) setters.setSortKey(saved.sortKey);
    if (setters?.setSortDir && saved.sortDir) setters.setSortDir(saved.sortDir);

    setStatusMsg("Setup loaded.");
    setTimeout(() => setStatusMsg(""), 1500);
  }

  function resetAll() {
    clearSetup(storageKey);

    setMode(MODES.INITIAL);
    setTicker("");
    setQuantity(10);

    setRows([]);
    setError("");
    setActivePreset(null);
    setStatusMsg("");
    setUsage(null);
    setNeedsUpgrade(false);
  }

  return {
    MODES,
    hasMode,
    showTicker,
    showQuantity,

    title,
    modeBadge,

    startDate,
    endDate,
    mode,
    ticker,
    quantity,
    rows,
    loading,
    error,
    dropdownOpen,
    activePreset,
    statusMsg,

    usage,
    needsUpgrade,

    setStartDate,
    setEndDate,
    setMode,
    setTicker,
    setQuantity,
    setError,
    setRows,

    togglePresetDropdown,
    setPreset,
    submitSearch,
    exportCsv,
    saveCurrentSetup,
    loadSavedSetup,
    resetAll,
  };
}
