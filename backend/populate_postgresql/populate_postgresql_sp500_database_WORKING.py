import yfinance as yf
import psycopg
from datetime import date, datetime, timedelta
import pandas as pd
import tickers_function_script


DB = dict(
    host="localhost",
    port=5432,
    dbname="stocks",
    user="devuser",
    password="devpass",
)


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

def fetch_history(ticker: str, start: str, end: str):
    df = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=False,
        actions=True,
        progress=False,
    )
    
    if df.empty:
        return []
    else:
        df = df.xs(ticker, axis=1, level='Ticker')
    

    # yfinance columns: Open High Low Close Adj Close Volume Dividends Stock Splits

    rows = []
    for dt, r in df.iterrows():
        rows.append((
            ticker,
            dt.date(),
            float(r["Open"]) if pd.notna(r["Open"]) else None,
            float(r["High"]) if pd.notna(r["High"]) else None,
            float(r["Low"]) if pd.notna(r["Low"]) else None,
            float(r["Close"]) if pd.notna(r["Close"]) else None,
            float(r["Adj Close"]) if pd.notna(r["Adj Close"]) else None,
            int(r["Volume"]) if pd.notna(r["Volume"]) else None,
            float(r["Dividends"]) if pd.notna(r["Dividends"]) else 0.0,
            float(r["Stock Splits"]) if pd.notna(r["Stock Splits"]) else 0.0,
        ))
    return rows
    

def main():
    
    tickers = tickers_function_script.get_sp500_tickers()
    start = "2025-01-01"
    end = "2026-01-30"  # end is exclusive in yfinance

    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            for t in tickers:
                rows = fetch_history(t, start, end)

                print("rows type:", type(rows), "len:", len(rows) if hasattr(rows, "__len__") else "n/a")

                if rows is None or len(rows) == 0:
                    print(f"{t}: no data returned")
                    continue

                cur.executemany(INSERT_SQL, rows)
                print(f"{t}: inserted/updated {len(rows)} rows")

if __name__ == "__main__":
    print("==================================================================================================================")
    print("=================================================================================================================")
    print(datetime.now())
    main()
    print(datetime.now())
