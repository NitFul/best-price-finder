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


def test_clean_store_name():
    from pricefinder.rakuten import clean_store_name
    assert clean_store_name("eBay - official_shoebacca") == "eBay"
    assert clean_store_name("Pro:Direct Sport US") == "Pro:Direct Sport"
    assert clean_store_name("Nike") == "Nike"


def test_new_store_row_gets_zero_when_not_on_rakuten(monkeypatch):
    from pricefinder import rakuten
    monkeypatch.setattr(rakuten, "lookup_rakuten_rate", lambda *a, **k: None)
    row = rakuten.new_store_row("Goalinn.com", "key")
    assert row["store"] == "Goalinn.com"
    assert row["rakuten_percent"] == "0"
    assert row["notes"] == "Not on Rakuten"
    assert row["last_checked"]


def test_new_store_row_flat_offer_is_zero_percent(monkeypatch):
    from pricefinder import rakuten
    monkeypatch.setattr(rakuten, "lookup_rakuten_rate",
                        lambda *a, **k: rakuten.RakutenRate(None, "$5 cash back offer, not a % rate", "u"))
    row = rakuten.new_store_row("Amazon", "key")
    assert row["rakuten_percent"] == "0" and "$5" in row["notes"]


# ---- Plurals, gender words, "with" features: real "northface" results ----
NORTHFACE = json.loads((Path(__file__).parent / "data" / "northface_borealis.json").read_text())
NF_Q = "northface mens backpacks borealis"


def test_plural_gender_and_with_features():
    assert match_score(NF_Q, "The North Face Borealis Backpack") == 1.0
    assert match_score(NF_Q, "The North Face Unisex Borealis Laptop Backpack") == 1.0
    assert match_score(NF_Q, "Borealis Backpack with Laptop Sleeve, The North Face") == 1.0
    assert match_score(NF_Q, "The North Face Women's Borealis Backpack") == 0.0
    assert match_score(NF_Q, "The North Face Borealis Mini Backpack") == 0.0
    assert match_score("iphone 18 pro", "iPhone 18 Pro Leather Case") == 0.0


def test_northface_search_returns_many_stores():
    ranked = build_options(NF_Q, parse_results(NORTHFACE), CashbackTable([]))
    stores = {o.listing.store for o in ranked.options}
    assert len(ranked.options) >= 10
    assert "The North Face" in stores
    assert not any("mini" in o.listing.title.lower() for o in ranked.options)


# ---- Amazon / Costco / brand site (real web results saved from Serper) ----
from pricefinder.stores import find_brand_site

STORES = json.loads((Path(__file__).parent / "data" / "store_checks.json").read_text())


def test_abbreviation_matches_initials():
    assert match_score(Q, "adidas F50 PRO Firm Ground Soccer Cleats") == 1.0


def test_brand_site_detected_with_product_page():
    adidas = find_brand_site(Q, STORES[Q + " official site"])
    assert adidas.domain == "adidas.com" and adidas.is_brand
    assert adidas.link.is_product_page and adidas.link.url.endswith("JR8953.html")
    nf = find_brand_site(NF_Q, STORES[NF_Q + " official site"])
    assert nf.domain == "thenorthface.com"
    assert "borealis-backpack" in nf.link.url and nf.link.is_product_page


def test_amazon_product_page_skips_other_models():
    found = pick_product_link(NF_Q, "amazon", STORES["site:amazon.com " + NF_Q])
    assert found.is_product_page and "/clp/" in found.url  # not the "Mini" listing


def test_costco_category_page_is_not_a_product():
    found = pick_product_link(NF_Q, "costco", STORES["site:costco.com " + NF_Q])
    assert found is None or not found.is_product_page


def test_kids_versions_hidden_unless_searched():
    assert match_score(Q, "adidas F50 Pro Firm Ground Youth Soccer Cleats") == 0.0
    assert match_score("adidas F50 Pro FG youth cleats", "adidas F50 Pro FG Youth Soccer Cleats") == 1.0


def test_exact_model_beats_longer_model_name():
    organic = [
        {"link": "https://www.adidas.com/us/f50-hyperfast-pro-firm-ground-soccer-cleats/KJ3438.html",
         "title": "White F50 Hyperfast Pro Firm Ground Soccer Cleats"},
        {"link": "https://www.adidas.com/us/f50-pro-firm-ground-soccer-cleats/JR8953.html",
         "title": "adidas F50 PRO Firm Ground Soccer Cleats - Black"},
    ]
    assert pick_product_link(Q, "adidas", organic).url.endswith("JR8953.html")


def test_brand_site_ignores_generic_word_matches():
    organic = [
        {"link": "https://soccerandrugby.com/soccer-shoes/adidas-f50-pro-fg-jh7683.htm", "title": "adidas F50 Pro FG"},
        {"link": "https://www.adidas.com/us/f50-pro-firm-ground-soccer-cleats/JR8953.html",
         "title": "adidas F50 PRO Firm Ground Soccer Cleats"},
    ]
    assert find_brand_site(Q, organic).domain == "adidas.com"
    assert find_brand_site(Q, organic[:1]) is None


# ---- Amazon prices via SerpApi (sample shaped like SerpApi's documented response) ----
from pricefinder.amazon import parse_amazon_results


