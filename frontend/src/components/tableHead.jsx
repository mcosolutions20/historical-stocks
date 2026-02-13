// frontend/src/components/tableHead.jsx
function TableHead({ sortKey, sortDir, onSort }) {
  const arrow = (key) => {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  };

  const headerBtn = {
    cursor: "pointer",
    userSelect: "none",
    whiteSpace: "nowrap",
  };

  return (
    <thead>
      <tr>
        <th style={{ width: 60 }}>#</th>
        <th scope="col">TICKER</th>

        <th
          scope="col"
          className="text-end"
          style={headerBtn}
          onClick={() => onSort("stddev")}
          title="Sort by standard deviation"
        >
          Daily volatility (std dev){arrow("stddev")}
        </th>

        <th
          scope="col"
          className="text-end"
          style={headerBtn}
          onClick={() => onSort("return")}
          title="Sort by return"
        >
          RETURN{arrow("return")}
        </th>
      </tr>
    </thead>
  );
}

export default TableHead;
