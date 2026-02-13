// frontend/src/hooks/useSorting.js
import { useEffect, useMemo, useState } from "react";

export default function useSorting({ rows, mode }) {
  const [sortKey, setSortKey] = useState("return");
  const [sortDir, setSortDir] = useState("desc");
  const [userTouchedSort, setUserTouchedSort] = useState(false);

  // Default sort by mode (unless user manually sorted)
  useEffect(() => {
    if (userTouchedSort) return;

    if (mode === "bottom") {
      setSortKey("return");
      setSortDir("asc");
    } else if (mode === "top" || mode === "stock") {
      setSortKey("return");
      setSortDir("desc");
    }
  }, [mode, userTouchedSort]);

  const sortedRows = useMemo(() => {
    const copy = [...(rows || [])];

    const getVal = (r) => {
      const v = sortKey === "stddev" ? r?.stddev : r?.return;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    };

    copy.sort((a, b) => {
      const av = getVal(a);
      const bv = getVal(b);

      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;

      const diff = av - bv;
      return sortDir === "asc" ? diff : -diff;
    });

    return copy;
  }, [rows, sortKey, sortDir]);

  function handleHeaderSort(key) {
    setUserTouchedSort(true);

    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
      return;
    }

    setSortKey(key);
  }

  return {
    sortKey,
    sortDir,
    sortedRows,
    setSortKey,
    setSortDir,
    handleHeaderSort,
  };
}
