"""Best Price Finder - run with:  streamlit run app.py"""

import streamlit as st

from pricefinder.cashback import CashbackTable, load_rows, rakuten_check_url, save_rows
from pricefinder.config import get_bool, get_int, get_setting
from pricefinder.limits import DailyLimiter
from pricefinder.rakuten import new_store_row, update_row
from pricefinder.ranking import build_options
from pricefinder.search import (
    SearchError,
    demo_results,
    find_product_link,
    google_search_url,
    search_shopping,
    store_matches_url,
)
from pricefinder.stores import FIXED_STORES, StoreCheck, check_brand, check_store

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


@st.cache_data(ttl=86400, show_spinner=False, max_entries=1000)
def cached_product_link(title: str, store: str):
    # Product pages rarely move, so cache for a day.
    if not daily_limiter().try_use():
        raise SearchError("The site reached today's search limit. Please try again tomorrow.")
    return find_product_link(title, store, API_KEY)


@st.cache_data(ttl=86400, show_spinner=False, max_entries=1000)
def cached_new_store_rate(store: str) -> dict:
    # Rakuten rate for a store not in cashback_rates.csv. Cached for a day.
    if not daily_limiter().try_use():
        raise SearchError("The site reached today's search limit.")
    return new_store_row(store, API_KEY)


TOP_N_STORES = 3


@st.cache_data(ttl=3600, show_spinner=False, max_entries=500)
def cached_key_store_checks(query: str) -> list[StoreCheck]:
    """Amazon, Costco and the brand's site for this search (3 credits, cached 1 hour)."""
    checks = []
    for name, domain in FIXED_STORES:
        if not daily_limiter().try_use():
            raise SearchError("The site reached today's search limit.")
        checks.append(check_store(query, name, domain, API_KEY))
    if daily_limiter().try_use():
        brand = check_brand(query, API_KEY)
        # Skip the brand if it's one of the fixed stores (e.g. searching "Amazon Kindle").
        if brand and brand.domain not in {d for _, d in FIXED_STORES}:
            # Only a category page found? Search the brand's own site once more.
            if not (brand.link and brand.link.is_product_page) and daily_limiter().try_use():
                retry = check_store(query, brand.name, brand.domain, API_KEY)
                if retry.link and (retry.link.is_product_page or not brand.link):
                    brand.link = retry.link
            checks.append(brand)
    return checks


def show_rakuten(rate_info: dict | None, price: float | None, store: str) -> None:
    """One line about the store's Rakuten cash back."""
    checked = (
        f" (checked {rate_info['last_checked']})"
        if rate_info and rate_info.get("last_checked") else ""
    )
    pct = rate_info["percent"] if rate_info else None
    if pct:
        up_to = "up to " if (rate_info.get("notes") or "").lower().startswith("up to") else ""
        amount = f" ({up_to}about ${price * pct / 100:,.2f})" if price else ""
        st.success(f"Activate Rakuten first: {up_to}{pct:g}% cash back{amount}{checked}")
    elif rate_info and pct == 0:
        why = rate_info.get("notes") or "no cash back at this store right now"
        st.caption(f"Rakuten: 0% – {why}{checked}.")
    elif rate_info and rate_info.get("notes"):
        st.caption(f"Rakuten: {rate_info['notes']}{checked}.")
    else:
        st.markdown(
            f"No Rakuten rate saved for this store. [Check Rakuten]({rakuten_check_url(store)})"
        )


def rates_table() -> CashbackTable:
    """Saved rates plus any looked up this visit (public site doesn't save them)."""
    extra = list(st.session_state.get("extra_rates", {}).values())
    return CashbackTable(load_rows() + extra)


def add_missing_store_rates(stores: list[str]) -> bool:
    """Look up Rakuten rates for stores not in the table. Returns True if any were added."""
    table = rates_table()
    missing = [s for s in dict.fromkeys(stores) if table.info(s) is None]
    if not missing:
        return False
    new_rows = []
    with st.spinner(f"Checking Rakuten for {', '.join(missing)}..."):
        for store in missing:
            try:
                new_rows.append(cached_new_store_rate(store))
            except SearchError:
                pass  # leave it as "not checked"; shown on the rates tab
    if not new_rows:
        return False
    if ALLOW_RATE_EDITING:
        save_rows(load_rows() + new_rows)  # your PC: keep them in the CSV
    else:
        extra = st.session_state.setdefault("extra_rates", {})
        for row in new_rows:
            extra[row["store"]] = row
    return True


