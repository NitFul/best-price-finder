from pricefinder.cashback import CashbackTable, normalize
from pricefinder.limits import DailyLimiter
from pricefinder.match import match_score
from pricefinder.models import Listing
from pricefinder.ranking import build_options
from pricefinder.search import (
    clean_url,
    demo_results,
    parse_money,
    parse_shipping,
    parse_results,
    pick_product_link,
    store_matches_url,
)

Q = "adidas F50 Pro FG Soccer Cleats"


def test_parse_money_and_shipping():
    assert parse_money("$1,219.99") == 1219.99
    assert parse_money(None) is None
    assert parse_shipping("Free delivery") == 0
    assert parse_shipping("$5.99 delivery") == 5.99
    assert parse_shipping(None) is None


def test_match_score():
    assert match_score(Q, "adidas F50 Pro FG Soccer Cleats - Men's") == 1.0
    assert match_score(Q, "adidas F50 League FG Soccer Cleats") < 0.85      # missing "Pro"
    assert match_score(Q, "adidas F50 Pro Firm Ground Cleats FG") >= 0.85   # only missing "soccer"
    assert match_score(Q, "adidas F50 Pro FG Soccer Cleats Used") == 0.0


def test_store_lookup():
    table = CashbackTable([
        {"store": "Dick's Sporting Goods", "aliases": "dicks", "rakuten_percent": "9", "notes": ""},
        {"store": "Amazon", "aliases": "amazon.com", "rakuten_percent": "", "notes": ""},
    ])
    assert normalize("Amazon.com") == "amazon"
    assert table.lookup("Dick's Sporting Goods") == ("Dick's Sporting Goods", 9.0)
    assert table.lookup("DICKS") == ("Dick's Sporting Goods", 9.0)
    assert table.lookup("Amazon.com") == ("Amazon", None)
    assert table.lookup("Some Random Shop") == (None, None)


def test_ranking_applies_cashback_and_shipping():
    table = CashbackTable([
        {"store": "Dick's Sporting Goods", "aliases": "", "rakuten_percent": "9", "notes": ""},
    ])
    listings = [
        Listing(Q, "Dick's Sporting Goods", 220.0, "x", shipping=0),
        Listing(Q, "Amazon.com", 205.0, "y", shipping=0),
        Listing(Q, "Shop C", 199.0, "z", shipping=10),
    ]
    opts = build_options(Q, listings, table).options
    assert [o.listing.store for o in opts] == ["Dick's Sporting Goods", "Amazon.com", "Shop C"]
    assert opts[0].effective_price == 200.2  # 220 - 9%
    assert opts[2].effective_price == 209.0  # 199 + 10 shipping


def test_store_matches_url():
    assert store_matches_url("DICK'S Sporting Goods", "https://www.dickssportinggoods.com/p/x")
    assert store_matches_url("Pro:Direct Sport US", "https://www.prodirectsport.us/collections/x")
    assert store_matches_url("Amazon.com - Seller", "https://www.amazon.com/dp/B0")
    assert not store_matches_url("DICK'S Sporting Goods", "https://www.instacart.com/products/1")


def test_pick_product_link_prefers_exact_product_page():
    organic = [
        {"link": "https://www.dickssportinggoods.com/f/adidas-f50-soccer-cleats?srsltid=abc"},
        {"link": "https://www.dickssportinggoods.com/p/adidas-f50-elite-fg-soccer-cleats-25x/25x"},
        {"link": "https://www.dickssportinggoods.com/p/adidas-f50-pro-fg-soccer-cleats-25y/25y?srsltid=abc"},
        {"link": "https://www.instacart.com/products/120430249"},
    ]
    found = pick_product_link(Q, "DICK'S Sporting Goods", organic)
    assert found.is_product_page
    assert found.url == "https://www.dickssportinggoods.com/p/adidas-f50-pro-fg-soccer-cleats-25y/25y"


