"""CYQ chip distribution demo (needs the optional baostock extra).

    pip install "chstockdata[baostock]"
    python examples/chip_distribution.py 600519 2026-02-01 2026-09-11
"""

from __future__ import annotations

import sys

import chstockdata as cd


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "600519"
    start = sys.argv[2] if len(sys.argv) > 2 else "2026-02-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2026-09-11"

    result = cd.get_chip_distribution(ticker, start, end)
    metrics = result["metrics"]
    quality = result["input_quality"]
    print(
        f"{result['ticker']} {start}~{end} | {result['trading_days']} trading days "
        f"| cumulative turnover {quality['cumulative_turnover_pct']:.1f}%"
    )
    print(
        f"  price {metrics['price']:.2f} | profit ratio {metrics['profit_ratio']:.2%}"
        f" | avg cost {metrics['avg_cost']:.2f}"
    )
    print(
        f"  90% cost range {metrics['cost_90'][0]:.2f}~{metrics['cost_90'][1]:.2f}"
        f" (concentration {metrics['concentration_90']:.2%})"
    )
    print(f"  chip peak {metrics['peak_price']:.2f}")
    print(f"  note: {result['disclaimer']}")


if __name__ == "__main__":
    main()
