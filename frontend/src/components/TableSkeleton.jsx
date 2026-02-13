// frontend/src/components/TableSkeleton.jsx
import React from "react";
import TableHead from "./tableHead";

export default function TableSkeleton({ sortKey, sortDir, onSort, rows = 8 }) {
  return (
    <div className="table-responsive placeholder-glow">
      <div className="text-muted small mb-2">Loading…</div>
      <table className="table table-striped align-middle">
        <TableHead sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i}>
              <td style={{ width: 60 }}>
                <span className="placeholder col-8" />
              </td>
              <td>
                <span className="placeholder col-6" />
              </td>
              <td className="text-end">
                <span className="placeholder col-4" />
              </td>
              <td className="text-end">
                <span className="placeholder col-4" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}