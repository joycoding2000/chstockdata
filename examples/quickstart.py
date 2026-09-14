"""Minimal end-to-end example (runs offline against cached data, online otherwise).

    python examples/quickstart.py 600519
"""

from __future__ import annotations

import sys

import chstockdata as cd


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "600519"

    print("resolve_ticker('贵州茅台') ->", cd.resolve_ticker("贵州茅台"))

    df = cd.get_stock_data(ticker, 30)
    if df is None or getattr(df, "empty", True):
        print(f"no daily bars for {ticker} (all sources unavailable?)")
    else:
        print(f"{ticker} last 3 daily bars:")
        print(df.tail(3).to_string(index=False))

    snapshot = cd.get_realtime_snapshot(ticker)
    if snapshot:
        price = snapshot.get("price") or snapshot.get("last")
        print(f"{ticker} realtime: {snapshot.get('source')}: {price}")

    print("market breadth source:", end=" ")
    breadth = cd.get_market_breadth()
    print(type(breadth).__name__)


if __name__ == "__main__":
    main()
