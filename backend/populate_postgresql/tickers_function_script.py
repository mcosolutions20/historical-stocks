from pytickersymbols import PyTickerSymbols

def get_sp500_tickers():
    """
    Retrieve S&P 500 ticker symbols using pytickersymbols.

    Returns:
        List of S&P 500 ticker symbols as strings.
    """
    # Get S&P 500 tickers
    stock_data = PyTickerSymbols()

    # DIRECT METHOD: Returns a list of strings (e.g., ['AAPL', 'MSFT', ...])
    sp500_tickers = stock_data.get_yahoo_ticker_symbols_by_index('S&P 500')

    # print(sp500_tickers)
    stocks =[]
    for stock in sp500_tickers:
        for s in stock:
            if "." not in s:  # Exclude tickers with dots
                stocks.append(s)

    return stocks  

# Additional function to get tickers including sp500 tickers in foreign markets
def get_sp500_tickers_with_dots():
    """
    Retrieve S&P 500 ticker symbols including those with dots using pytickersymbols.

    Returns:
        List of S&P 500 ticker symbols as strings.
    """
    # Get S&P 500 tickers
    stock_data = PyTickerSymbols()

    # DIRECT METHOD: Returns a list of strings (e.g., ['AAPL', 'MSFT', ...])
    sp500_tickers = stock_data.get_yahoo_ticker_symbols_by_index('S&P 500')

    # print(sp500_tickers)
    stocks =[]
    for stock in sp500_tickers:
        for s in stock:
            if "." in s:  # Exclude tickers with dots
                stocks.append(s)

    return stocks



 