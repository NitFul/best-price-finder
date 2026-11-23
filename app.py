"""Best Price Finder - run with:  streamlit run app.py"""

import streamlit as st

from pricefinder.cashback import CashbackTable, load_rows, rakuten_check_url, save_rows
from pricefinder.config import get_bool, get_int, get_setting
from pricefinder.limits import DailyLimiter
from pricefinder.ranking import build_options
from pricefinder.search import SearchError, demo_results, search_shopping

st.set_page_config(page_title="Best Price Finder", page_icon="🏷️", layout="centered")

API_KEY = get_setting("SERPER_API_KEY")
# Only turn this on for your own computer (in .env). Keep it off on the public site.
ALLOW_RATE_EDITING = get_bool("ALLOW_RATE_EDITING", False)
DAILY_SEARCH_LIMIT = get_int("DAILY_SEARCH_LIMIT", 60)
SESSION_SEARCH_LIMIT = get_int("SESSION_SEARCH_LIMIT", 10)
MAX_QUERY_LENGTH = 120


@st.cache_resource
def daily_limiter() -> DailyLimiter:
    # One shared counter for every visitor of the site.
    return DailyLimiter(DAILY_SEARCH_LIMIT)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=500)
def cached_search(query: str):
    # Only runs on a cache miss, so repeat searches within an hour are free
    # and don't count toward the daily limit.
    if not daily_limiter().try_use():
        raise SearchError("The site reached today's search limit. Please try again tomorrow.")
    return search_shopping(query, API_KEY)


# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")
    demo = st.toggle(
        "Demo mode (made-up data)",
        value=not API_KEY,
        help="Try the app without an API key. Prices are not real.",
    )
    if not API_KEY:
        st.warning("No SERPER_API_KEY is set. Only demo mode works.")
    min_match = st.slider(
        "How closely titles must match", 0.5, 1.0, 0.85, 0.05,
        help="1.0 = every search word must appear in the listing title.",
    )
    best_per_store = st.checkbox("Show only the best offer per store", value=True)

st.title("🏷️ Best Price Finder")
tab_search, tab_rates = st.tabs(["Search", "Cashback rates"])

# ---------- Search tab ----------
with tab_search:
    with st.form("search"):
        query = st.text_input(
            "Item", placeholder="adidas F50 Pro FG Soccer Cleats", max_chars=MAX_QUERY_LENGTH
        )
        submitted = st.form_submit_button("Find best price", type="primary")

    if submitted and query.strip():
        q = " ".join(query.split())[:MAX_QUERY_LENGTH]
        used = st.session_state.get("searches_used", 0)
        try:
            if demo:
                listings = demo_results()
            elif not API_KEY:
                st.error("Search isn't set up yet. Turn on demo mode to try the app.")
                st.stop()
            elif used >= SESSION_SEARCH_LIMIT:
                st.error(
                    f"You've reached the limit of {SESSION_SEARCH_LIMIT} searches per visit. "
                    "Please come back later."
                )
                st.stop()
            else:
                with st.spinner("Searching stores..."):
                    listings = cached_search(q)
                st.session_state["searches_used"] = used + 1
        except SearchError as e:
            st.error(str(e))
            st.stop()

        if demo:
            st.info("Demo mode: these listings and prices are made up.")

        table = CashbackTable(load_rows())
        options = build_options(q, listings, table, min_match, best_per_store)

        if not options:
            st.warning(
                f"Found {len(listings)} listings, but none matched closely enough. "
                "Try lowering the match setting in the sidebar."
            )
        else:
            st.caption(f"{len(options)} options from {len(listings)} listings, cheapest first after cashback.")

        for i, o in enumerate(options, 1):
            L = o.listing
            with st.container(border=True):
                left, right = st.columns([3, 1])
                with left:
                    st.markdown(f"**Option {i}: {L.store}**")
                    st.write(L.title)
                    if o.cashback_percent:
                        st.success(
                            f"Activate Rakuten first: {o.cashback_percent:g}% cash back "
                            f"(about ${o.cashback_amount:,.2f})"
                        )
                    else:
                        st.markdown(
                            f"No Rakuten rate saved for this store. "
                            f"[Check Rakuten]({rakuten_check_url(L.store)})"
                        )
                    if L.link:
                        st.link_button("Go to store", L.link)
                with right:
                    st.metric("Effective price", f"${o.effective_price:,.2f}")
                    ship = (
                        "Free shipping" if L.shipping == 0
                        else f"+ ${L.shipping:,.2f} shipping" if L.shipping
                        else "Shipping unknown"
                    )
                    st.caption(f"Price ${L.price:,.2f}  \n{ship}")
                    if o.match_score < 1:
                        st.caption(f"Title match {o.match_score:.0%}")

# ---------- Cashback rates tab ----------
with tab_rates:
    columns = {
        "store": st.column_config.TextColumn("Store", required=True),
        "aliases": st.column_config.TextColumn("Aliases"),
        "rakuten_percent": st.column_config.TextColumn("Rakuten %", help="e.g. 9 or 2.5"),
        "notes": st.column_config.TextColumn("Notes"),
    }
    if ALLOW_RATE_EDITING:
        st.write(
            "Rakuten doesn't offer a free API, so enter rates here. Rates change often, "
            "so check them before buying. **Aliases** are other names a store shows up as "
            "in search results, separated by `|`."
        )
        edited = st.data_editor(
            load_rows(), num_rows="dynamic", width="stretch",
            column_config=columns, key="rates_editor",
        )
        if st.button("Save rates"):
            save_rows(edited)
            st.success("Saved to cashback_rates.csv.")
    else:
        st.write(
            "Cash back rates used for ranking. They're updated by hand and may be out "
            "of date, so confirm the current rate on Rakuten before you buy."
        )
        st.dataframe(load_rows(), width="stretch", column_config=columns, hide_index=True)

st.divider()
st.caption(
    "Prices come from Google Shopping results and may have changed. Cash back rates are "
    "entered by hand and may be out of date. This site isn't affiliated with Rakuten or "
    "any store. Always check the final price at checkout."
)
