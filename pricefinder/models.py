from dataclasses import dataclass


@dataclass
class Listing:
    """One product offer from one store."""

    title: str
    store: str
    price: float
    link: str
    shipping: float | None = None  # None = unknown, 0 = free
    image_url: str | None = None
    rating: float | None = None
    rating_count: int | None = None
    monthly: bool = False  # True = price is a monthly payment ("$66.66/mo"), not the full price
    note: str = ""  # shown with the listing, e.g. "Costco member price"


@dataclass
class Option:
    """A listing with cashback applied, ready to show the user."""

    listing: Listing
    match_score: float
    cashback_percent: float | None  # None = no rate on file for this store
    cashback_amount: float
    effective_price: float
