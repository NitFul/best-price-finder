"""Combine listings with cashback and rank by effective price."""

from .cashback import CashbackTable
from .match import match_score
from .models import Listing, Option


def build_options(
    query: str,
    listings: list[Listing],
    cashback: CashbackTable,
    min_match: float = 0.85,
    best_per_store: bool = True,
) -> list[Option]:
    options = []
    for listing in listings:
        score = match_score(query, listing.title)
        if score < min_match:
            continue
        _, pct = cashback.lookup(listing.store)
        # Cashback is paid on the item price, not on shipping.
        cb_amount = round(listing.price * pct / 100, 2) if pct else 0.0
        effective = round(listing.price + (listing.shipping or 0) - cb_amount, 2)
        options.append(Option(listing, score, pct, cb_amount, effective))

    options.sort(key=lambda o: (o.effective_price, -o.match_score))

    if best_per_store:
        seen, unique = set(), []
        for o in options:
            key = o.listing.store.lower()
            if key not in seen:
                seen.add(key)
                unique.append(o)
        options = unique
    return options
