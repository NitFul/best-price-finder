"""Filter listings, apply cashback, and rank by effective price."""

import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import median

from .cashback import CashbackTable
from .match import match_score, tokens
from .models import Listing, Option

# Phones sold through these are tied to a carrier or a plan.
CARRIERS = re.compile(
    r"\b(verizon|at&t|att|t-mobile|tmobile|sprint|visible|mint mobile|cricket|"
    r"boost mobile|metro by t-mobile|metropcs|xfinity|spectrum mobile|us cellular|"
    r"straight talk|tracfone|total wireless|google fi|h2o wireless|ultra mobile|"
    r"red pocket|consumer cellular|lycamobile|tello|us mobile|simple mobile|"
    r"page plus|net10|walmart family mobile|good2go|reach mobile)\b",
    re.I,
)

# A listing below this share of the typical price is likely an accessory,
# a part, or a fake "bait" price.
SUSPICIOUS_PRICE_RATIO = 0.4


@dataclass
class Ranked:
    options: list[Option]
    hidden: Counter = field(default_factory=Counter)  # reason -> number of listings hidden


def is_carrier_deal(listing: Listing, query: str) -> bool:
    if CARRIERS.search(query):
        return False  # the user asked for a carrier
    return bool(CARRIERS.search(listing.title) or CARRIERS.search(listing.store))


def build_options(
    query: str,
    listings: list[Listing],
    cashback: CashbackTable,
    min_match: float = 0.85,
    best_per_store: bool = True,
    hide_carrier_deals: bool = True,
    hide_suspicious_prices: bool = True,
) -> Ranked:
    hidden = Counter()
    kept: list[tuple[Listing, float]] = []
    for listing in listings:
        score = match_score(query, listing.title)
        if score < min_match:
            hidden["different product or accessory"] += 1
        elif listing.monthly:
            hidden["monthly payment plans"] += 1
        elif hide_carrier_deals and is_carrier_deal(listing, query):
            hidden["carrier-locked / plan deals"] += 1
        else:
            kept.append((listing, score))

    if hide_suspicious_prices and len(kept) >= 4:
        floor = median(l.price for l, _ in kept) * SUSPICIOUS_PRICE_RATIO
        too_cheap = [(l, s) for l, s in kept if l.price < floor]
        hidden["suspiciously cheap prices"] += len(too_cheap)
        kept = [(l, s) for l, s in kept if l.price >= floor]

    options = []
    for listing, score in kept:
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
    return Ranked(options, +hidden)
