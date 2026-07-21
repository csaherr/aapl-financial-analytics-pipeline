"""AAPL financial analytics pipeline.

The pipeline can load a saved Alpha Vantage JSON response or request fresh daily
market data, calculate interpretable price and volatility metrics, assign
rule-based market-behavior labels, persist the records to SQLite, and print SQL
summary results.

The Buy/Sell/Hold labels describe same-day price behavior. They are not a
forecast or investment recommendation.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import requests

API_URL = "https://www.alphavantage.co/query"
DEFAULT_SYMBOL = "AAPL"
DEFAULT_LIMIT = 20
TIME_SERIES_KEY = "Time Series (Daily)"


class PipelineError(RuntimeError):
    """Raised when the pipeline cannot safely continue."""


def get_stock_data(symbol: str, api_key: str, timeout: int = 30) -> dict[str, Any]:
    """Request daily stock data from Alpha Vantage and return parsed JSON."""
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol.upper(),
        "apikey": api_key,
    }
    try:
        response = requests.get(API_URL, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PipelineError(f"Alpha Vantage request failed: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise PipelineError("Alpha Vantage returned a non-JSON response.") from exc

    return validate_response(data)


def load_json_response(path: Path) -> dict[str, Any]:
    """Load and validate a saved Alpha Vantage JSON response."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Could not read JSON input {path}: {exc}") from exc
    return validate_response(data)


def validate_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate required Alpha Vantage response fields and surface API errors."""
    if not isinstance(data, dict):
        raise PipelineError("Expected the API response to be a JSON object.")

    for error_key in ("Error Message", "Note", "Information"):
        if error_key in data and TIME_SERIES_KEY not in data:
            raise PipelineError(f"Alpha Vantage response: {data[error_key]}")

    time_series = data.get(TIME_SERIES_KEY)
    if not isinstance(time_series, dict) or not time_series:
        raise PipelineError(f"Missing or empty '{TIME_SERIES_KEY}' section.")

    return data


def classify_volatility(daily_range_percent: float) -> str:
    """Classify intraday range as Low, Moderate, or High volatility."""
    if daily_range_percent < 1.5:
        return "Low"
    if daily_range_percent <= 3.0:
        return "Moderate"
    return "High"


def classify_movement(percent_change: float) -> str:
    """Classify open-to-close movement as Positive, Neutral, or Negative."""
    if percent_change > 0.5:
        return "Positive"
    if percent_change < -0.5:
        return "Negative"
    return "Neutral"


def generate_signal(movement_label: str, volatility_label: str) -> str:
    """Create a descriptive signal with a conservative high-volatility override."""
    if volatility_label == "High":
        return "Hold"
    if movement_label == "Positive":
        return "Buy"
    if movement_label == "Negative":
        return "Sell"
    return "Hold"


def calculate_metrics(
    trade_date: str,
    raw_record: dict[str, str],
    symbol: str,
) -> dict[str, Any]:
    """Convert one raw API record into a validated analytical record."""
    required_fields = {
        "1. open",
        "2. high",
        "3. low",
        "4. close",
        "5. volume",
    }
    missing = required_fields.difference(raw_record)
    if missing:
        raise PipelineError(
            f"Record {trade_date} is missing fields: {', '.join(sorted(missing))}"
        )

    try:
        open_price = float(raw_record["1. open"])
        high_price = float(raw_record["2. high"])
        low_price = float(raw_record["3. low"])
        close_price = float(raw_record["4. close"])
        volume = int(raw_record["5. volume"])
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"Record {trade_date} contains non-numeric values.") from exc

    if open_price <= 0:
        raise PipelineError(f"Record {trade_date} has a non-positive opening price.")
    if high_price < low_price:
        raise PipelineError(f"Record {trade_date} has high price below low price.")

    price_change = close_price - open_price
    percent_change = (price_change / open_price) * 100
    daily_range = high_price - low_price
    daily_range_percent = (daily_range / open_price) * 100
    volatility_label = classify_volatility(daily_range_percent)
    movement_label = classify_movement(percent_change)
    signal = generate_signal(movement_label, volatility_label)

    return {
        "symbol": symbol.upper(),
        "trade_date": trade_date,
        "open_price": open_price,
        "high_price": high_price,
        "low_price": low_price,
        "close_price": close_price,
        "volume": volume,
        "price_change": price_change,
        "percent_change": percent_change,
        "daily_range": daily_range,
        "daily_range_percent": daily_range_percent,
        "movement_label": movement_label,
        "volatility_label": volatility_label,
        "signal": signal,
    }


def parse_daily_records(
    data: dict[str, Any], symbol: str, limit: int = DEFAULT_LIMIT
) -> list[dict[str, Any]]:
    """Parse the most recent valid daily records from a response."""
    if limit < 1:
        raise PipelineError("Record limit must be at least 1.")

    time_series = data[TIME_SERIES_KEY]
    records: list[dict[str, Any]] = []

    for trade_date in sorted(time_series.keys(), reverse=True):
        try:
            record = calculate_metrics(trade_date, time_series[trade_date], symbol)
        except PipelineError as exc:
            print(f"Skipping invalid record: {exc}", file=sys.stderr)
            continue
        records.append(record)
        if len(records) >= limit:
            break

    if not records:
        raise PipelineError("No valid daily records were available for analysis.")
    return records


def create_database(database_path: Path) -> None:
    """Create the SQLite database and analytical table when needed."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
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
            )
            """
        )


def insert_records(database_path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Insert or update processed records and return the number written."""
    rows = list(records)
    sql = """
        INSERT INTO stock_analysis (
            symbol, trade_date, open_price, high_price, low_price, close_price,
            volume, price_change, percent_change, daily_range,
            daily_range_percent, movement_label, volatility_label, signal
        ) VALUES (
            :symbol, :trade_date, :open_price, :high_price, :low_price,
            :close_price, :volume, :price_change, :percent_change,
            :daily_range, :daily_range_percent, :movement_label,
            :volatility_label, :signal
        )
        ON CONFLICT(symbol, trade_date) DO UPDATE SET
            open_price = excluded.open_price,
            high_price = excluded.high_price,
            low_price = excluded.low_price,
            close_price = excluded.close_price,
            volume = excluded.volume,
            price_change = excluded.price_change,
            percent_change = excluded.percent_change,
            daily_range = excluded.daily_range,
            daily_range_percent = excluded.daily_range_percent,
            movement_label = excluded.movement_label,
            volatility_label = excluded.volatility_label,
            signal = excluded.signal
    """
    with sqlite3.connect(database_path) as connection:
        connection.executemany(sql, rows)
    return len(rows)


