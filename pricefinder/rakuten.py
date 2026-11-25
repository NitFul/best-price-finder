"""Look up a store's Rakuten cash back rate from Google search results.

Rakuten has no free public API and blocks automated page reads, but Google's
results for Rakuten's store pages show the rate in the title or snippet, e.g.
"Dick's Sporting Goods Coupons, Promo Codes & 2% Cash Back". We search with
Serper (1 credit per store) and read the rate from those results.
"""

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

import requests

from .cashback import normalize
from .search import SERPER_SEARCH_URL, SearchError

PERCENT_RE = re.compile(r"(up\s+to\s+)?(\d+(?:\.\d+)?)\s*%\s*cash\s*back", re.I)
FLAT_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*cash\s*back", re.I)
NO_CASHBACK_RE = re.compile(r"\bno\s+cash\s*back\b", re.I)
# Rakuten's own store pages: rakuten.com/shop/<store> or rakuten.com/store/<store>
STORE_PAGE_RE = re.compile(r"^/(shop|store)/([^/]+)/?$", re.I)


@dataclass
class RakutenRate:
    percent: float | None  # None = no % rate found (e.g. only a flat $ offer)
    note: str
    source: str  # the Rakuten page the rate came from


def _slug_matches(slug: str, names: list[str]) -> bool:
    s = normalize(slug)
    for name in names:
        n = normalize(name)
        if len(n) >= 3 and len(s) >= 3 and (s in n or n in s):
            return True
    return False


def pick_rate(names: list[str], organic: list[dict]) -> RakutenRate | None:
    """Find the rate in search results, trusting Rakuten store pages only."""
    pages = []
    for r in organic:
        url = r.get("link") or ""
        parts = urlparse(url)
        if not parts.netloc.lower().endswith("rakuten.com") or "ref_id" in parts.query:
            continue  # not Rakuten, or a refer-a-friend page with a special rate
        m = STORE_PAGE_RE.match(parts.path)
        if m and _slug_matches(m.group(2), names):
            # /shop/ is Rakuten's main store page, so trust it first.
            pages.append((0 if m.group(1).lower() == "shop" else 1, r))
    pages = [r for _, r in sorted(pages, key=lambda p: p[0])]

    # Page titles are more reliable than snippets, so check all titles first.
    for field in ("title", "snippet"):
        for r in pages:
            text = r.get(field) or ""
            if NO_CASHBACK_RE.search(text):
                return RakutenRate(0.0, "No cash back right now", r["link"])
            m = PERCENT_RE.search(text)
            if m:
                note = "Up to this rate (varies by category)" if m.group(1) else ""
                return RakutenRate(float(m.group(2)), note, r["link"])
    for field in ("title", "snippet"):
        for r in pages:
            m = FLAT_RE.search(r.get(field) or "")
            if m:
                return RakutenRate(None, f"${m.group(1)} cash back offer, not a % rate", r["link"])
    return None


def lookup_rakuten_rate(store: str, aliases: list[str], api_key: str) -> RakutenRate | None:
    """Search Google (via Serper) for the store's Rakuten rate. Uses 1 credit."""
    if not api_key:
        raise SearchError("No Serper API key set.")
    try:
        resp = requests.post(
            SERPER_SEARCH_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": f"site:rakuten.com {store} cash back", "gl": "us", "num": 10},
            timeout=20,
        )
    except requests.RequestException as e:
        raise SearchError(f"Could not reach Serper: {e}") from e
    if resp.status_code != 200:
        raise SearchError(f"Serper error {resp.status_code}: {resp.text[:200]}")
    return pick_rate([store, *aliases], resp.json().get("organic", []))


def update_row(row: dict, api_key: str) -> str:
    """Refresh one CSV row in place. Returns a short summary of what happened."""
    aliases = [a for a in row.get("aliases", "").split("|") if a.strip()]
    rate = lookup_rakuten_rate(row["store"], aliases, api_key)
    row["last_checked"] = date.today().isoformat()
    if rate is None:
        row["rakuten_percent"] = ""
        row["notes"] = "Not found on Rakuten"
        row["source"] = ""
        return "not found"
    row["rakuten_percent"] = "" if rate.percent is None else f"{rate.percent:g}"
    row["notes"] = rate.note
    row["source"] = rate.source
    return f"{rate.percent:g}%" if rate.percent is not None else rate.note
