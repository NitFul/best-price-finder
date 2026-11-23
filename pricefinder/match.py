"""Decide how well a listing title matches what the user searched for."""

import re

# Words that usually mean the listing is not a new, complete product.
UNWANTED_WORDS = {
    "used", "refurbished", "renewed", "pre-owned", "preowned", "open-box",
    "replacement", "laces", "insoles", "case", "cover", "bag", "sticker",
}


# Generic words count less than model words: missing "soccer" matters less
# than missing "Pro" (which would mean a different model).
GENERIC_WORDS = {
    "soccer", "football", "cleats", "cleat", "shoes", "shoe", "boots", "boot",
    "sneakers", "sneaker", "running", "men", "mens", "women", "womens", "kids",
    "youth", "unisex", "the", "and", "for", "with", "new",
}
GENERIC_WEIGHT = 0.3


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())


def match_score(query: str, title: str) -> float:
    """Weighted share of the search words found in the title (0.0 to 1.0).

    Returns 0 if the title has an unwanted word (e.g. "used") that the
    search did not include.
    """
    q = set(tokens(query))
    if not q:
        return 0.0
    t = set(tokens(title))
    # Also match words split differently, e.g. "F50" vs "F 50".
    joined_title = "".join(tokens(title))
    if (UNWANTED_WORDS & t) - q:
        return 0.0
    def weight(w: str) -> float:
        return GENERIC_WEIGHT if w in GENERIC_WORDS else 1.0

    total = sum(weight(w) for w in q)
    found = sum(weight(w) for w in q if w in t or w.replace("-", "") in joined_title)
    return found / total
