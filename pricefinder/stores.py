"""Always check a few key stores: Amazon, Costco, and the brand's own website.

Google Shopping often leaves these out (Amazon rarely lists there), so we
find their product pages with a Google web search. Web results don't include
prices, so a price is shown only when Google Shopping also listed that store.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from .cashback import normalize
from .match import GENERIC_WORDS, tokens
from .search import SERPER_SEARCH_URL, ProductLink, SearchError, pick_product_link

# Big retailers and marketplaces: never mistaken for "the brand's website".
RETAILERS = {
    "amazon", "ebay", "walmart", "target", "costco", "bestbuy", "dickssportinggoods",
    "kohls", "macys", "nordstrom", "nordstromrack", "zappos", "footlocker", "jdsports",
    "finishline", "academy", "rei", "poshmark", "mercari", "etsy", "aliexpress", "temu",
    "google", "youtube", "reddit", "wikipedia", "facebook", "instagram", "tiktok",
    "pinterest", "x", "twitter", "soccer", "prodirectsport", "goat", "stockx",
    "flightclub", "farfetch", "ssense", "scheels", "sierra", "tjmaxx", "marshalls",
    "rakuten", "slickdeals", "apple-store",
}

FIXED_STORES = [("Amazon", "amazon.com"), ("Costco", "costco.com")]


@dataclass
class StoreCheck:
    name: str          # "Amazon", "Costco", or the brand's site, e.g. "adidas.com"
    domain: str
    link: ProductLink | None
    is_brand: bool = False


def _site_core(url: str) -> tuple[str, str]:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    parts = host.split(".")
    core = parts[-2] if len(parts) >= 2 else host
    return host, normalize(core)


def find_brand_site(query: str, organic: list[dict]) -> StoreCheck | None:
    """Pick the brand's own website from web results for the query.

    A site counts as the brand's when its name matches a search word, e.g.
    "adidas" -> adidas.com, "northface" -> thenorthface.com.
    """
    words = [w for w in tokens(query) if w not in GENERIC_WORDS]
    exact = {normalize(w) for w in words if len(w) >= 3}
    # Brands usually come first: "northface ..." or "north face ..." -> thenorthface.com
    lead = {normalize(w) for w in (words[:1] + ["".join(words[:2])]) if len(w) >= 4}

    sites = []
    for r in organic:
        host, core = _site_core(r.get("link") or "")
        if core and len(core) >= 3 and core not in RETAILERS and (host, core) not in sites:
            sites.append((host, core))
    # First an exact name match (adidas -> adidas.com), then a partial one.
    for is_match in (lambda c: c in exact, lambda c: any(w in c for w in lead)):
        for host, core in sites:
            if is_match(core):
                same_site = [o for o in organic if _site_core(o.get("link") or "")[0] == host]
                link = pick_product_link(query, core, same_site)
                return StoreCheck(host, host, link, is_brand=True)
    return None


def _search(q: str, api_key: str) -> list[dict]:
    try:
        resp = requests.post(
            SERPER_SEARCH_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": q, "gl": "us", "num": 10},
            timeout=20,
        )
    except requests.RequestException as e:
        raise SearchError(f"Could not reach Serper: {e}") from e
    if resp.status_code != 200:
        raise SearchError(f"Serper error {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("organic", [])


def check_store(query: str, name: str, domain: str, api_key: str) -> StoreCheck:
    """Find the product page on one store's site. Uses 1 search credit."""
    organic = _search(f"site:{domain} {query}", api_key)
    core = _site_core("https://" + domain)[1]
    return StoreCheck(name, domain, pick_product_link(query, core, organic))


def check_brand(query: str, api_key: str) -> StoreCheck | None:
    """Find the brand's website and product page. Uses 1 search credit."""
    return find_brand_site(query, _search(f"{query} official site", api_key))
