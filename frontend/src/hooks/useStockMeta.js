// frontend/src/hooks/useStockMeta.js
import { useEffect, useMemo, useState } from "react";
import { fetchMeta } from "../api";

export default function useStockMeta() {
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const m = await fetchMeta();
        setMeta(m);
      } catch {
        // meta is optional UI
      }
    })();
  }, []);

  const dbMinDate = useMemo(() => (meta?.min_date ? new Date(meta.min_date) : null), [meta]);
  const dbMaxDate = useMemo(() => (meta?.max_date ? new Date(meta.max_date) : null), [meta]);

  return { meta, dbMinDate, dbMaxDate };
}