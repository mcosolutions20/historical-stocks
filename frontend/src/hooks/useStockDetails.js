// frontend/src/hooks/useStockDetails.js
import { useEffect, useState } from "react";
import { fetchStock } from "../api";

export default function useStockDetails({ startDate, endDate }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRow, setDetailRow] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailData, setDetailData] = useState(null);

  function openDetail(row) {
    setDetailRow(row);
    setDetailData(null);
    setDetailError("");
    setDetailOpen(true);
  }

  function closeDetail() {
    setDetailOpen(false);
  }

  useEffect(() => {
    async function load() {
      if (!detailOpen || !detailRow?.ticker) return;

      setDetailLoading(true);
      setDetailError("");

      try {
        const data = await fetchStock({
          startDate,
          endDate,
          ticker: detailRow.ticker,
        });
        setDetailData(data);
      } catch (err) {
        const msg =
          err?.response?.data?.detail ||
          err?.response?.data?.message ||
          err?.message ||
          "Failed to load ticker details.";
        setDetailError(String(msg));
      } finally {
        setDetailLoading(false);
      }
    }

    load();
  }, [detailOpen, detailRow, startDate, endDate]);

  return {
    detailOpen,
    detailRow,
    detailLoading,
    detailError,
    detailData,
    openDetail,
    closeDetail,
  };
}