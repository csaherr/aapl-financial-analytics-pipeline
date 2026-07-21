"""Generate portfolio visuals from the SQLite analysis database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


def load_records(database_path: Path, symbol: str) -> list[sqlite3.Row]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        return list(
            connection.execute(
                """
                SELECT trade_date, close_price, percent_change,
                       daily_range_percent, signal, volatility_label
                FROM stock_analysis
                WHERE symbol = ?
                ORDER BY trade_date
                """,
                (symbol.upper(),),
            )
        )


def save_charts(records: list[sqlite3.Row], output_dir: Path, symbol: str) -> None:
    if not records:
        raise ValueError(f"No records found for {symbol}.")
    output_dir.mkdir(parents=True, exist_ok=True)

    dates = [row["trade_date"] for row in records]
    close_prices = [row["close_price"] for row in records]
    percent_changes = [row["percent_change"] for row in records]

    plt.figure(figsize=(10, 5.5))
    plt.plot(dates, close_prices, marker="o")
    plt.title(f"{symbol.upper()} Closing Price - Analysis Window")
    plt.xlabel("Trade date")
    plt.ylabel("Closing price ($)")
    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "closing_price_trend.png", dpi=180)
    plt.close()

    plt.figure(figsize=(10, 5.5))
    plt.bar(dates, percent_changes)
    plt.axhline(0, linewidth=1)
    plt.title(f"{symbol.upper()} Daily Open-to-Close Percent Change")
    plt.xlabel("Trade date")
    plt.ylabel("Percent change (%)")
    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "daily_percent_change.png", dpi=180)
    plt.close()

    signal_labels = ["Buy", "Sell", "Hold"]
    signal_counts = [
        sum(1 for row in records if row["signal"] == label)
        for label in signal_labels
    ]
    plt.figure(figsize=(7.5, 5.2))
    bars = plt.bar(signal_labels, signal_counts)
    plt.title("Rule-Based Signal Distribution")
    plt.xlabel("Signal")
    plt.ylabel("Trading days")
    plt.bar_label(bars)
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "signal_distribution.png", dpi=180)
    plt.close()

    volatility_labels = ["Low", "Moderate", "High"]
    volatility_counts = [
        sum(1 for row in records if row["volatility_label"] == label)
        for label in volatility_labels
    ]
    plt.figure(figsize=(7.5, 5.2))
    bars = plt.bar(volatility_labels, volatility_counts)
    plt.title("Volatility Classification Distribution")
    plt.xlabel("Volatility label")
    plt.ylabel("Trading days")
    plt.bar_label(bars)
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "volatility_distribution.png", dpi=180)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database", type=Path, default=Path("database/aapl_stock_analysis.db")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("assets"))
    parser.add_argument("--symbol", default="AAPL")
    args = parser.parse_args()

    records = load_records(args.database, args.symbol)
    save_charts(records, args.output_dir, args.symbol)
    print(f"Saved charts to {args.output_dir}")


if __name__ == "__main__":
    main()
