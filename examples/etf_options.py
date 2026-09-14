"""ETF option chain demo (live, Sina source).

    python examples/etf_options.py 510050
"""

from __future__ import annotations

import sys

import chstockdata as cd


def main() -> None:
    underlying = sys.argv[1] if len(sys.argv) > 1 else "510050"

    contracts = cd.list_etf_option_contracts(underlying, call=True)
    print(f"{underlying} call contracts by month: {list(contracts)[:4]} ...")

    chain = cd.get_etf_option_chain(underlying)
    print(
        f"month={chain['month']} calls={len(chain['call_contracts'])} "
        f"puts={len(chain['put_contracts'])} quoted={len(chain['rows'])} "
        f"failed={len(chain['failed_contracts'])}"
    )
    for row in chain["rows"][:5]:
        greeks = row.get("greeks") or {}
        iv = greeks.get("iv")
        iv_text = f"{iv:.2%}" if iv is not None else "n/a"
        print(
            f"  [{row['direction']}] {row.get('name') or row['code']} "
            f"strike={row.get('strike')} last={row.get('last')} "
            f"IV={iv_text} delta={greeks.get('delta')}"
        )


if __name__ == "__main__":
    main()
