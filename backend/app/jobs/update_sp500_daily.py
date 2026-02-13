import logging
from datetime import datetime, timedelta, timezone
from typing import List

import pandas as pd
import yfinance as yf

from app.db import get_conn
from populate_postgresql.tickers_function_script import get_sp500_tickers

INSERT_SQL = """
INSERT INTO sp500_historical
(ticker, trade_date, open, high, low, close, adj_close, volume, dividends, stock_splits)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (ticker, trade_date) DO UPDATE SET
  open = EXCLUDED.open,
  high = EXCLUDED.high,
  low = EXCLUDED.low,
  close = EXCLUDED.close,
  adj_close = EXCLUDED.adj_close,
  volume = EXCLUDED.volume,
  dividends = EXCLUDED.dividends,
  stock_splits = EXCLUDED.stock_splits;
"""

log = logging.getLogger("daily_sp500_update")


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _chunks(xs: List[str], n: int):
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


def _as_float(v):
    if pd.isna(v):
        return None
    return float(v)


def _as_int(v):
    if pd.isna(v):
        return None
    return int(v)


def _download_batch(tickers: List[str], start: str, end: str) -> pd.DataFrame:
    """
    yfinance returns a DataFrame.
    For multiple tickers, columns are a MultiIndex: (PriceField, Ticker)
    """
    df = yf.download(
        tickers=tickers,
        start=start,
        end=end,           # end is exclusive
        auto_adjust=False,
        actions=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    return df


def _rows_from_batch(df: pd.DataFrame, tickers: List[str]):
    rows = []
    if df is None or df.empty:
        return rows

    # For multiple tickers, expect MultiIndex columns (field, ticker)
    # For single ticker, yfinance sometimes returns flat columns
    multi = isinstance(df.columns, pd.MultiIndex)

    for t in tickers:
        if multi:
            if ("Open", t) not in df.columns:
                continue
            sub = df.xs(t, axis=1, level=1, drop_level=False)
            # sub columns remain MultiIndex; access via ("Open", t)
            for dt, r in sub.iterrows():
                rows.append(
                    (
                        t,
                        dt.date(),
                        _as_float(r.get(("Open", t))),
                        _as_float(r.get(("High", t))),
                        _as_float(r.get(("Low", t))),
                        _as_float(r.get(("Close", t))),
                        _as_float(r.get(("Adj Close", t))),
                        _as_int(r.get(("Volume", t))),
                        _as_float(r.get(("Dividends", t))) or 0.0,
                        _as_float(r.get(("Stock Splits", t))) or 0.0,
                    )
                )
        else:
            # flat columns case
            for dt, r in df.iterrows():
                rows.append(
                    (
                        t,
                        dt.date(),
                        _as_float(r.get("Open")),
                        _as_float(r.get("High")),
                        _as_float(r.get("Low")),
                        _as_float(r.get("Close")),
                        _as_float(r.get("Adj Close")),
                        _as_int(r.get("Volume")),
                        _as_float(r.get("Dividends")) or 0.0,
                        _as_float(r.get("Stock Splits")) or 0.0,
                    )
                )

    return rows


def run(days_back: int = 10, batch_size: int = 50):
    """
    Pull a small rolling window so weekends/holidays are covered automatically.
    """
    _setup_logging()

    tickers = get_sp500_tickers()
    tickers = sorted(set(tickers))

    # Use UTC dates; the market-close “yesterday” is reliably available by morning ET.
    now = datetime.now(timezone.utc)
    start_dt = (now - timedelta(days=days_back)).date()
    end_dt = (now + timedelta(days=1)).date()  # end exclusive, include up to today

    start = start_dt.isoformat()
    end = end_dt.isoformat()

    log.info("Starting daily update: tickers=%d days_back=%d start=%s end(excl)=%s", len(tickers), days_back, start, end)

    total_rows = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for batch in _chunks(tickers, batch_size):
                df = _download_batch(batch, start, end)
                rows = _rows_from_batch(df, batch)

                if not rows:
                    log.warning("Batch had no rows: size=%d", len(batch))
                    continue

                cur.executemany(INSERT_SQL, rows)
                total_rows += len(rows)
                log.info("Inserted/updated rows=%d (running_total=%d)", len(rows), total_rows)

    log.info("DONE. total_rows=%d", total_rows)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--days-back", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=50)
    args = p.parse_args()

    run(days_back=args.days_back, batch_size=args.batch_size)

# to run this script locally, you can use the following command:
# docker compose exec backend python -m app.jobs.update_sp500_daily --days-back 10