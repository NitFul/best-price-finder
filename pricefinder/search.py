"""Get shopping results from Serper.dev (Google Shopping data)."""

import json
import re
from pathlib import Path

import requests

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


def demo_results() -> list[Listing]:
    """Made-up sample data so the app can be tried before you have a key."""
    return parse_results(json.loads(DEMO_FILE.read_text(encoding="utf-8")))
