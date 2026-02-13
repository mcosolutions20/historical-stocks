# backend/app/portfolios.py
from __future__ import annotations

from datetime import date
from typing import Dict, Any, List, Optional, Tuple

from fastapi import HTTPException
from .db import get_conn


def _norm_ticker(t: str) -> str:
    t = (t or "").strip().upper()
    if not t:
        raise HTTPException(status_code=400, detail="ticker is required")
    if len(t) > 12:
        raise HTTPException(status_code=400, detail="ticker too long")
    return t


def _lookup_price(ticker: str, trade_date: date) -> float:
    """
    Uses adj_close from your DB.
    If exact date isn't a trading day, uses the last available prior trading day.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date, adj_close
                FROM sp500_historical
                WHERE ticker = %s
                  AND trade_date <= %s
                  AND adj_close IS NOT NULL
                ORDER BY trade_date DESC
                LIMIT 1;
                """,
                (ticker, trade_date),
            )
            row = cur.fetchone()

    if not row or row[1] is None:
        raise HTTPException(status_code=400, detail=f"No price found for {ticker} on/before {trade_date.isoformat()}")
    return float(row[1])


def init_portfolio_tables() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolios (
                  id BIGSERIAL PRIMARY KEY,
                  user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  cash_balance DOUBLE PRECISION NOT NULL DEFAULT 0,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  UNIQUE(user_id, name)
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                  id BIGSERIAL PRIMARY KEY,
                  portfolio_id BIGINT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                  ticker TEXT NOT NULL,
                  side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
                  shares DOUBLE PRECISION NOT NULL CHECK (shares > 0),
                  price DOUBLE PRECISION NOT NULL CHECK (price > 0),
                  trade_date DATE NOT NULL,
                  notes TEXT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_portfolio ON transactions(portfolio_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_portfolio_date ON transactions(portfolio_id, trade_date);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_portfolio_ticker ON transactions(portfolio_id, ticker);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sp500_index_daily (
                  trade_date DATE PRIMARY KEY,
                  index_value DOUBLE PRECISION NOT NULL
                );
                """
            )
        conn.commit()


# =========================
# CRUD: Portfolios
# =========================
def list_portfolios(user_id: int) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, cash_balance, created_at, updated_at
                FROM portfolios
                WHERE user_id = %s
                ORDER BY updated_at DESC;
                """,
                (user_id,),
            )
            rows = cur.fetchall()

    return [
        {"id": int(r[0]), "name": r[1], "cash_balance": float(r[2] or 0), "created_at": r[3], "updated_at": r[4]}
        for r in rows
    ]


def create_portfolio(user_id: int, name: str, cash_balance: float = 0) -> Dict[str, Any]:
    name = (name or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="portfolio name must be at least 2 characters")
    cash_balance = float(cash_balance or 0)
    if cash_balance < 0:
        raise HTTPException(status_code=400, detail="cash_balance cannot be negative")

    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO portfolios (user_id, name, cash_balance)
                    VALUES (%s, %s, %s)
                    RETURNING id, name, cash_balance, created_at, updated_at;
                    """,
                    (user_id, name, cash_balance),
                )
                row = cur.fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise HTTPException(status_code=400, detail="portfolio name already exists")

    return {"id": int(row[0]), "name": row[1], "cash_balance": float(row[2] or 0), "created_at": row[3], "updated_at": row[4]}


def update_portfolio(user_id: int, portfolio_id: int, name: Optional[str], cash_balance: Optional[float]) -> Dict[str, Any]:
    sets = []
    params = []

    if name is not None:
        name = name.strip()
        if len(name) < 2:
            raise HTTPException(status_code=400, detail="portfolio name must be at least 2 characters")
        sets.append("name = %s")
        params.append(name)

    if cash_balance is not None:
        cash_balance = float(cash_balance)
        if cash_balance < 0:
            raise HTTPException(status_code=400, detail="cash_balance cannot be negative")
        sets.append("cash_balance = %s")
        params.append(cash_balance)

    if not sets:
        raise HTTPException(status_code=400, detail="no fields provided to update")

    sets.append("updated_at = NOW()")
    params.extend([portfolio_id, user_id])

    sql = f"""
        UPDATE portfolios
        SET {", ".join(sets)}
        WHERE id = %s AND user_id = %s
        RETURNING id, name, cash_balance, created_at, updated_at;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, tuple(params))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="portfolio not found")
                conn.commit()
            except HTTPException:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise HTTPException(status_code=400, detail="portfolio name already exists")

    # Invalidate cached performance when cash_balance changes OR if name changes (safe + simple)
    from .cache import bump_portfolio_version
    bump_portfolio_version(int(portfolio_id))

    return {"id": int(row[0]), "name": row[1], "cash_balance": float(row[2] or 0), "created_at": row[3], "updated_at": row[4]}


