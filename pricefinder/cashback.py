"""Cashback rates, kept in an editable CSV file (cashback_rates.csv).

Rates can be refreshed automatically from Google search results (see
rakuten.py) or entered by hand. They change often; refresh before a big purchase.
"""

import csv
import re
from pathlib import Path
from urllib.parse import quote_plus

RATES_FILE = Path(__file__).resolve().parent.parent / "cashback_rates.csv"
FIELDS = ["store", "aliases", "rakuten_percent", "notes", "last_checked", "source"]


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
        self._by_name: dict[str, dict] = {}
        for row in rows:
            store = row["store"]
            try:
                pct = float(row["rakuten_percent"].rstrip("%")) if row["rakuten_percent"] else None
            except ValueError:
                pct = None
            info = {**row, "percent": pct}
            names = [store] + [a for a in row.get("aliases", "").split("|") if a.strip()]
            for name in names:
                self._by_name[normalize(name)] = info

    def info(self, store_name: str) -> dict | None:
        """The table row for a store (with a parsed 'percent'), or None if not listed."""
        key = normalize(store_name)
        if key in self._by_name:
            return self._by_name[key]
        # Partial match, e.g. "Dick's Sporting Goods - Seller" contains "dickssportinggoods".
        for name, value in self._by_name.items():
            if len(name) >= 4 and (name in key or key in name):
                return value
        return None

    def lookup(self, store_name: str) -> tuple[str | None, float | None]:
        """Return (known store name, Rakuten %) or (None, None) if not in the table."""
        row = self.info(store_name)
        return (row["store"], row["percent"]) if row else (None, None)


def rakuten_check_url(store_name: str) -> str:
    """A search link to confirm the store's current Rakuten rate."""
    return "https://www.google.com/search?q=" + quote_plus(f"Rakuten {store_name} cash back")
