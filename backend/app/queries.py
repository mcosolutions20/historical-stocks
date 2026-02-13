from datetime import date
from typing import List, Dict, Literal, Optional

from .db import get_conn


def get_single_stock(ticker: str, start: date, end: date) -> Optional[Dict]:
    """
    Returns single-ticker stats for the date range PLUS a simple equal-weight benchmark.

    Adds:
      - best_day_date / best_day_return
      - worst_day_date / worst_day_return
      - max_drawdown (negative fraction)
      - max_drawdown_start_date (peak date)
      - max_drawdown_end_date (trough date)
      - beta (regr_slope of stock_return vs bench_return)
      - correlation (corr of stock_return vs bench_return)

    Benchmark definition:
      - Compute daily returns for all tickers in range
      - Benchmark daily return = AVG(daily_return) across tickers for each trade_date
      - Benchmark period return = compounded benchmark daily returns
      - Benchmark stddev = stddev_samp(benchmark daily returns)

    Also adds:
      - ticker_sharpe (approx): mean(daily_return)/stddev(daily_return) * sqrt(252)
      - benchmark_sharpe (approx)
      - information_ratio (approx): mean(active_daily)/stddev(active_daily) * sqrt(252)
      - alpha = ticker_period_return - benchmark_period_return
    """
    sql = """
    WITH prices AS (
      SELECT trade_date, adj_close
      FROM sp500_historical
      WHERE ticker = %s
        AND trade_date BETWEEN %s AND %s
        AND adj_close IS NOT NULL
      ORDER BY trade_date
    ),

    first_last AS (
      SELECT
        (SELECT adj_close FROM prices ORDER BY trade_date ASC  LIMIT 1) AS first_price,
        (SELECT adj_close FROM prices ORDER BY trade_date DESC LIMIT 1) AS last_price,
        (SELECT trade_date FROM prices ORDER BY trade_date ASC  LIMIT 1) AS first_date,
        (SELECT trade_date FROM prices ORDER BY trade_date DESC LIMIT 1) AS last_date,
        (SELECT COUNT(*) FROM prices) AS trading_days
    ),

    stock_daily AS (
      SELECT
        trade_date,
        adj_close,
        (adj_close / LAG(adj_close) OVER (ORDER BY trade_date) - 1) AS daily_return
      FROM prices
    ),

    best_worst AS (
      SELECT
        (SELECT trade_date
         FROM stock_daily
         WHERE daily_return IS NOT NULL
         ORDER BY daily_return DESC
         LIMIT 1) AS best_day_date,
        (SELECT daily_return
         FROM stock_daily
         WHERE daily_return IS NOT NULL
         ORDER BY daily_return DESC
         LIMIT 1) AS best_day_return,

        (SELECT trade_date
         FROM stock_daily
         WHERE daily_return IS NOT NULL
         ORDER BY daily_return ASC
         LIMIT 1) AS worst_day_date,
        (SELECT daily_return
         FROM stock_daily
         WHERE daily_return IS NOT NULL
         ORDER BY daily_return ASC
         LIMIT 1) AS worst_day_return
    ),

    -- Drawdown series: drawdown = (price / running_peak) - 1
    dd_base AS (
      SELECT
        trade_date,
        adj_close,
        MAX(adj_close) OVER (
          ORDER BY trade_date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_peak
      FROM prices
    ),

    dd AS (
      SELECT
        trade_date,
        adj_close,
        running_peak,
        MAX(trade_date) FILTER (WHERE adj_close = running_peak) OVER (
          ORDER BY trade_date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_peak_date,
        CASE
          WHEN running_peak IS NULL OR running_peak = 0 THEN NULL
          ELSE (adj_close / running_peak) - 1
        END AS drawdown
      FROM dd_base
    ),

    max_dd_row AS (
      SELECT
        drawdown AS max_drawdown,
        running_peak_date AS max_drawdown_start_date,
        trade_date AS max_drawdown_end_date
      FROM dd
      WHERE drawdown IS NOT NULL
      ORDER BY drawdown ASC
      LIMIT 1
    ),

    -- ===== BENCHMARK: equal-weight avg daily return across all tickers =====
    base_all AS (
      SELECT ticker, trade_date, adj_close
      FROM sp500_historical
      WHERE trade_date BETWEEN %s AND %s
        AND adj_close IS NOT NULL
    ),

    daily_all AS (
      SELECT
        ticker,
        trade_date,
        (adj_close / LAG(adj_close) OVER (PARTITION BY ticker ORDER BY trade_date) - 1) AS daily_return
      FROM base_all
    ),

    bench_daily AS (
      SELECT
        trade_date,
        AVG(daily_return) AS bench_return
      FROM daily_all
      WHERE daily_return IS NOT NULL
      GROUP BY trade_date
      ORDER BY trade_date
    ),

    bench_stats AS (
      SELECT
        CASE
          WHEN COUNT(*) = 0 THEN NULL
          ELSE EXP(SUM(LN(1 + bench_return))) - 1
        END AS bench_period_return,
        STDDEV_SAMP(bench_return) AS bench_stddev,
        AVG(bench_return) AS bench_mean_daily
      FROM bench_daily
      WHERE bench_return IS NOT NULL
        AND (1 + bench_return) > 0
    ),

    stock_stats AS (
      SELECT
        STDDEV_SAMP(daily_return) AS stock_stddev,
        AVG(daily_return) AS stock_mean_daily
      FROM stock_daily
      WHERE daily_return IS NOT NULL
    ),

    pair_daily AS (
      -- pair up stock vs bench on same trade_date
      SELECT
        s.trade_date,
        s.daily_return AS stock_return,
        b.bench_return
      FROM stock_daily s
      JOIN bench_daily b
        ON b.trade_date = s.trade_date
      WHERE s.daily_return IS NOT NULL
        AND b.bench_return IS NOT NULL
    ),

    beta_corr AS (
      SELECT
        -- beta = slope(stock_return ~ bench_return)
        REGR_SLOPE(stock_return, bench_return) AS beta,
        CORR(stock_return, bench_return) AS correlation
      FROM pair_daily
    ),

    active_daily AS (
      SELECT
        p.trade_date,
        (p.stock_return - p.bench_return) AS active_return
      FROM pair_daily p
    ),

    active_stats AS (
      SELECT
        STDDEV_SAMP(active_return) AS active_stddev,
        AVG(active_return) AS active_mean
      FROM active_daily
      WHERE active_return IS NOT NULL
    )

    SELECT
      %s AS ticker,

      -- Core ticker period return
      CASE
        WHEN first_last.first_price IS NULL
          OR first_last.last_price IS NULL
          OR first_last.first_price = 0
        THEN NULL
        ELSE (first_last.last_price / first_last.first_price) - 1
      END AS period_return,

      -- Daily volatility for ticker
      stock_stats.stock_stddev AS stddev,

      -- Extra ticker context
      first_last.first_date AS start_date,
      first_last.last_date  AS end_date,
      first_last.first_price AS start_adj_close,
      first_last.last_price AS end_adj_close,
      CASE
        WHEN first_last.first_price IS NULL OR first_last.last_price IS NULL
        THEN NULL
        ELSE (first_last.last_price - first_last.first_price)
      END AS dollar_change,
      first_last.trading_days AS trading_days,

      -- Best/Worst day
      best_worst.best_day_date,
      best_worst.best_day_return,
      best_worst.worst_day_date,
      best_worst.worst_day_return,

      -- Max drawdown + dates
      max_dd_row.max_drawdown,
      max_dd_row.max_drawdown_start_date,
      max_dd_row.max_drawdown_end_date,

      -- Benchmark stats
      bench_stats.bench_period_return AS benchmark_return,
      bench_stats.bench_stddev        AS benchmark_stddev,

      -- Sharpe-like (risk-free assumed ~0, daily -> annualized)
      CASE
        WHEN stock_stats.stock_stddev IS NULL OR stock_stats.stock_stddev = 0
        THEN NULL
        ELSE (stock_stats.stock_mean_daily / stock_stats.stock_stddev) * SQRT(252)
      END AS ticker_sharpe,

      CASE
        WHEN bench_stats.bench_stddev IS NULL OR bench_stats.bench_stddev = 0
        THEN NULL
        ELSE (bench_stats.bench_mean_daily / bench_stats.bench_stddev) * SQRT(252)
      END AS benchmark_sharpe,

      -- Information ratio (active vs benchmark)
      CASE
        WHEN active_stats.active_stddev IS NULL OR active_stats.active_stddev = 0
        THEN NULL
        ELSE (active_stats.active_mean / active_stats.active_stddev) * SQRT(252)
      END AS information_ratio,

      -- Alpha (simple period alpha)
      CASE
        WHEN bench_stats.bench_period_return IS NULL
        THEN NULL
        ELSE (
          CASE
            WHEN first_last.first_price IS NULL
              OR first_last.last_price IS NULL
              OR first_last.first_price = 0
            THEN NULL
            ELSE (first_last.last_price / first_last.first_price) - 1
          END
          - bench_stats.bench_period_return
        )
      END AS alpha,

      -- NEW: beta/correlation vs benchmark
      beta_corr.beta AS beta,
      beta_corr.correlation AS correlation

    FROM first_last
    CROSS JOIN bench_stats
    CROSS JOIN stock_stats
    CROSS JOIN active_stats
    CROSS JOIN best_worst
    LEFT JOIN max_dd_row ON TRUE
    CROSS JOIN beta_corr;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ticker, start, end, start, end, ticker))
            row = cur.fetchone()

    if not row:
        return None

    (
        t,
        period_return,
        stddev,
        start_date,
        end_date,
        start_adj_close,
        end_adj_close,
        dollar_change,
        trading_days,
        best_day_date,
        best_day_return,
        worst_day_date,
        worst_day_return,
        max_drawdown,
        max_drawdown_start_date,
        max_drawdown_end_date,
        benchmark_return,
        benchmark_stddev,
        ticker_sharpe,
        benchmark_sharpe,
        information_ratio,
        alpha,
        beta,
        correlation,
    ) = row

    if period_return is None and stddev is None and trading_days in (None, 0):
        return None

    return {
        "ticker": t,
        "return": float(period_return) if period_return is not None else None,
        "stddev": float(stddev) if stddev is not None else None,

        "start_date": str(start_date) if start_date is not None else None,
        "end_date": str(end_date) if end_date is not None else None,
        "start_adj_close": float(start_adj_close) if start_adj_close is not None else None,
        "end_adj_close": float(end_adj_close) if end_adj_close is not None else None,
        "dollar_change": float(dollar_change) if dollar_change is not None else None,
        "trading_days": int(trading_days) if trading_days is not None else None,

        "best_day_date": str(best_day_date) if best_day_date is not None else None,
        "best_day_return": float(best_day_return) if best_day_return is not None else None,
        "worst_day_date": str(worst_day_date) if worst_day_date is not None else None,
        "worst_day_return": float(worst_day_return) if worst_day_return is not None else None,

        "max_drawdown": float(max_drawdown) if max_drawdown is not None else None,
        "max_drawdown_start_date": str(max_drawdown_start_date) if max_drawdown_start_date is not None else None,
        "max_drawdown_end_date": str(max_drawdown_end_date) if max_drawdown_end_date is not None else None,

        "benchmark_return": float(benchmark_return) if benchmark_return is not None else None,
        "benchmark_stddev": float(benchmark_stddev) if benchmark_stddev is not None else None,

        "ticker_sharpe": float(ticker_sharpe) if ticker_sharpe is not None else None,
        "benchmark_sharpe": float(benchmark_sharpe) if benchmark_sharpe is not None else None,
        "information_ratio": float(information_ratio) if information_ratio is not None else None,
        "alpha": float(alpha) if alpha is not None else None,

        "beta": float(beta) if beta is not None else None,
        "correlation": float(correlation) if correlation is not None else None,
    }




def get_outliers(
    start: date,
    end: date,
    direction: Literal["top", "bottom"],
    n: int,
) -> List[Dict]:
    order = "DESC" if direction == "top" else "ASC"

    sql = f"""
    WITH base AS (
      SELECT ticker, trade_date, adj_close
      FROM sp500_historical
      WHERE trade_date BETWEEN %s AND %s
        AND adj_close IS NOT NULL
    ),
    daily AS (
      SELECT
        ticker,
        trade_date,
        (adj_close / LAG(adj_close) OVER (PARTITION BY ticker ORDER BY trade_date) - 1) AS daily_return
      FROM base
    ),
    first_last AS (
      SELECT
        ticker,
        (ARRAY_AGG(adj_close ORDER BY trade_date ASC))[1] AS first_price,
        (ARRAY_AGG(adj_close ORDER BY trade_date DESC))[1] AS last_price,
        COUNT(*) AS points
      FROM base
      GROUP BY ticker
    ),
    stats AS (
      SELECT
        fl.ticker,
        CASE
          WHEN fl.points < 2 OR fl.first_price IS NULL OR fl.last_price IS NULL OR fl.first_price = 0
            THEN NULL
          ELSE (fl.last_price / fl.first_price) - 1
        END AS period_return,
        (SELECT STDDEV_SAMP(d.daily_return)
           FROM daily d
           WHERE d.ticker = fl.ticker AND d.daily_return IS NOT NULL
        ) AS stddev
      FROM first_last fl
    )
    SELECT ticker, period_return, stddev
    FROM stats
    WHERE period_return IS NOT NULL
    ORDER BY period_return {order}
    LIMIT %s;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (start, end, n))
            rows = cur.fetchall()

    results = []
    for t, period_return, stddev in rows:
        results.append({
            "ticker": t,
            "return": float(period_return) if period_return is not None else None,
            "stddev": float(stddev) if stddev is not None else None,
        })

    return results

def get_meta() -> Dict:
    """
    Global metadata about the DB table.
    Frontend expects:
      - min_date (YYYY-MM-DD)
      - max_date (YYYY-MM-DD)
      - tickers (distinct ticker count)
      - rows (total row count)
    """
    sql = """
    SELECT
      MIN(trade_date) AS min_date,
      MAX(trade_date) AS max_date,
      COUNT(DISTINCT ticker) AS tickers,
      COUNT(*) AS rows
    FROM sp500_historical
    WHERE adj_close IS NOT NULL;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

    if not row:
        return {"min_date": None, "max_date": None, "tickers": 0, "rows": 0}

    min_date, max_date, tickers, rows = row

    return {
        "min_date": str(min_date) if min_date is not None else None,
        "max_date": str(max_date) if max_date is not None else None,
        "tickers": int(tickers) if tickers is not None else 0,
        "rows": int(rows) if rows is not None else 0,
    }
