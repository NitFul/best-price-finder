"""Costco prices via an Apify scraper (sian.agency/costco-data-scraper).

Costco isn't in Google Shopping and has no public API, so this runs a
third-party Apify actor that reads costco.com search results. Note: this
scrapes Costco's site, which Costco's terms don't allow; it was added at the
owner's request. Runs take about 1-2 minutes, so they are started in the
background and checked until done.

Needs APIFY_TOKEN (https://console.apify.com/settings/integrations).
Cost: about $0.90 per 1,000 results (~$0.02 per search), within Apify's
free monthly credit.
"""

import requests

from .models import Listing
from .search import SearchError

API = "https://api.apify.com/v2"
ACTOR = "sian.agency~costco-data-scraper"
MAX_CHARGE_PER_RUN_USD = 0.10  # safety cap per search
RUN_TIMEOUT_SECONDS = 240
DONE_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get(path: str, token: str, **params) -> dict | list:
    try:
        resp = requests.get(f"{API}{path}", headers=_headers(token), params=params, timeout=30)
    except requests.RequestException as e:
        raise SearchError(f"Could not reach Apify: {e}") from e
    if resp.status_code == 401:
        raise SearchError("Apify rejected the token. Check APIFY_TOKEN.")
    if resp.status_code != 200:
        raise SearchError(f"Apify error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def start_costco_search(query: str, token: str) -> dict:
    """Start a Costco search run. Returns {"run_id", "dataset_id", "status"}."""
    if not token:
        raise SearchError("No Apify token. Add APIFY_TOKEN to your .env file.")
    try:
        resp = requests.post(
            f"{API}/acts/{ACTOR}/runs",
            headers=_headers(token),
            params={"timeout": RUN_TIMEOUT_SECONDS, "maxTotalChargeUsd": MAX_CHARGE_PER_RUN_USD},
            json={"operation": "search", "query": query, "country": "US", "maxPages": 1},
            timeout=30,
        )
    except requests.RequestException as e:
        raise SearchError(f"Could not reach Apify: {e}") from e
    if resp.status_code == 401:
        raise SearchError("Apify rejected the token. Check APIFY_TOKEN.")
    if resp.status_code not in (200, 201):
        raise SearchError(f"Apify error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()["data"]
    return {"run_id": data["id"], "dataset_id": data["defaultDatasetId"], "status": data["status"]}


def run_status(run_id: str, token: str) -> str:
    """READY, RUNNING, SUCCEEDED, FAILED, ABORTED or TIMED-OUT."""
    return _get(f"/actor-runs/{run_id}", token)["data"]["status"]


def parse_costco_items(items: list[dict]) -> list[Listing]:
    listings = []
    for item in items:
        if item.get("status") not in (None, "success"):
            continue
        title = item.get("itemName") or ""
        price = item.get("salePrice") or item.get("listPrice")
        if not title or not price:
            continue
        brand = item.get("brand")
        brand = brand[0] if isinstance(brand, list) and brand else (brand or "")
        if brand and brand.lower() not in title.lower():
            title = f"{brand} {title}"
        notes = []
        if item.get("memberOnly"):
            notes.append("Costco member price")
        if item.get("inStock") is False:
            notes.append("out of stock online")
        listings.append(
            Listing(
                title=title,
                store="Costco",
                price=float(price),
                link=item.get("productUrl") or "",
                image_url=item.get("image"),
                rating=item.get("rating") or None,
                rating_count=item.get("reviewCount") or None,
                note=", ".join(notes),
            )
        )
    return listings


def fetch_costco_listings(dataset_id: str, token: str) -> list[Listing]:
    items = _get(f"/datasets/{dataset_id}/items", token, clean="true", limit=100)
    return parse_costco_items(items if isinstance(items, list) else [])


def check_apify_token(token: str) -> tuple[bool, str]:
    """Validate the token and show this month's usage. Free; uses no credit."""
    if not token:
        return False, "APIFY_TOKEN is not set"
    try:
        user = _get("/users/me", token)["data"]
    except SearchError as e:
        return False, str(e)
    msg = f"signed in as {user.get('username', '?')}"
    try:
        limits = _get("/users/me/limits", token)["data"]
        used = limits.get("current", {}).get("monthlyUsageUsd")
        cap = limits.get("limits", {}).get("maxMonthlyUsageUsd")
        if used is not None and cap:
            msg += f", ${used:.2f} of ${cap:.2f} used this month"
    except (SearchError, KeyError, TypeError):
        pass
    return True, msg
