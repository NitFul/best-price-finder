"""Decide how well a listing title matches what the user searched for."""

import re

# Words that usually mean the listing is not a new, complete product
# (used items, or accessories for the product).
UNWANTED_WORDS = {
    "used", "refurbished", "renewed", "pre-owned", "preowned", "open-box",
    "replacement", "laces", "insoles", "case", "cover", "sticker", "skin",
    "protector", "holster", "sleeve", "charger", "cable", "adapter", "mount",
    "stand", "strap", "wallet", "folio", "bumper", "decal", "lens", "tempered",
}

# Words that name a different model of the same product line:
# searching "iPhone 18 Pro" should not return "iPhone 18 Pro Max".
VARIANT_WORDS = {"max", "plus", "mini", "ultra", "lite", "fe"}

# Gender words are often missing from titles ("Unisex" or nothing), so they
# don't count toward the score. A title for the other gender is rejected.
GENDER_WORDS = {
    "men": "m", "mens": "m", "man": "m", "male": "m", "boys": "m",
    "women": "w", "womens": "w", "woman": "w", "female": "w", "ladies": "w", "girls": "w",
}

# Generic words count less than model words: missing "soccer" matters less
# than missing "Pro" (which would mean a different model).
GENERIC_WORDS = {
    "soccer", "football", "cleat", "shoe", "boot", "sneaker", "running",
    "unisex", "the", "and", "for", "with", "new", "apple", "phone",
    "smartphone", "unlocked", "firm", "ground", "black", "white", "size",
}

# Kids' versions are a different product unless the search asks for them.
KIDS_WORDS = {"youth", "kid", "kids", "junior", "toddler", "infant", "baby", "jr"}
GENERIC_WEIGHT = 0.3


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())


def singular(word: str) -> str:
    """'backpacks' -> 'backpack', 'cases' -> 'case'; leaves 'glass', 'pro' alone."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def is_accessory_for(query_words: set[str], title_words: list[str]) -> bool:
    """'Case for iPhone 18 Pro': the searched product comes after 'for'."""
    if "for" in query_words or "for" not in title_words:
        return False
    before = set(title_words[: title_words.index("for")])
    key_words = query_words - GENERIC_WORDS - set(GENDER_WORDS)
    return bool(key_words) and not (key_words & before)


UNWANTED_PHRASES = ("open box", "pre owned", "like new", "for parts", "certified refurbished")


def has_unwanted_word(query_words: set[str], title_words: list[str]) -> bool:
    """True for 'iPhone 18 Pro Case', but not 'Backpack with Laptop Sleeve'."""
    title_text = " ".join(title_words)
    query_text = " ".join(sorted(query_words))
    if any(p in title_text and p not in query_text for p in UNWANTED_PHRASES):
        return True
    after_with = False
    for w in title_words:
        if w == "with":
            after_with = True  # "with ..." describes a feature of the product
        elif not after_with and singular(w) in UNWANTED_WORDS and singular(w) not in query_words:
            return True
    return False


def extra_words(query: str, title: str) -> int:
    """How many model-like words the title has that the search didn't ask for.

    Used to break ties: for "F50 Pro", "F50 Pro" beats "F50 Hyperfast Pro".
    """
    q = {singular(w) for w in tokens(query)}
    joined_q = "".join(tokens(query))
    return sum(
        1 for w in {singular(x) for x in tokens(title)}
        if w not in q and w not in joined_q and w not in GENERIC_WORDS
        and w not in GENDER_WORDS and not w.isdigit() and len(w) > 2
    )


def match_score(query: str, title: str) -> float:
    """Weighted share of the search words found in the title (0.0 to 1.0).

    Returns 0 if the listing looks like a different product: used items,
    accessories, another model (e.g. "Max" when not searched for), or the
    other gender.
    """
    q = {singular(w) for w in tokens(query)}
    if not q:
        return 0.0
    title_words = tokens(title)
    t = {singular(w) for w in title_words}

    if has_unwanted_word(q, title_words):
        return 0.0
    if (VARIANT_WORDS & t) - q:
        return 0.0
    if (KIDS_WORDS & t) and not (KIDS_WORDS & q):
        return 0.0
    if is_accessory_for(q, title_words):
        return 0.0
    q_gender = {GENDER_WORDS[w] for w in q if w in GENDER_WORDS}
    t_gender = {GENDER_WORDS[w] for w in t if w in GENDER_WORDS}
    if q_gender and t_gender and not (q_gender & t_gender) and "unisex" not in t:
        return 0.0

    scored = q - set(GENDER_WORDS)
    if not scored:
        return 1.0

    def weight(w: str) -> float:
        return GENERIC_WEIGHT if w in GENERIC_WORDS else 1.0

    # Also match words written together or apart ("northface" vs "North Face")
    # and abbreviations ("FG" vs "Firm Ground").
    joined_title = "".join(title_words)
    initials = "".join(w[0] for w in title_words)

    def found_in_title(w: str) -> bool:
        if w in t or w.replace("-", "") in joined_title:
            return True
        return 2 <= len(w) <= 4 and w.isalpha() and w in initials

    total = sum(weight(w) for w in scored)
    found = sum(weight(w) for w in scored if found_in_title(w))
    return found / total