def test_parse_amazon_results():
    data = {"organic_results": [
        {"asin": "B0AD", "title": "adidas F50 Pro FG Soccer Cleats", "sponsored": True,
         "price": "$150.00", "extracted_price": 150.0, "link": "https://www.amazon.com/sspa/click?x"},
        {"asin": "B0FLJL1CWM", "title": "adidas Mens F50 Pro Firm Ground Soccer Cleats",
         "price": "$129.99", "extracted_price": 129.99, "rating": 4.6, "reviews": 210,
         "link": "https://www.amazon.com/adidas-Mens/dp/B0FLJL1CWM/ref=sr_1_1",
         "link_clean": "https://www.amazon.com/dp/B0FLJL1CWM/"},
        {"asin": "B0NOPRICE", "title": "adidas F50 Pro (currently unavailable)"},
    ]}
    listings = parse_amazon_results(data)
    assert len(listings) == 1  # sponsored and no-price items skipped
    a = listings[0]
    assert a.store == "Amazon" and a.price == 129.99
    assert a.link == "https://www.amazon.com/dp/B0FLJL1CWM/"
    assert a.rating_count == 210


def test_amazon_listing_competes_in_ranking():
    amazon = parse_amazon_results({"organic_results": [
        {"title": "adidas Mens F50 Pro Firm Ground Soccer Cleats", "extracted_price": 129.99,
         "link_clean": "https://www.amazon.com/dp/B0FLJL1CWM/"}]})
    table = CashbackTable([{"store": "Amazon", "aliases": "", "rakuten_percent": "0", "notes": ""}])
    opts = build_options(Q, demo_results() + amazon, table).options
    assert opts[0].listing.store == "Amazon"  # cheapest after cashback


def test_real_amazon_results_brand_added_and_ranked():
    data = json.loads((Path(__file__).parent / "data" / "amazon_f50.json").read_text())
    listings = parse_amazon_results(data)
    assert listings and all(l.store == "Amazon" for l in listings)
    first = next(l for l in listings if "Unisex-Adult F50 Pro" in l.title)
    assert first.title.startswith("adidas ")      # brand added from the brand field
    assert first.shipping == 0.0                  # "FREE delivery"
    assert "/ref=" not in first.link              # clean product link
    opts = build_options(Q, listings, CashbackTable([])).options
    assert opts and opts[0].listing.store == "Amazon"
    assert "women" not in opts[0].listing.title.lower()


def test_open_box_and_like_new_hidden():
    q = "iphone 18 pro"
    assert match_score(q, "Open Box Apple iPhone 18 Pro (A3713) Unlocked - 5G") == 0.0
    assert match_score(q, "Apple iPhone 18 Pro - Like New") == 0.0
    assert match_score(q, "Apple iPhone 18 Pro 256GB") == 1.0


# ---- Costco via Apify (sample shaped like the actor's documented output) ----
from pricefinder.costco import parse_costco_items


def test_parse_costco_items():
    items = [
        {"_operation": "search", "status": "success", "itemNumber": "1",
         "itemName": "AirPods Pro 3", "brand": ["Apple"], "salePrice": 199.99, "listPrice": 249.99,
         "memberOnly": True, "inStock": True, "productUrl": "https://www.costco.com/p/-/airpods/1"},
        {"status": "success", "itemName": "Kirkland Paper Towels", "brand": ["Kirkland Signature"],
         "salePrice": None, "listPrice": 23.99, "inStock": False, "productUrl": "https://www.costco.com/p/2"},
        {"status": "error", "itemName": "Broken", "salePrice": 1},
        {"status": "success", "itemName": "No price item"},
    ]
    listings = parse_costco_items(items)
    assert len(listings) == 2
    a, b = listings
    assert a.store == "Costco" and a.title == "Apple AirPods Pro 3" and a.price == 199.99
    assert a.note == "Costco member price"
    assert b.price == 23.99 and "out of stock" in b.note
    assert b.title.startswith("Kirkland Signature")


def test_real_costco_results_match_airpods():
    items = json.loads((Path(__file__).parent / "data" / "costco_airpods.json").read_text())
    listings = parse_costco_items(items)
    assert listings and all(l.store == "Costco" for l in listings)
    opts = build_options("Apple AirPods Pro 3", listings, CashbackTable([])).options
    assert opts and "AirPods Pro 3" in opts[0].listing.title
    assert opts[0].listing.link.startswith("https://www.costco.com/")
    assert not any("Belkin" in o.listing.title or "AirPods 4" in o.listing.title for o in opts)


def test_overpriced_bundles_dont_hide_real_deals():
    q = "Apple AirPods Pro 3"
    prices = [("Amazon", 149.0), ("Costco", 149.99), ("Best Buy", 179.99), ("FlexShopper", 279.99),
              ("iPromo", 335.0), ("Geek Tech", 345.31), ("VXB.com", 368.95), ("GildedBox", 425.0),
              ("AS2 Electronics", 431.68), ("Bait Shop", 12.0)]
    listings = [Listing(f"Apple AirPods Pro 3", s, p, "x") for s, p in prices]
    ranked = build_options(q, listings, CashbackTable([]))
    stores = [o.listing.store for o in ranked.options]
    assert stores[:2] == ["Amazon", "Costco"]
    assert "Bait Shop" not in stores and ranked.hidden["suspiciously cheap prices"] == 1
