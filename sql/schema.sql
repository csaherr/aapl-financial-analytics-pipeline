-- SQLite schema for the AAPL financial analytics pipeline.
CREATE TABLE IF NOT EXISTS stock_analysis (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume INTEGER NOT NULL,
    price_change REAL NOT NULL,
    percent_change REAL NOT NULL,
    daily_range REAL NOT NULL,
    daily_range_percent REAL NOT NULL,
    movement_label TEXT NOT NULL,
    volatility_label TEXT NOT NULL,
    signal TEXT NOT NULL,
    PRIMARY KEY (symbol, trade_date)
);