def use_session_search() -> bool:
    """Count one search for this visitor. Shows an error if over the limit."""
    used = st.session_state.get("searches_used", 0)
    if used >= SESSION_SEARCH_LIMIT:
        st.error(
            f"You've reached the limit of {SESSION_SEARCH_LIMIT} searches per visit. "
            "Please come back later."
        )
        return False
    st.session_state["searches_used"] = used + 1
    return True


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
    hide_carrier = st.checkbox(
        "Hide carrier-locked / plan deals", value=True,
        help="Hides listings from or locked to Verizon, AT&T, T-Mobile, etc.",
    )
    hide_suspicious = st.checkbox(
        "Hide suspiciously cheap prices", value=True,
        help="Hides listings far below the typical price (often accessories or fake offers).",
    )
    check_key_stores = st.checkbox(
        "Also check Amazon, Costco & brand site", value=True,
        help="Finds the product page at these stores, which Google Shopping often "
             "leaves out. Uses 3 extra searches (remembered for an hour).",
    )

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
        try:
            if demo:
                listings = demo_results()
            elif not API_KEY:
                st.error("Search isn't set up yet. Turn on demo mode to try the app.")
                st.stop()
            elif not use_session_search():
                st.stop()
            else:
                with st.spinner("Searching stores..."):
                    listings = cached_search(q)
        except SearchError as e:
            st.error(str(e))
            st.stop()
        # Keep results so they stay on screen when a button below is clicked.
        st.session_state["results"] = {"query": q, "listings": listings, "demo": demo}
        st.session_state["direct_links"] = {}

    results = st.session_state.get("results")
    if results:
        q, listings = results["query"], results["listings"]
        if results["demo"]:
            st.info("Demo mode: these listings and prices are made up.")

        def rank():
            t = rates_table()
            return t, build_options(
                q, listings, t, min_match, best_per_store, hide_carrier, hide_suspicious
            )

        table, ranked = rank()
        key_checks = []
        if not results["demo"] and API_KEY:
            if check_key_stores:
                try:
                    with st.spinner("Checking Amazon, Costco and the brand's website..."):
                        key_checks = cached_key_store_checks(q)
                except SearchError as e:
                    st.warning(f"Couldn't check Amazon/Costco/brand site: {e}")
            # Make sure the top stores and key stores have a Rakuten rate (even
            # if it's 0), then re-rank in case a new rate changes the order.
            top = [o.listing.store for o in ranked.options[:TOP_N_STORES]]
            if add_missing_store_rates(top + [c.name for c in key_checks]):
                table, ranked = rank()
        options = ranked.options
        st.session_state["top_stores"] = {
            "query": q,
            "demo": results["demo"],
            "rows": [(o.listing.store, table.info(o.listing.store)) for o in options[:TOP_N_STORES]],
        }
        hidden_note = ", ".join(f"{n} {reason}" for reason, n in ranked.hidden.items())

        if not options:
            st.warning(
                f"Found {len(listings)} listings, but none passed the filters"
                + (f" (hidden: {hidden_note})" if hidden_note else "")
                + ". Try changing the settings in the sidebar."
            )
        else:
            st.caption(
                f"Results for **{q}**: {len(options)} options from {len(listings)} listings, "
                "cheapest first after cashback."
                + (f"  \nHidden: {hidden_note}." if hidden_note else "")
            )

        # --- Always check Amazon, Costco and the brand's own website ---
        if key_checks:
            st.markdown("**Also check these stores**")
            cols = st.columns(len(key_checks))
            for col, check in zip(cols, key_checks):
                with col, st.container(border=True):
                    st.markdown(f"**{'🏷️ Brand site: ' if check.is_brand else ''}{check.name}**")
                    # Price only if Google Shopping listed this store too.
                    same_store = [
                        o for o in options
                        if store_matches_url(o.listing.store, "https://" + check.domain)
                    ]
                    if same_store:
                        cheapest = min(same_store, key=lambda o: o.listing.price)
                        st.metric("Price", f"${cheapest.listing.price:,.2f}")
                        show_rakuten(table.info(check.name), cheapest.listing.price, check.name)
                    else:
                        st.caption("Price not listed by Google. Open the store to check.")
                        show_rakuten(table.info(check.name), None, check.name)
                    if check.link and check.link.is_product_page:
                        st.link_button(f"View on {check.name}", check.link.url, type="primary")
                    elif check.link:
                        st.link_button(f"Related page on {check.name}", check.link.url)
                        st.caption("Exact product not found here.")
                    else:
                        st.caption(f"Not found at {check.name}.")

        direct_links = st.session_state.setdefault("direct_links", {})
        for i, o in enumerate(options, 1):
            L = o.listing
            link_key = f"{L.store}|{L.title}"
            with st.container(border=True):
                left, right = st.columns([3, 1])
                with left:
                    st.markdown(f"**Option {i}: {L.store}**")
                    st.write(L.title)
                    show_rakuten(table.info(L.store), L.price, L.store)

                    # Links to where the price came from.
                    b1, b2 = st.columns(2)
                    if results["demo"]:
                        b1.link_button("Go to store", L.link)
                    else:
                        b1.link_button(f"Find on {L.store}", google_search_url(L.title, L.store))
                        if L.link:
                            b2.link_button("Price source (Google Shopping)", L.link)

                    if not results["demo"]:
                        if link_key in direct_links:
                            found = direct_links[link_key]
                            if found is None:
                                st.caption("Couldn't find this product on the store's own site.")
                            elif found.is_product_page:
                                st.link_button(f"✅ Product page on {L.store}", found.url, type="primary")
                            else:
                                st.link_button(f"Store page (closest match) on {L.store}", found.url)
                                st.caption("Couldn't find the exact product page, only a related page.")
                        elif st.button(
                            "Get direct product link", key=f"direct_{i}",
                            help="Finds the product page on the store's site. Uses 1 search.",
                        ):
                            if use_session_search():
                                try:
                                    with st.spinner("Finding product page..."):
                                        direct_links[link_key] = cached_product_link(L.title, L.store)
                                except SearchError as e:
                                    st.error(str(e))
                                else:
                                    st.rerun()
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
        "last_checked": st.column_config.TextColumn("Last checked"),
        "source": st.column_config.LinkColumn("Source", display_text="Rakuten page"),
    }
    # --- Top stores from the latest search, always shown, even at 0% ---
    top = st.session_state.get("top_stores")
    if top and top["rows"]:
        st.subheader(f"Top {len(top['rows'])} stores for “{top['query']}”")
        top_rows = []
        for rank_no, (store, info) in enumerate(top["rows"], 1):
            if info:
                pct, notes = info["percent"], info.get("notes") or ""
                listed_as = info["store"] if info["store"] != store else ""
                top_rows.append({
                    "rank": rank_no,
                    "store": store,
                    "rakuten_percent": f"{pct or 0:g}%",
                    "notes": (f"Listed as {listed_as}. " if listed_as else "") + notes,
                    "last_checked": info.get("last_checked") or "",
                    "source": info.get("source") or "",
                })
            else:
                top_rows.append({
                    "rank": rank_no, "store": store, "rakuten_percent": "0%",
                    "notes": "Not checked (demo mode)" if top["demo"] else "Couldn't check Rakuten",
                    "last_checked": "", "source": "",
                })
        st.dataframe(
            top_rows, width="stretch", hide_index=True,
            column_config={**columns, "rank": st.column_config.NumberColumn("#", width="small"),
                           "rakuten_percent": st.column_config.TextColumn("Rakuten %")},
        )
    else:
        st.caption("Search for an item to see the Rakuten rates of its top 3 stores here.")

    st.subheader("All saved rates")
    if ALLOW_RATE_EDITING:
        rows = load_rows()

        # --- Automatic update from Rakuten (via Google search results) ---
        st.markdown("**Update from Rakuten**")
        st.write(
            "Finds each store's current Rakuten cash back rate from Google search results "
            "for Rakuten's store pages. **Each store uses 1 search credit.**"
        )
        all_stores = [r["store"] for r in rows]
        selected = st.multiselect("Stores to update", all_stores, default=all_stores)
        if st.button(
            f"Update {len(selected)} store(s) from Rakuten", type="primary",
            disabled=not (API_KEY and selected),
        ):
            progress = st.progress(0.0, text="Checking Rakuten rates...")
            report = []
            for n, row in enumerate(r for r in rows if r["store"] in selected):
                try:
                    result = update_row(row, API_KEY)
                except SearchError as e:
                    result = f"error: {e}"
                report.append({"store": row["store"], "result": result})
                progress.progress((n + 1) / len(selected), text=f"Checked {row['store']}")
            save_rows(rows)
            st.session_state["rate_report"] = report
            # New key so the table below reloads the saved values.
            st.session_state["rates_version"] = st.session_state.get("rates_version", 0) + 1
            st.rerun()
        if report := st.session_state.get("rate_report"):
            with st.expander(f"Last update: {len(report)} store(s) checked", expanded=True):
                st.dataframe(report, width="stretch", hide_index=True)
            st.caption(
                "To update the public website, commit and push cashback_rates.csv to GitHub."
            )

        # --- Manual editing ---
        st.markdown("**Edit rates**")
        st.write(
            "Fix or add rates by hand. **Aliases** are other names a store shows up as "
            "in search results, separated by `|`. Leave Rakuten % empty if unknown, "
            "or enter 0 for no cash back."
        )
        edited = st.data_editor(
            rows, num_rows="dynamic", width="stretch", column_config=columns,
            key=f"rates_editor_{st.session_state.get('rates_version', 0)}",
        )
        if st.button("Save rates"):
            save_rows(edited)
            st.success("Saved to cashback_rates.csv.")
    else:
        st.write(
            "Rakuten cash back rates used for ranking, with the date each was last "
            "checked. Rates change often, so confirm on Rakuten before you buy."
        )
        st.dataframe(
            load_rows(), width="stretch", hide_index=True,
            column_config=columns,
            column_order=["store", "rakuten_percent", "notes", "last_checked", "source"],
        )

st.divider()
st.caption(
    "Prices come from Google Shopping results and may have changed. Cash back rates come "
    "from Rakuten's pages as shown in Google search results and may be out of date. This "
    "site isn't affiliated with Rakuten or any store. Always check the final price at checkout."
)
