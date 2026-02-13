// frontend/src/components/ResultsTable.jsx
import React from "react";
import TableHead from "./tableHead";
import StockPickItem from "./stockPickItem";
import TableSkeleton from "./TableSkeleton";

export default function ResultsTable({
  loading,
  error,
  rows,
  sortKey,
  sortDir,
  onSort,
  onRowClick,
}) {
  if (loading) {
    return <TableSkeleton />;
  }

  if (error) {
    return (
      <div className="alert alert-warning mb-0" role="alert">
        {error}
      </div>
    );
  }

  if (!rows || rows.length === 0) {
    return (
      <div className="text-muted text-center py-4">
        No results yet. Pick a mode, choose dates, and run a search.
      </div>
    );
  }

  return (
    <div className="table-responsive">
      <table className="table table-hover align-middle mb-0">
        <TableHead sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <tbody>
          {rows.map((r, i) => (
            <StockPickItem
              key={`${r.ticker}-${i}`}
              id={i + 1}
              ticker={r.ticker}
              stddev={r.stddev}
              ret={r.return}
              onClick={onRowClick}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
