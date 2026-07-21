-- 1. Signal distribution
SELECT
    signal,
    COUNT(*) AS signal_count
FROM stock_analysis
GROUP BY signal
ORDER BY signal_count DESC, signal;

-- 2. Average percent change by signal
SELECT
    signal,
    ROUND(AVG(percent_change), 2) AS avg_percent_change
FROM stock_analysis
GROUP BY signal
ORDER BY signal;

-- 3. Highest-volatility trading day
SELECT
    trade_date,
    symbol,
    ROUND(daily_range_percent, 2) AS range_percent,
    volatility_label,
    signal
FROM stock_analysis
ORDER BY daily_range_percent DESC
LIMIT 1;

-- 4. High-volatility trading days
SELECT
    trade_date,
    symbol,
    ROUND(percent_change, 2) AS percent_change,
    ROUND(daily_range_percent, 2) AS range_percent,
    signal
FROM stock_analysis
WHERE volatility_label = 'High'
ORDER BY trade_date DESC;

-- 5. Average closing price by symbol
SELECT
    symbol,
    ROUND(AVG(close_price), 2) AS avg_closing_price
FROM stock_analysis
GROUP BY symbol;
