CREATE TABLE IF NOT EXISTS sp500_historical (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ticker VARCHAR(20) NOT NULL,
  trade_date DATE NOT NULL,
  open NUMERIC(12,4),
  high NUMERIC(12,4),
  low NUMERIC(12,4),
  close NUMERIC(12,4),
  adj_close NUMERIC(12,4),
  volume BIGINT,
  dividends NUMERIC(12,4),
  stock_splits NUMERIC(8,4),
  CONSTRAINT sp500_historical_ticker_date_uniq UNIQUE (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS sp500_historical_ticker_date_idx
  ON sp500_historical (ticker, trade_date);