def run_analytics_queries(database_path: Path, symbol: str) -> dict[str, Any]:
    """Run the core SQL summaries used in the project report."""
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        signal_distribution = [
            dict(row)
            for row in connection.execute(
                """
                SELECT signal, COUNT(*) AS signal_count
                FROM stock_analysis
                WHERE symbol = ?
                GROUP BY signal
                ORDER BY signal_count DESC, signal
                """,
                (symbol.upper(),),
            )
        ]
        average_change = [
            dict(row)
            for row in connection.execute(
                """
                SELECT signal, ROUND(AVG(percent_change), 2) AS avg_percent_change
                FROM stock_analysis
                WHERE symbol = ?
                GROUP BY signal
                ORDER BY signal
                """,
                (symbol.upper(),),
            )
        ]
        highest_volatility = connection.execute(
            """
            SELECT trade_date, symbol,
                   ROUND(daily_range_percent, 2) AS range_percent,
                   volatility_label, signal
            FROM stock_analysis
            WHERE symbol = ?
            ORDER BY daily_range_percent DESC
            LIMIT 1
            """,
            (symbol.upper(),),
        ).fetchone()
        high_volatility_days = [
            dict(row)
            for row in connection.execute(
                """
                SELECT trade_date, symbol,
                       ROUND(percent_change, 2) AS percent_change,
                       ROUND(daily_range_percent, 2) AS range_percent,
                       signal
                FROM stock_analysis
                WHERE symbol = ? AND volatility_label = 'High'
                ORDER BY trade_date DESC
                """,
                (symbol.upper(),),
            )
        ]
        average_close = connection.execute(
            """
            SELECT symbol, ROUND(AVG(close_price), 2) AS avg_closing_price
            FROM stock_analysis
            WHERE symbol = ?
            GROUP BY symbol
            """,
            (symbol.upper(),),
        ).fetchone()

    return {
        "signal_distribution": signal_distribution,
        "average_change_by_signal": average_change,
        "highest_volatility_day": dict(highest_volatility)
        if highest_volatility
        else None,
        "high_volatility_days": high_volatility_days,
        "average_closing_price": dict(average_close) if average_close else None,
    }


def print_summary_report(
    records: list[dict[str, Any]], query_results: dict[str, Any]
) -> None:
    """Print a concise analytical summary for the selected sample."""
    signal_counts = Counter(record["signal"] for record in records)
    volatility_counts = Counter(record["volatility_label"] for record in records)
    symbol = records[0]["symbol"]
    dates = sorted(record["trade_date"] for record in records)

    print(f"\n{symbol} Financial Analytics Summary")
    print("=" * 38)
    print(f"Records processed: {len(records)}")
    print(f"Sample period: {dates[0]} through {dates[-1]}")
    print(
        "Signals: "
        f"Buy={signal_counts['Buy']}, "
        f"Sell={signal_counts['Sell']}, "
        f"Hold={signal_counts['Hold']}"
    )
    print(
        "Volatility: "
        f"Low={volatility_counts['Low']}, "
        f"Moderate={volatility_counts['Moderate']}, "
        f"High={volatility_counts['High']}"
    )

    highest = query_results.get("highest_volatility_day")
    if highest:
        print(
            "Highest-volatility day: "
            f"{highest['trade_date']} ({highest['range_percent']}%, "
            f"signal={highest['signal']})"
        )

    average_close = query_results.get("average_closing_price")
    if average_close:
        print(f"Average closing price: ${average_close['avg_closing_price']:.2f}")

    print(
        "\nNote: Signals classify same-day behavior and are not investment advice."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a rule-based stock analytics dataset and SQLite database."
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Ticker symbol.")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Number of recent daily records to process.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("database/aapl_stock_analysis.db"),
        help="SQLite output path.",
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        help="Use a saved Alpha Vantage response instead of a live request.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.input_json:
            data = load_json_response(args.input_json)
        else:
            api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
            if not api_key:
                raise PipelineError(
                    "Set ALPHA_VANTAGE_API_KEY or provide --input-json."
                )
            data = get_stock_data(args.symbol, api_key)

        records = parse_daily_records(data, args.symbol, args.limit)
        create_database(args.database)
        rows_written = insert_records(args.database, records)
        query_results = run_analytics_queries(args.database, args.symbol)
        print_summary_report(records, query_results)
        print(f"Rows written to {args.database}: {rows_written}")
        return 0
    except PipelineError as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
