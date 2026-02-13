import React, { useEffect, useState } from "react";

export default function HoldingEditModal({ isOpen, holding, onClose, onSave, loading }) {
  const [shares, setShares] = useState("");
  const [avgCost, setAvgCost] = useState("");

  useEffect(() => {
    if (!holding) return;
    setShares(String(holding.shares ?? ""));
    setAvgCost(holding.avg_cost === null || holding.avg_cost === undefined ? "" : String(holding.avg_cost));
  }, [holding]);

  if (!isOpen || !holding) return null;

  function submit() {
    const s = Number(shares);
    if (!Number.isFinite(s) || s <= 0) return;

    const ac = avgCost.trim() === "" ? null : Number(avgCost);
    if (ac !== null && (!Number.isFinite(ac) || ac < 0)) return;

    onSave({ shares: s, avg_cost: ac });
  }

  return (
    <>
      <div className="modal fade show" style={{ display: "block" }} tabIndex="-1" role="dialog">
        <div className="modal-dialog" role="document">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">Edit Holding — {holding.ticker}</h5>
              <button type="button" className="btn-close" aria-label="Close" onClick={onClose} />
            </div>

            <div className="modal-body">
              <div className="mb-2">
                <label className="form-label">Shares</label>
                <input
                  className="form-control"
                  value={shares}
                  onChange={(e) => setShares(e.target.value)}
                  placeholder="e.g. 10"
                />
              </div>

              <div className="mb-2">
                <label className="form-label">Avg Cost (optional)</label>
                <input
                  className="form-control"
                  value={avgCost}
                  onChange={(e) => setAvgCost(e.target.value)}
                  placeholder="e.g. 180.25"
                />
                <div className="form-text">Leave blank to store null.</div>
              </div>
            </div>

            <div className="modal-footer">
              <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={loading}>
                Cancel
              </button>
              <button type="button" className="btn btn-primary" onClick={submit} disabled={loading}>
                Save
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* backdrop */}
      <div className="modal-backdrop fade show" />
    </>
  );
}
