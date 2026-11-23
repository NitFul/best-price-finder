from pricefinder.cashback import CashbackTable, normalize
from pricefinder.limits import DailyLimiter
from pricefinder.match import match_score
from pricefinder.models import Listing
from pricefinder.ranking import build_options
from pricefinder.search import demo_results, parse_money, parse_shipping

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
    opts = build_options(Q, listings, table)
    assert [o.listing.store for o in opts] == ["Dick's Sporting Goods", "Amazon.com", "Shop C"]
    assert opts[0].effective_price == 200.2  # 220 - 9%
    assert opts[2].effective_price == 209.0  # 199 + 10 shipping


def test_daily_limiter():
    lim = DailyLimiter(2)
    assert lim.try_use() and lim.try_use()
    assert not lim.try_use()
    assert lim.remaining == 0


def test_demo_data_filters_wrong_items():
    opts = build_options(Q, demo_results(), CashbackTable([]))
    stores = {o.listing.store for o in opts}
    assert "eBay" not in stores      # used listing filtered out
    assert "Walmart" not in stores   # different model (League) filtered out
