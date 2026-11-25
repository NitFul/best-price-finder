r"""Refresh Rakuten cash back rates in cashback_rates.csv.

Usage:
    .\.venv\Scripts\python update_rates.py              # all stores
    .\.venv\Scripts\python update_rates.py Nike Amazon  # only these stores

Each store uses 1 Serper search credit.
"""

import sys

from pricefinder.cashback import load_rows, save_rows
from pricefinder.config import get_setting
from pricefinder.rakuten import update_row
from pricefinder.search import SearchError


def main(only: list[str]) -> None:
    api_key = get_setting("SERPER_API_KEY")
    if not api_key:
        sys.exit("SERPER_API_KEY is not set in .env")
    rows = load_rows()
    wanted = {s.lower() for s in only}
    for row in rows:
        if wanted and row["store"].lower() not in wanted:
            continue
        try:
            result = update_row(row, api_key)
        except SearchError as e:
            result = f"error: {e}"
        print(f"{row['store']:28} {result}")
    save_rows(rows)
    print("Saved cashback_rates.csv")


if __name__ == "__main__":
    main(sys.argv[1:])