def test_clean_url_strips_tracking():
    assert clean_url("https://www.ebay.com/itm/188?_trkparms=x&_trksid=y&itmmeta=z") == "https://www.ebay.com/itm/188"
    assert clean_url("https://shop.com/p/1?color=red&utm_source=g") == "https://shop.com/p/1?color=red"


def test_pick_product_link_category_only_and_none():
    organic = [{"link": "https://www.prodirectsport.us/collections/adidas-f50-soccer-cleats"}]
    found = pick_product_link(Q, "Pro:Direct Sport US", organic)
    assert found and not found.is_product_page
    assert pick_product_link(Q, "Some Shop", organic) is None


def test_daily_limiter():
    lim = DailyLimiter(2)
    assert lim.try_use() and lim.try_use()
    assert not lim.try_use()
    assert lim.remaining == 0


def test_demo_data_filters_wrong_items():
    opts = build_options(Q, demo_results(), CashbackTable([])).options
    stores = {o.listing.store for o in opts}
    assert "eBay" not in stores      # used listing filtered out
    assert "Walmart" not in stores   # different model (League) filtered out


# ---- Electronics: real "iphone 18 pro" results saved from Serper ----
import json
from pathlib import Path

IPHONE = json.loads((Path(__file__).parent / "data" / "iphone_18_pro.json").read_text())


def test_accessories_and_other_models_rejected():
    q = "iphone 18 pro"
    assert match_score(q, "Apple iPhone 18 Pro 256GB Silver") == 1.0
    assert match_score(q, "Clear Case for iPhone 18 Pro with MagSafe") == 0.0
    assert match_score(q, "Spigen Ultra Hybrid iPhone 18 Pro Cover") == 0.0
    assert match_score(q, "Screen Protector for Apple iPhone 18 Pro") == 0.0
    assert match_score(q, "Apple iPhone 18 Pro Max") == 0.0
    assert match_score("iphone 18 pro max", "Apple iPhone 18 Pro Max") == 1.0


def test_monthly_price_detected():
    listings = parse_results(IPHONE)
    verizon = [l for l in listings if l.store == "Verizon"]
    assert verizon and all(l.monthly for l in verizon)


def test_iphone_results_are_real_full_price_phones():
    ranked = build_options("iphone 18 pro", parse_results(IPHONE), CashbackTable([]))
    stores = {o.listing.store for o in ranked.options}
    titles = " ".join(o.listing.title.lower() for o in ranked.options)
    assert ranked.options, "expected some results"
    assert "Verizon" not in stores                  # monthly plan
    assert "elettrodomestici.shop" not in stores    # $12 bait price + carrier-locked
    assert "max" not in titles                      # different model
    assert all(o.listing.price > 500 for o in ranked.options)
    assert ranked.hidden["monthly payment plans"] > 0


# ---- Rakuten rates from real Google search results (saved from Serper) ----
from pricefinder.rakuten import pick_rate

RAKUTEN = json.loads((Path(__file__).parent / "data" / "rakuten_search.json").read_text())


def _rate(store, *aliases):
    return pick_rate([store, *aliases], RAKUTEN[store]["organic"])


def test_rakuten_percent_rate_from_store_page():
    r = _rate("Dick's Sporting Goods", "dicks")
    assert r.percent == 2.0
    assert r.source == "https://www.rakuten.com/shop/dickssportinggoods"


def test_rakuten_title_beats_snippet_and_ignores_referral_pages():
    # Nike: /shop title has no %, its snippet says 6%; /store title says 4%.
    # Titles are trusted first; the refer-a-friend page is ignored.
    assert _rate("Nike").percent == 4.0


def test_rakuten_no_cashback_and_flat_offer():
    assert _rate("Walmart").percent == 0.0
    amazon = _rate("Amazon")
    assert amazon.percent is None and "$5" in amazon.note


def test_rakuten_ignores_other_stores_pages():
    assert pick_rate(["Target"], RAKUTEN["Nike"]["organic"]) is None
