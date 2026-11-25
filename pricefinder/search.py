"""Get shopping results from Serper.dev (Google Shopping data)."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

import requests

from .cashback import normalize
from .match import match_score
from .models import Listing

SERPER_SHOPPING_URL = "https://google.serper.dev/shopping"
DEMO_FILE = Path(__file__).resolve().parent.parent / "sample_data" / "demo_shopping.json"


class SearchError(Exception):
    pass


def parse_money(text: str | None) -> float | None:
    """'$1,219.99' -> 1219.99. Returns None if no number is found."""
    if not text:
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", text)
    return float(m.group(1).replace(",", "")) if m else None


def parse_shipping(delivery: str | None) -> float | None:
    """'Free delivery' -> 0, '$5.99 delivery' -> 5.99, missing -> None (unknown)."""
    if not delivery:
        return None
    if "free" in delivery.lower():
        return 0.0
    return parse_money(delivery)


MONTHLY_PRICE = re.compile(r"/\s*mo\b|/\s*month|per\s+month|monthly", re.I)


def parse_results(data: dict) -> list[Listing]:
    listings = []
    for item in data.get("shopping", []):
        price = parse_money(item.get("price"))
        if price is None or not item.get("title"):
            continue
        listings.append(
            Listing(
                title=item["title"],
                store=item.get("source") or "Unknown store",
                price=price,
                monthly=bool(MONTHLY_PRICE.search(item.get("price") or "")),
                link=item.get("link") or "",
                shipping=parse_shipping(item.get("delivery")),
                image_url=item.get("imageUrl"),
                rating=item.get("rating"),
                rating_count=item.get("ratingCount"),
            )
        )
    return listings


def search_shopping(query: str, api_key: str, country: str = "us", num: int = 40) -> list[Listing]:
    """Search Google Shopping via Serper. Each call uses 1 free credit."""
    if not api_key:
        raise SearchError("No Serper API key. Add SERPER_API_KEY to your .env file.")
    try:
        resp = requests.post(
            SERPER_SHOPPING_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "gl": country, "num": num},
            timeout=20,
        )
    except requests.RequestException as e:
        raise SearchError(f"Could not reach Serper: {e}") from e
    if resp.status_code in (401, 403):
        raise SearchError("Serper rejected the API key. Check SERPER_API_KEY in .env.")
    if resp.status_code != 200:
        raise SearchError(f"Serper error {resp.status_code}: {resp.text[:200]}")
    return parse_results(resp.json())


SERPER_SEARCH_URL = "https://google.serper.dev/search"

# URL patterns that usually mean a single product page, or a list of products.
PRODUCT_PATH = re.compile(r"/(p|dp|ip|itm|product|products|prd|pd)/|/product[-_]", re.I)
CATEGORY_PATH = re.compile(r"/(c|f|collections|category|categories|search|s|browse|shop)/?($|[?/])", re.I)


@dataclass
class ProductLink:
    url: str
    is_product_page: bool  # False = best we found was a category/store page


def store_matches_url(store: str, url: str) -> bool:
    """True if the URL's website looks like it belongs to the store name."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    parts = host.split(".")
    core = normalize(parts[-2] if len(parts) >= 2 else host)
    key = normalize(store)
    return len(core) >= 3 and (core in key or key in core)


TRACKING_PARAMS = {"srsltid", "_trkparms", "_trksid", "itmprp", "itmmeta", "ref", "ref_", "gclid", "fbclid"}


def clean_url(url: str) -> str:
    """Drop tracking parameters (Google, eBay, utm_*) from a store URL."""
    parts = urlparse(url)
    query = [
        (k, v) for k, v in parse_qsl(parts.query)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    return urlunparse(parts._replace(query=urlencode(query)))


def pick_product_link(title: str, store: str, organic: list[dict]) -> ProductLink | None:
    """Choose the best result on the store's own site, preferring product pages."""
    best, best_score = None, -1.0
    for r in organic:
        url = r.get("link") or ""
        if not url or not store_matches_url(store, url):
            continue
        path = urlparse(url).path
        is_product = bool(PRODUCT_PATH.search(path)) and not CATEGORY_PATH.search(path)
        text = f"{r.get('title', '')} {path.replace('-', ' ').replace('/', ' ')}"
        score = match_score(title, text) + (0.5 if is_product else 0)
        if score > best_score:
            best, best_score = ProductLink(clean_url(url), is_product), score
    return best


def find_product_link(title: str, store: str, api_key: str, country: str = "us") -> ProductLink | None:
    """Look up the store's own page for this product. Uses 1 Serper credit."""
    try:
        resp = requests.post(
            SERPER_SEARCH_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": f"{title} {store}", "gl": country, "num": 10},
            timeout=20,
        )
    except requests.RequestException as e:
        raise SearchError(f"Could not reach Serper: {e}") from e
    if resp.status_code != 200:
        raise SearchError(f"Serper error {resp.status_code}: {resp.text[:200]}")
    return pick_product_link(title, store, resp.json().get("organic", []))


def google_search_url(title: str, store: str) -> str:
    """Free fallback: a Google search for this product at this store."""
    return "https://www.google.com/search?q=" + quote_plus(f"{title} {store}")


def demo_results() -> list[Listing]:
    """Made-up sample data so the app can be tried before you have a key."""
    return parse_results(json.loads(DEMO_FILE.read_text(encoding="utf-8")))
