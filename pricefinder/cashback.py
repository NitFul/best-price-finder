"""Cashback rates, kept in an editable CSV file (cashback_rates.csv).

Rakuten has no free public API and blocks automated page reads, so rates
are entered by hand. They change often; update them before a big purchase.
"""

import csv
import re
from pathlib import Path
from urllib.parse import quote_plus

RATES_FILE = Path(__file__).resolve().parent.parent / "cashback_rates.csv"
FIELDS = ["store", "aliases", "rakuten_percent", "notes"]


def normalize(name: str) -> str:
    """'Dick's Sporting Goods' -> 'dickssportinggoods', 'Amazon.com' -> 'amazon'."""
    n = name.lower().strip()
    n = re.sub(r"\.(com|net|org|us)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)


def load_rows(path: Path = RATES_FILE) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [{k: (row.get(k) or "").strip() for k in FIELDS} for row in csv.DictReader(f)]


def save_rows(rows: list[dict], path: Path = RATES_FILE) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in rows:
            if (row.get("store") or "").strip():
                w.writerow({k: (row.get(k) or "") for k in FIELDS})


class CashbackTable:
    def __init__(self, rows: list[dict]):
        self._by_name: dict[str, tuple[str, float | None]] = {}
        for row in rows:
            store = row["store"]
            try:
                pct = float(row["rakuten_percent"].rstrip("%")) if row["rakuten_percent"] else None
            except ValueError:
                pct = None
            names = [store] + [a for a in row["aliases"].split("|") if a.strip()]
            for name in names:
                self._by_name[normalize(name)] = (store, pct)

    def lookup(self, store_name: str) -> tuple[str | None, float | None]:
        """Return (known store name, Rakuten %) or (None, None) if not in the table."""
        key = normalize(store_name)
        if key in self._by_name:
            return self._by_name[key]
        # Partial match, e.g. "Dick's Sporting Goods - Seller" contains "dickssportinggoods".
        for name, value in self._by_name.items():
            if len(name) >= 4 and (name in key or key in name):
                return value
        return None, None


def rakuten_check_url(store_name: str) -> str:
    """A search link to confirm the store's current Rakuten rate."""
    return "https://www.google.com/search?q=" + quote_plus(f"Rakuten {store_name} cash back")