def delete_portfolio(user_id: int, portfolio_id: int) -> Dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM portfolios WHERE id=%s AND user_id=%s RETURNING id;", (portfolio_id, user_id))
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(status_code=404, detail="portfolio not found")

    return {"deleted": True}


# =========================
# Transactions helpers
# =========================
def _fetch_transactions(user_id: int, portfolio_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, cash_balance
                FROM portfolios
                WHERE id=%s AND user_id=%s
                LIMIT 1;
                """,
                (portfolio_id, user_id),
            )
            p = cur.fetchone()
            if not p:
                raise HTTPException(status_code=404, detail="portfolio not found")

            cur.execute(
                """
                SELECT id, ticker, side, shares, price, trade_date, notes, created_at, updated_at
                FROM transactions
                WHERE portfolio_id = %s
                ORDER BY trade_date ASC, id ASC;
                """,
                (portfolio_id,),
            )
            rows = cur.fetchall()

    portfolio = {"id": int(p[0]), "name": p[1], "cash_balance": float(p[2] or 0)}
    txs = []
    for r in rows:
        txs.append(
            {
                "id": int(r[0]),
                "ticker": r[1],
                "side": r[2],
                "shares": float(r[3]),
                "price": float(r[4]),
                "trade_date": r[5].isoformat(),
                "notes": r[6],
                "created_at": r[7],
                "updated_at": r[8],
            }
        )
    return portfolio, txs


def _compute_positions_from_transactions(txs: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    pos: Dict[str, Dict[str, float]] = {}

    for tx in txs:
        t = _norm_ticker(tx["ticker"])
        side = tx["side"]
        sh = float(tx["shares"])
        px = float(tx["price"])

        if t not in pos:
            pos[t] = {"shares": 0.0, "cost_basis": 0.0, "avg_cost": 0.0}

        cur_sh = pos[t]["shares"]
        cur_cost = pos[t]["cost_basis"]
        cur_avg = (cur_cost / cur_sh) if cur_sh > 0 else 0.0

        if side == "BUY":
            cur_sh += sh
            cur_cost += sh * px
        elif side == "SELL":
            if sh > cur_sh + 1e-9:
                raise HTTPException(status_code=400, detail=f"SELL exceeds shares for {t}")
            cur_sh -= sh
            cur_cost -= sh * cur_avg
            if cur_sh < 1e-9:
                cur_sh = 0.0
                cur_cost = 0.0
        else:
            raise HTTPException(status_code=400, detail="side must be BUY or SELL")

        pos[t]["shares"] = cur_sh
        pos[t]["cost_basis"] = cur_cost
        pos[t]["avg_cost"] = (cur_cost / cur_sh) if cur_sh > 0 else 0.0

    return {t: v for (t, v) in pos.items() if v["shares"] > 0}


def _compute_cash_current(starting_cash: float, txs: List[Dict[str, Any]]) -> float:
    cash = float(starting_cash or 0)
    for tx in txs:
        sh = float(tx["shares"])
        px = float(tx["price"])
        if tx["side"] == "BUY":
            cash -= sh * px
        else:
            cash += sh * px
    return cash


def list_transactions(user_id: int, portfolio_id: int) -> Dict[str, Any]:
    portfolio, txs = _fetch_transactions(user_id, portfolio_id)
    return {"portfolio": portfolio, "transactions": txs}


def create_transaction(
    user_id: int,
    portfolio_id: int,
    ticker: str,
    side: str,
    shares: float,
    price: Optional[float],
    trade_date: date,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    ticker = _norm_ticker(ticker)
    side = (side or "").strip().upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")

    shares = float(shares)
    if shares <= 0:
        raise HTTPException(status_code=400, detail="shares must be > 0")

    if price is None:
        price = _lookup_price(ticker, trade_date)
    price = float(price)
    if price <= 0:
        raise HTTPException(status_code=400, detail="price must be > 0")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM portfolios WHERE id=%s AND user_id=%s;", (portfolio_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="portfolio not found")

            cur.execute(
                """
                INSERT INTO transactions (portfolio_id, ticker, side, shares, price, trade_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, ticker, side, shares, price, trade_date, notes, created_at, updated_at;
                """,
                (portfolio_id, ticker, side, shares, price, trade_date, notes),
            )
            row = cur.fetchone()
        conn.commit()

    _validate_transactions_non_negative(user_id, portfolio_id)

    # Invalidate cached performance
    from .cache import bump_portfolio_version
    bump_portfolio_version(int(portfolio_id))

    return {
        "id": int(row[0]),
        "ticker": row[1],
        "side": row[2],
        "shares": float(row[3]),
        "price": float(row[4]),
        "trade_date": row[5].isoformat(),
        "notes": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }

def update_transaction(
    user_id: int,
    transaction_id: int,
    side: str,
    shares: float,
    price: Optional[float],
    trade_date: date,
    notes: Optional[str],
) -> Dict[str, Any]:
    side = (side or "").strip().upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")

    shares = float(shares)
    if shares <= 0:
        raise HTTPException(status_code=400, detail="shares must be > 0")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.ticker, t.portfolio_id
                FROM transactions t
                JOIN portfolios p ON p.id = t.portfolio_id
                WHERE t.id=%s AND p.user_id=%s
                LIMIT 1;
                """,
                (transaction_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="transaction not found")
            ticker = row[0]
            portfolio_id = int(row[1])

    if price is None:
        price = _lookup_price(ticker, trade_date)
    price = float(price)
    if price <= 0:
        raise HTTPException(status_code=400, detail="price must be > 0")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE transactions
                SET side=%s, shares=%s, price=%s, trade_date=%s, notes=%s, updated_at=NOW()
                WHERE id=%s
                RETURNING id, ticker, side, shares, price, trade_date, notes, created_at, updated_at;
                """,
                (side, shares, price, trade_date, notes, transaction_id),
            )
            updated = cur.fetchone()
        conn.commit()

    _validate_transactions_non_negative(user_id, portfolio_id)

    # Invalidate cached performance
    from .cache import bump_portfolio_version
    bump_portfolio_version(int(portfolio_id))

    return {
        "id": int(updated[0]),
        "ticker": updated[1],
        "side": updated[2],
        "shares": float(updated[3]),
        "price": float(updated[4]),
        "trade_date": updated[5].isoformat(),
        "notes": updated[6],
        "created_at": updated[7],
        "updated_at": updated[8],
    }

def delete_transaction(user_id: int, transaction_id: int) -> Dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM transactions t
                USING portfolios p
                WHERE t.portfolio_id = p.id
                  AND t.id=%s
                  AND p.user_id=%s
                RETURNING t.id, p.id;
                """,
                (transaction_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="transaction not found")
        conn.commit()

    portfolio_id = int(row[1])
    _validate_transactions_non_negative(user_id, portfolio_id)

    # Invalidate cached performance
    from .cache import bump_portfolio_version
    bump_portfolio_version(int(portfolio_id))

    return {"deleted": True}

# =========================
# CSV Export / Import (transactions)
# =========================
def export_transactions_csv(user_id: int, portfolio_id: int) -> Dict[str, Any]:
    """
    Returns: {"filename": "...", "csv": "..."}
    Frontend can download as a file.
    """
    portfolio, txs = _fetch_transactions(user_id, portfolio_id)

    import io, csv as _csv
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["ticker", "side", "shares", "price", "trade_date", "notes"])
    for tx in txs:
        w.writerow(
            [
                tx["ticker"],
                tx["side"],
                tx["shares"],
                tx["price"],
                tx["trade_date"],
                tx.get("notes") or "",
            ]
        )

    filename = f"portfolio_{portfolio_id}_transactions.csv"
    return {"filename": filename, "csv": buf.getvalue()}


def import_transactions_csv(user_id: int, portfolio_id: int, csv_text: str) -> Dict[str, Any]:
    """
    CSV headers (case-insensitive):
      - ticker (required)
      - side (BUY/SELL) (required)
      - shares (required)
      - price (optional; if blank -> auto-fill from DB close on/before trade_date)
      - trade_date (required; YYYY-MM-DD)
      - notes (optional)

    Inserts rows in a single DB transaction.
    """
    import io, csv as _csv

    if not csv_text or not csv_text.strip():
        raise HTTPException(status_code=400, detail="empty CSV")

    # ownership check
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM portfolios WHERE id=%s AND user_id=%s;", (portfolio_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="portfolio not found")

    def _canon_header(h: str) -> str:
        h = (h or "").strip().lower()
        # normalize common separators
        for ch in (" ", "-", "."):
            h = h.replace(ch, "_")
        while "__" in h:
            h = h.replace("__", "_")
        return h

    # common brokerage / app export aliases
    aliases = {
        "ticker": {"ticker", "symbol", "security", "instrument", "underlying", "asset"},
        "side": {"side", "action", "type", "transaction_type", "buy_sell", "order_side"},
        "shares": {"shares", "qty", "quantity", "units", "shares_quantity"},
        "price": {"price", "fill_price", "avg_price", "execution_price", "trade_price"},
        "trade_date": {"trade_date", "date", "trade_date_utc", "filled_at", "execution_date"},
        "notes": {"notes", "note", "description", "memo"},
    }

    buf = io.StringIO(csv_text)
    reader = _csv.DictReader(buf)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV missing headers")

    # build canonical header map
    canon_to_raw = {_canon_header(h): h for h in reader.fieldnames if h}

    def _find_col(key: str) -> Optional[str]:
        for a in aliases[key]:
            if a in canon_to_raw:
                return canon_to_raw[a]
        return None

    col_ticker = _find_col("ticker")
    col_side = _find_col("side")
    col_shares = _find_col("shares")
    col_price = _find_col("price")
    col_date = _find_col("trade_date")
    col_notes = _find_col("notes")

    missing = []
    if not col_ticker:
        missing.append("ticker")
    if not col_shares:
        missing.append("shares")
    if not col_date:
        missing.append("trade_date")

    # side is sometimes inferable from negative qty; still prefer explicit
    if not col_side:
        # allow missing side if qty is signed
        pass

    if missing:
        raise HTTPException(status_code=400, detail=f"CSV missing required column(s): {', '.join(missing)}")

    rows_to_insert = []
    errors = []
    inserted = 0

    def _parse_date(s: str) -> date:
        s = (s or "").strip()
        if not s:
            raise ValueError("trade_date is required")
        # try ISO first
        try:
            return date.fromisoformat(s[:10])
        except Exception:
            pass
        # try MM/DD/YYYY
        try:
            mm, dd, yyyy = s.split("/")
            return date(int(yyyy), int(mm), int(dd))
        except Exception:
            raise ValueError("trade_date must be YYYY-MM-DD or MM/DD/YYYY")

    def _parse_side(raw_side: str, shares_val: float) -> str:
        s = (raw_side or "").strip().upper()
        if s in ("BUY", "B"):
            return "BUY"
        if s in ("SELL", "S"):
            return "SELL"
        if "BUY" in s:
            return "BUY"
        if "SELL" in s:
            return "SELL"
        if s in ("PURCHASE", "OPEN"):
            return "BUY"
        if s in ("CLOSE", "REDEMPTION"):
            return "SELL"
        # infer from sign
        if shares_val < 0:
            return "SELL"
        if shares_val > 0:
            return "BUY" if s == "" else "BUY"
        raise ValueError("side must be BUY or SELL")

    for idx, row in enumerate(reader, start=2):  # header line is 1
        try:
            ticker = _norm_ticker((row.get(col_ticker, "") or ""))

            shares_raw = (row.get(col_shares, "") or "").strip().replace(",", "")
            if shares_raw == "":
                raise ValueError("shares is required")
            shares_signed = float(shares_raw)
            if shares_signed == 0:
                raise ValueError("shares must be non-zero")

            td_raw = (row.get(col_date, "") or "")
            td = _parse_date(td_raw)

            raw_side = (row.get(col_side, "") if col_side else "") or ""
            side = _parse_side(raw_side, shares_signed)
            shares = abs(shares_signed)

            price = None
            if col_price:
                pr_raw = (row.get(col_price, "") or "").strip().replace(",", "")
                if pr_raw != "":
                    price = float(pr_raw)
                    if price <= 0:
                        raise ValueError("price must be > 0")

            notes = (row.get(col_notes, "") if col_notes else "") or None
            if notes is not None:
                notes = str(notes).strip()
                if notes == "":
                    notes = None

            if price is None:
                price = _lookup_price(ticker, td)

            rows_to_insert.append((portfolio_id, ticker, side, shares, price, td, notes))
        except Exception as e:
            errors.append({"line": idx, "error": str(e)})
            if len(errors) >= 25:
                break

    if errors:
        raise HTTPException(status_code=400, detail={"message": "CSV validation failed", "errors": errors})

    with get_conn() as conn:
        with conn.cursor() as cur:
            for rec in rows_to_insert:
                cur.execute(
                    """
                    INSERT INTO transactions (portfolio_id, ticker, side, shares, price, trade_date, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """,
                    rec,
                )
                inserted += 1
        conn.commit()

    _validate_transactions_non_negative(user_id, portfolio_id)

    return {"imported": inserted}


def _validate_transactions_non_negative(user_id: int, portfolio_id: int) -> None:
    _, txs = _fetch_transactions(user_id, portfolio_id)
    _compute_positions_from_transactions(txs)


# =========================
# Portfolio detail / valuation / performance / rebalance
# (unchanged from your previous transactions version)
# =========================
# NOTE: Keep the rest of your file the same as the transactions version you already have
# (get_portfolio_detail, get_portfolio_valuation, get_portfolio_performance, rebalance_suggestion, etc.)



def get_portfolio_detail(user_id: int, portfolio_id: int) -> Dict[str, Any]:
    portfolio, txs = _fetch_transactions(user_id, portfolio_id)
    positions = _compute_positions_from_transactions(txs)

    holdings = []
    for ticker in sorted(positions.keys()):
        holdings.append(
            {
                "ticker": ticker,
                "shares": positions[ticker]["shares"],
                "avg_cost": positions[ticker]["avg_cost"],
            }
        )

    return {
        "portfolio": portfolio,
        "holdings": holdings,          # derived
        "transactions": txs,           # raw ledger
    }


# =========================
# Valuation + Allocation + Unrealized P/L (from transactions)
# =========================
def get_portfolio_valuation(user_id: int, portfolio_id: int) -> Dict[str, Any]:
    portfolio, txs = _fetch_transactions(user_id, portfolio_id)
    positions = _compute_positions_from_transactions(txs)

    cash_current = _compute_cash_current(portfolio["cash_balance"], txs)

    tickers = list(positions.keys())
    latest_price: Dict[str, Tuple[Optional[date], Optional[float]]] = {t: (None, None) for t in tickers}

    if tickers:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # latest price per ticker from sp500_historical
                cur.execute(
                    """
                    WITH tickers AS (
                      SELECT UNNEST(%s::text[]) AS ticker
                    ),
                    latest AS (
                      SELECT DISTINCT ON (s.ticker)
                        s.ticker, s.trade_date, s.adj_close
                      FROM sp500_historical s
                      JOIN tickers t ON t.ticker = s.ticker
                      WHERE s.adj_close IS NOT NULL
                      ORDER BY s.ticker, s.trade_date DESC
                    )
                    SELECT ticker, trade_date, adj_close FROM latest;
                    """,
                    (tickers,),
                )
                for t, d, px in cur.fetchall():
                    latest_price[t] = (d, float(px) if px is not None else None)

    out_positions = []
    holdings_value = 0.0
    cost_basis_total = 0.0
    unrealized_total = 0.0

    for ticker in sorted(tickers):
        sh = float(positions[ticker]["shares"])
        ac = float(positions[ticker]["avg_cost"])
        cb = float(positions[ticker]["cost_basis"])
        cost_basis_total += cb

        d, px = latest_price.get(ticker, (None, None))
        mv = sh * px if px is not None else 0.0
        holdings_value += mv

        unreal = (mv - cb) if (px is not None) else 0.0
        unrealized_total += unreal
        unreal_pct = (unreal / cb) if cb > 0 else None

        out_positions.append(
            {
                "ticker": ticker,
                "shares": sh,
                "avg_cost": ac,
                "cost_basis": cb,
                "price_date": (d.isoformat() if d is not None else None),
                "last_price": px,
                "market_value": mv,
                "unrealized_pl": (unreal if px is not None else None),
                "unrealized_pl_pct": unreal_pct,
            }
        )

    total_value = cash_current + holdings_value
    for p in out_positions:
        p["weight"] = (p["market_value"] / total_value) if total_value > 0 else 0.0

    unrealized_pct_on_cost = (unrealized_total / cost_basis_total) if cost_basis_total > 0 else None

    return {
        "portfolio": {"id": int(portfolio_id), "name": portfolio["name"], "cash_balance": float(portfolio["cash_balance"] or 0)},
        "totals": {
            "holdings_value": holdings_value,
            "cash_current": cash_current,
            "total_value": total_value,
            "cost_basis_total": cost_basis_total if cost_basis_total > 0 else None,
            "unrealized_pl_total": unrealized_total if cost_basis_total > 0 else None,
            "unrealized_pl_pct_on_cost": unrealized_pct_on_cost,
        },
        "positions": out_positions,
    }


# =========================
# SP500 dataset-wide benchmark (equal-weight index)
# =========================
def _ensure_sp500_index_daily() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM sp500_index_daily LIMIT 1;")
            if cur.fetchone():
                conn.commit()
                return

            cur.execute(
                """
                WITH per_ticker AS (
                  SELECT
                    ticker,
                    trade_date,
                    adj_close,
                    LAG(adj_close) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close
                  FROM sp500_historical
                  WHERE adj_close IS NOT NULL
                ),
                daily_ret AS (
                  SELECT
                    trade_date,
                    AVG((adj_close / NULLIF(prev_close, 0)) - 1) AS avg_ret
                  FROM per_ticker
                  WHERE prev_close IS NOT NULL
                  GROUP BY trade_date
                ),
                ordered AS (
                  SELECT
                    trade_date,
                    avg_ret,
                    SUM(LN(1 + avg_ret)) OVER (ORDER BY trade_date) AS cum_log
                  FROM daily_ret
                  WHERE avg_ret IS NOT NULL
                )
                INSERT INTO sp500_index_daily(trade_date, index_value)
                SELECT
                  trade_date,
                  100 * EXP(cum_log) AS index_value
                FROM ordered
                ORDER BY trade_date ASC;
                """
            )
        conn.commit()


def _sp500_index_series(start: date, end: date) -> List[Tuple[date, Optional[float]]]:
    _ensure_sp500_index_daily()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH dates AS (
                  SELECT d::date AS day
                  FROM generate_series(%s::date, %s::date, interval '1 day') d
                )
                SELECT
                  dates.day,
                  idx.trade_date,
                  idx.index_value
                FROM dates
                LEFT JOIN LATERAL (
                  SELECT trade_date, index_value
                  FROM sp500_index_daily
                  WHERE trade_date <= dates.day
                  ORDER BY trade_date DESC
                  LIMIT 1
                ) idx ON TRUE
                ORDER BY dates.day ASC;
                """,
                (start, end),
            )
            rows = cur.fetchall()
    return [(r[0], (float(r[2]) if r[2] is not None else None)) for r in rows]


# =========================
# Performance (with transactions)
# =========================
def get_portfolio_performance(
    user_id: int,
    portfolio_id: int,
    start: date,
    end: date,
    benchmark_ticker: str = "SP500",
) -> Dict[str, Any]:
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    # --- caching ---
    # Cache is invalidated by "portfolio version" which we bump on any write.
    from .cache import cache_get, cache_set, get_portfolio_version, PERF_CACHE_TTL_SECONDS

    ver = get_portfolio_version(int(portfolio_id))
    cache_key = f"perf:v1:user={user_id}:pid={portfolio_id}:ver={ver}:start={start.isoformat()}:end={end.isoformat()}:bench={benchmark_ticker}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    portfolio, txs = _fetch_transactions(user_id, portfolio_id)
    start_cash = float(portfolio["cash_balance"] or 0)

    # Benchmark series (SP500 only for now — matches your "whole dataset" ask)
    bench_series = _sp500_index_series(start, end)
    days = [d for (d, _) in bench_series]
    bench_price = {d: v for (d, v) in bench_series}

    # Preload daily prices for tickers touched by txs
    touched = sorted({_norm_ticker(t["ticker"]) for t in txs})
    prices_by_ticker: Dict[str, List[Tuple[date, Optional[float]]]] = {t: [] for t in touched}

    if touched:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for t in touched:
                    cur.execute(
                        """
                        WITH dates AS (
                          SELECT d::date AS day
                          FROM generate_series(%s::date, %s::date, interval '1 day') d
                        )
                        SELECT
                          dates.day,
                          p.trade_date,
                          p.adj_close
                        FROM dates
                        LEFT JOIN LATERAL (
                          SELECT trade_date, adj_close
                          FROM sp500_historical
                          WHERE ticker = %s
                            AND trade_date <= dates.day
                            AND adj_close IS NOT NULL
                          ORDER BY trade_date DESC
                          LIMIT 1
                        ) p ON TRUE
                        ORDER BY dates.day ASC;
                        """,
                        (start, end, t),
                    )
                    rows = cur.fetchall()
                    prices_by_ticker[t] = [(r[0], (float(r[2]) if r[2] is not None else None)) for r in rows]

    # Index transactions by date for simulation
    tx_by_day: Dict[date, List[Dict[str, Any]]] = {}
    for tx in txs:
        td = date.fromisoformat(tx["trade_date"])
        if start <= td <= end:
            tx_by_day.setdefault(td, []).append(tx)

    # simulate day-by-day
    shares: Dict[str, float] = {}
    cash = start_cash

    series = []
    for i, day in enumerate(days):
        # apply todays transactions using trade price (ledger)
        for tx in tx_by_day.get(day, []):
            t = _norm_ticker(tx["ticker"])
            sh = float(tx["shares"])
            px = float(tx["price"])
            if tx["side"] == "BUY":
                cash -= sh * px
                shares[t] = shares.get(t, 0.0) + sh
            else:
                cash += sh * px
                shares[t] = shares.get(t, 0.0) - sh
                if shares[t] < 1e-9:
                    shares.pop(t, None)

        hv = 0.0
        for t, sh in shares.items():
            px = prices_by_ticker.get(t, [])[i][1] if t in prices_by_ticker else None
            if px is not None:
                hv += sh * px

        pv = cash + hv
        bv = bench_price.get(day)

        series.append({"date": day.isoformat(), "portfolio_value": pv, "benchmark_price": bv})

    # normalize to index=100
    first_port = None
    first_bench = None
    for pt in series:
        if first_port is None and pt["portfolio_value"] is not None:
            first_port = float(pt["portfolio_value"])
        if first_bench is None and pt["benchmark_price"] is not None:
            first_bench = float(pt["benchmark_price"])
        if first_port is not None and first_bench is not None:
            break

    for pt in series:
        pv = float(pt["portfolio_value"])
        bp = pt["benchmark_price"]
        pt["portfolio_index"] = (pv / first_port) * 100 if first_port and first_port > 0 else 100.0
        pt["benchmark_index"] = ((float(bp) / first_bench) * 100) if (bp is not None and first_bench and first_bench > 0) else None

    def _metrics_from_values(values: List[float]) -> Dict[str, Any]:
        if len(values) < 2:
            return {"total_return": 0.0, "vol_annual": None, "sharpe": None, "max_drawdown": None}

        rets = []
        for i in range(1, len(values)):
            prev = values[i - 1]
            cur = values[i]
            if prev <= 0:
                rets.append(0.0)
            else:
                rets.append((cur / prev) - 1.0)

        total_return = (values[-1] / values[0] - 1.0) if values[0] > 0 else 0.0

        import math
        if len(rets) >= 2:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            vol_daily = math.sqrt(var)
            vol_annual = vol_daily * math.sqrt(252.0)
        else:
            vol_annual = None

        sharpe = None
        if vol_annual and vol_annual > 0 and len(rets) >= 2:
            ann_ret = ((1.0 + total_return) ** (252.0 / max(1, len(rets))) - 1.0)
            sharpe = ann_ret / vol_annual

        peak = values[0]
        mdd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (v / peak) - 1.0 if peak > 0 else 0.0
            if dd < mdd:
                mdd = dd

        return {
            "total_return": total_return,
            "vol_annual": vol_annual,
            "sharpe": sharpe,
            "max_drawdown": mdd,
        }

    port_vals = [float(pt["portfolio_value"]) for pt in series]
    bench_vals = [float(pt["benchmark_price"]) for pt in series if pt.get("benchmark_price") is not None]

    portfolio_metrics = _metrics_from_values(port_vals)
    benchmark_metrics = _metrics_from_values(bench_vals) if len(bench_vals) == len(series) else None

    excess_total_return = None
    if series and series[0].get("benchmark_index") is not None and series[-1].get("benchmark_index") is not None:
        b0 = float(series[0]["benchmark_index"])
        b1 = float(series[-1]["benchmark_index"])
        if b0 > 0:
            bench_total = (b1 / b0) - 1.0
            excess_total_return = portfolio_metrics["total_return"] - bench_total

    result = {
        "portfolio_id": int(portfolio_id),
        "benchmark_ticker": "SP500",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "series": series,
        "metrics": {
            "portfolio": portfolio_metrics,
            "benchmark": benchmark_metrics,
            "excess_total_return": excess_total_return,
        },
    }

    cache_set(cache_key, result, ttl_seconds=PERF_CACHE_TTL_SECONDS)
    return result


# =========================
# CSV Export (performance series)
# =========================
def export_performance_csv(
    user_id: int,
    portfolio_id: int,
    start: date,
    end: date,
    benchmark_ticker: str = "SP500",
) -> Dict[str, Any]:
    """
    Returns a CSV export of the performance series (one row per day).

    Includes extra columns:
      - portfolio_daily_return
      - benchmark_daily_return
      - portfolio_cum_return
      - benchmark_cum_return
      - portfolio_drawdown
      - benchmark_drawdown
    """
    perf = get_portfolio_performance(
        user_id=user_id,
        portfolio_id=portfolio_id,
        start=start,
        end=end,
        benchmark_ticker=benchmark_ticker,
    )

    series = perf.get("series", []) or []

    # helpers
    def _pct_change(prev, cur):
        if prev is None or cur is None:
            return None
        try:
            prev = float(prev)
            cur = float(cur)
        except Exception:
            return None
        if prev == 0:
            return None
        return (cur / prev) - 1.0

    def _cum_return(first, cur):
        if first is None or cur is None:
            return None
        try:
            first = float(first)
            cur = float(cur)
        except Exception:
            return None
        if first == 0:
            return None
        return (cur / first) - 1.0

    def _drawdown(running_peak, cur):
        if running_peak is None or cur is None:
            return None
        try:
            running_peak = float(running_peak)
            cur = float(cur)
        except Exception:
            return None
        if running_peak == 0:
            return None
        return (cur / running_peak) - 1.0

    # compute derived columns
    first_pv = None
    first_bi = None

    prev_pv = None
    prev_bi = None

    peak_pv = None
    peak_bi = None

    rows_out = []
    for pt in series:
        d = pt.get("date")

        pv = pt.get("portfolio_value")
        bi = pt.get("benchmark_index")  # benchmark_index is the normalized benchmark curve

        # set firsts
        if first_pv is None and pv is not None:
            first_pv = pv
        if first_bi is None and bi is not None:
            first_bi = bi

        # daily returns
        p_ret = _pct_change(prev_pv, pv)
        b_ret = _pct_change(prev_bi, bi)

        # cumulative returns
        p_cum = _cum_return(first_pv, pv)
        b_cum = _cum_return(first_bi, bi)

        # running peaks for drawdown
        if pv is not None:
            peak_pv = pv if peak_pv is None else max(float(peak_pv), float(pv))
        if bi is not None:
            peak_bi = bi if peak_bi is None else max(float(peak_bi), float(bi))

        p_dd = _drawdown(peak_pv, pv)
        b_dd = _drawdown(peak_bi, bi)

        rows_out.append(
            {
                "date": d,
                "portfolio_value": pv,
                "portfolio_index": pt.get("portfolio_index"),
                "benchmark_price": pt.get("benchmark_price"),
                "benchmark_index": bi,
                "portfolio_daily_return": p_ret,
                "benchmark_daily_return": b_ret,
                "portfolio_cum_return": p_cum,
                "benchmark_cum_return": b_cum,
                "portfolio_drawdown": p_dd,
                "benchmark_drawdown": b_dd,
            }
        )

        prev_pv = pv if pv is not None else prev_pv
        prev_bi = bi if bi is not None else prev_bi

    import io, csv as _csv

    buf = io.StringIO()
    w = _csv.writer(buf)

    w.writerow(
        [
            "date",
            "portfolio_value",
            "portfolio_index",
            "benchmark_price",
            "benchmark_index",
            "portfolio_daily_return",
            "benchmark_daily_return",
            "portfolio_cum_return",
            "benchmark_cum_return",
            "portfolio_drawdown",
            "benchmark_drawdown",
        ]
    )

    for r in rows_out:
        w.writerow(
            [
                r["date"],
                r["portfolio_value"],
                r["portfolio_index"],
                r["benchmark_price"],
                r["benchmark_index"],
                r["portfolio_daily_return"],
                r["benchmark_daily_return"],
                r["portfolio_cum_return"],
                r["benchmark_cum_return"],
                r["portfolio_drawdown"],
                r["benchmark_drawdown"],
            ]
        )

    safe_bench = (perf.get("benchmark_ticker") or benchmark_ticker or "BENCH").replace("/", "_")
    filename = f"portfolio_{portfolio_id}_performance_{perf.get('start','')}_{perf.get('end','')}_{safe_bench}.csv"
    return {"filename": filename, "csv": buf.getvalue()}


# =========================
# Rebalance Helper (current positions from transactions)
# =========================
def rebalance_suggestion(
    user_id: int,
    portfolio_id: int,
    targets: List[Dict[str, Any]],
    include_cash_in_total: bool = True,
) -> Dict[str, Any]:
    if targets is None:
        targets = []

    target_map: Dict[str, float] = {}
    for t in targets:
        ticker = _norm_ticker(t.get("ticker"))
        w = t.get("weight")
        if w is None:
            raise HTTPException(status_code=400, detail=f"missing weight for {ticker}")
        try:
            w = float(w)
        except Exception:
            raise HTTPException(status_code=400, detail=f"invalid weight for {ticker}")
        if w < 0:
            raise HTTPException(status_code=400, detail=f"weight cannot be negative for {ticker}")
        target_map[ticker] = w

    sum_w = sum(target_map.values())
    if sum_w > 1.000001:
        raise HTTPException(status_code=400, detail="target weights must sum to <= 1.0")

    val = get_portfolio_valuation(user_id, portfolio_id)

    cash = float(val["totals"]["cash_current"] or 0)
    positions = val["positions"]

    holdings_value = float(val["totals"]["holdings_value"] or 0)
    total_value = float(val["totals"]["total_value"] or 0)

    denom = total_value if include_cash_in_total else (holdings_value if holdings_value > 0 else total_value)
    if denom <= 0:
        denom = 1.0

    cur_map = {p["ticker"]: p for p in positions}
    universe = sorted(set(list(target_map.keys()) + list(cur_map.keys())))

    suggestions = []
    net_trade_value = 0.0

    for ticker in universe:
        cur = cur_map.get(ticker)
        cur_mv = float(cur["market_value"]) if cur else 0.0
        last_price = cur["last_price"] if cur else None

        target_w = float(target_map.get(ticker, 0.0))
        target_value = target_w * denom

        delta_value = target_value - cur_mv

        if last_price is None or last_price == 0:
            delta_shares = None
        else:
            delta_shares = delta_value / float(last_price)

        net_trade_value += delta_value

        suggestions.append(
            {
                "ticker": ticker,
                "current_value": cur_mv,
                "current_weight": (cur_mv / denom) if denom > 0 else 0.0,
                "target_weight": target_w,
                "target_value": target_value,
                "delta_value": delta_value,
                "last_price": last_price,
                "delta_shares": delta_shares,
            }
        )

    cash_after = cash - net_trade_value

    return {
        "portfolio_id": int(portfolio_id),
        "include_cash_in_total": bool(include_cash_in_total),
        "denominator_value": denom,
        "cash_before": cash,
        "cash_after_est": cash_after,
        "targets_sum": sum_w,
        "suggestions": suggestions,
        "note": "Math-only rebalance helper. Not financial advice.",
    }
