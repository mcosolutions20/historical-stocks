// frontend/src/components/stockPickItem.jsx
import React from "react";
import { fmtPercentFromFraction, fmtNumber, numOrNull, signClass } from "../utils/format";

function StockPickItem({ id, ticker, stddev, ret, onClick }) {
  const r = numOrNull(ret);
  const s = numOrNull(stddev);

  const returnCls = signClass(r);

  return (
    <tr
      style={{ cursor: onClick ? "pointer" : "default" }}
      onClick={() => onClick?.({ ticker, return: ret, stddev })}
      title={onClick ? "Click for details" : undefined}
    >
      <th scope="row">{id}</th>
      <td className="fw-semibold">{ticker}</td>
      <td className="text-end">{fmtNumber(s, 4)}</td>
      <td className={`text-end fw-semibold ${returnCls}`}>{fmtPercentFromFraction(r, 2)}</td>
    </tr>
  );
}

export default StockPickItem;
