"""Decide how well a listing title matches what the user searched for."""

import re

# Words that usually mean the listing is not a new, complete product
# (used items, or accessories for the product).
UNWANTED_WORDS = {
    "used", "refurbished", "renewed", "pre-owned", "preowned", "open-box",
    "replacement", "laces", "insoles", "case", "cases", "cover", "covers",
    "bag", "sticker", "skin", "skins", "protector", "protectors", "holster",
    "sleeve", "charger", "cable", "adapter", "mount", "stand", "strap",
    "wallet", "folio", "bumper", "decal", "lens", "tempered",
}

# Words that name a different model of the same product line:
# searching "iPhone 18 Pro" should not return "iPhone 18 Pro Max".
VARIANT_WORDS = {"max", "plus", "mini", "ultra", "lite", "fe"}

# Generic words count less than model words: missing "soccer" matters less
# than missing "Pro" (which would mean a different model).
GENERIC_WORDS = {
    "soccer", "football", "cleats", "cleat", "shoes", "shoe", "boots", "boot",
    "sneakers", "sneaker", "running", "men", "mens", "women", "womens", "kids",
    "youth", "unisex", "the", "and", "for", "with", "new", "apple", "phone",
    "smartphone", "unlocked",
}
GENERIC_WEIGHT = 0.3


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())


def is_accessory_for(query_words: set[str], title_words: list[str]) -> bool:
    """'Case for iPhone 18 Pro': the searched product comes after 'for'."""
    if "for" in query_words or "for" not in title_words:
        return False
    before = set(title_words[: title_words.index("for")])
    key_words = query_words - GENERIC_WORDS
    return bool(key_words) and not (key_words & before)


def match_score(query: str, title: str) -> float:
    """Weighted share of the search words found in the title (0.0 to 1.0).

    Returns 0 if the listing looks like a different product: used items,
    accessories, or another model (e.g. "Max" when not searched for).
    """
    q = set(tokens(query))
    if not q:
        return 0.0
    title_words = tokens(title)
    t = set(title_words)
    if (UNWANTED_WORDS & t) - q:
        return 0.0
    if (VARIANT_WORDS & t) - q:
        return 0.0
    if is_accessory_for(q, title_words):
        return 0.0

    def weight(w: str) -> float:
        return GENERIC_WEIGHT if w in GENERIC_WORDS else 1.0

    # Also match words split differently, e.g. "F50" vs "F 50".
    joined_title = "".join(title_words)
    total = sum(weight(w) for w in q)
    found = sum(weight(w) for w in q if w in t or w.replace("-", "") in joined_title)
    return found / total
