"""Amazon prices from SerpApi's Amazon Search API (free plan: 250 searches/month).

Amazon rarely appears in Google Shopping, so this adds Amazon listings with
real prices to the results. Needs SERPAPI_KEY (free at https://serpapi.com).
"""

import requests

from .models import Listing
from .search import SearchError, parse_money

SERPAPI_URL = "https://serpapi.com/search.json"


def parse_amazon_results(data: dict) -> list[Listing]:
    listings = []
    for item in data.get("organic_results", []):
        if item.get("sponsored"):
            continue  # ads; the organic results are the real matches
        price = item.get("extracted_price")
        if price is None:
            price = parse_money(item.get("price") if isinstance(item.get("price"), str) else None)
        if not price or not item.get("title"):
            continue
        listings.append(
            Listing(
                title=item["title"],
                store="Amazon",
                price=float(price),
                link=item.get("link_clean") or item.get("link") or "",
                image_url=item.get("thumbnail"),
                rating=item.get("rating"),
                rating_count=item.get("reviews"),
            )
        )
    return listings


def search_amazon(query: str, api_key: str) -> list[Listing]:
    """Search Amazon.com. Uses 1 SerpApi search."""
    if not api_key:
        raise SearchError("No SerpApi key. Add SERPAPI_KEY to your .env file.")
    try:
        resp = requests.get(
            SERPAPI_URL,
            params={"engine": "amazon", "k": query, "amazon_domain": "amazon.com", "api_key": api_key},
            timeout=30,
        )
    except requests.RequestException as e:
        raise SearchError(f"Could not reach SerpApi: {e}") from e
    if resp.status_code == 401:
        raise SearchError("SerpApi rejected the key. Check SERPAPI_KEY in .env.")
    try:
        data = resp.json()
    except ValueError:
        raise SearchError(f"SerpApi error {resp.status_code}")
    if resp.status_code != 200 or data.get("error"):
        if "hasn't returned any results" in str(data.get("error", "")):
            return []
        raise SearchError(f"SerpApi: {data.get('error') or resp.status_code}")
    return parse_amazon_results(data)
