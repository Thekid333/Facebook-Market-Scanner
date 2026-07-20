"""
scanner.py
----------
The Playwright scan cycle shared by both entry points:

  * Scraper.py     — headless-style CLI loop
  * gui_scraper.py — desktop GUI with an on/off toggle

One cycle launches Chromium with the saved Facebook session, visits every
configured search, parses the listing cards, records new items into the store,
and opens each new item's page to stamp its real listed time.

Edit SEARCH_URLS below to change what gets scanned — the CLI and the GUI both
read this one dictionary, so there is a single source of truth.
"""

import os
import random

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

import marketplace_core as core

# ==========================================
#              CONFIGURATION
# ==========================================

# Friendly name -> Facebook Marketplace search URL.
# Tip: append &sortBy=creation_time_descend for the freshest items.
SEARCH_URLS = {
    "Washer and Dryer": "https://www.facebook.com/marketplace/112825518732186/search?sortBy=distance_ascend&query=Washer%20and%20Dryer&exact=false",
    "Washer and Dryer (newest)": "https://www.facebook.com/marketplace/112825518732186/search?minPrice=0&deliveryMethod=local_pick_up&sortBy=creation_time_descend&query=Washer%20and%20Dryer&exact=false",
    # "Free Items": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=0&daysSinceListed=1&sortBy=creation_time_descend&query=Free&exact=false",
    # "KitchenAid Mixer": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=100&daysSinceListed=1&sortBy=creation_time_descend&query=KitchenAid%20Mixer&exact=false",
    # "Dyson V10": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=125&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&query=Dyson%20V10&exact=false",
}

AUTH_FILE = "fb_auth.json"

# Where the visible browser window opens.
# 2000,100 = Right Monitor | -1500,100 = Left Monitor | 100,100 = Main
BROWSER_POSITION = "--window-position=2000,100"

# Seconds to sleep between scan cycles (randomized to look human).
CYCLE_SLEEP_RANGE = (180, 360)


async def run_scan_cycle(store, log=print, on_new=None, should_continue=None):
    """
    Run ONE complete pass over all SEARCH_URLS, recording new listings in `store`.

    - `log`: line logger (defaults to print).
    - `on_new`: optional callback invoked with each newly-recorded record dict.
    - `should_continue`: optional zero-arg callable checked between searches so a
      GUI stop switch can abort the rest of the batch.

    Returns `(new_count, healed)`: new listings found, and stored listings whose
    real listed_at was backfilled. The caller publishes the store afterwards —
    pass `changed=bool(new_count or healed)` to core.publish_store so unchanged
    cycles skip the gist PATCH and keep the feed's ETag stable.
    """
    new_count = 0
    healed = 0
    # One shared budget of item-page fetches per cycle: new listings first,
    # whatever is left goes to backfilling older records missing listed_at.
    detail_budget = core.DETAIL_FETCH_CAP
    attempted_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[BROWSER_POSITION, "--disable-blink-features=AutomationControlled"],
        )

        if os.path.exists(AUTH_FILE):
            context = await browser.new_context(
                storage_state=AUTH_FILE, viewport={"width": 1280, "height": 800}
            )
        else:
            log(f"WARNING: No login file ({AUTH_FILE}) found. Run setup_login.py first.")
            context = await browser.new_context()

        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        for search_name, url in SEARCH_URLS.items():
            if should_continue is not None and not should_continue():
                log("Stop signal received. Aborting current batch.")
                break

            log(f"Scanning: {search_name}...")
            try:
                await page.goto(url, timeout=60000)
                try:
                    await page.keyboard.press("Escape")  # dismiss any login popup
                except Exception:
                    pass

                await page.wait_for_timeout(random.randint(2000, 4000))
                await page.mouse.wheel(0, 1500)  # scroll to load lazy listings
                await page.wait_for_timeout(2000)

                soup = BeautifulSoup(await page.content(), "html.parser")
                new_records = []
                for link in soup.find_all("a", href=True):
                    record = core.parse_listing(link, search_name)
                    if record is None:
                        continue
                    if core.record_listing(store, record):
                        new_count += 1
                        new_records.append(record)
                        log(f"  + NEW: {record['title']} ({record['price']}) {record['location']}")
                        if on_new is not None:
                            on_new(record)

                # Open each new item's page to stamp its real listed time.
                if new_records and detail_budget > 0:
                    detail_budget -= await core.enrich_listed_times(
                        page, new_records, log=log, limit=detail_budget
                    )
                    attempted_ids.update(r["id"] for r in new_records)

                await page.wait_for_timeout(random.randint(3000, 6000))

            except Exception as e:
                log(f"Error scanning {search_name}: {e}")
                continue

        # Heal older store records that still lack a listed_at (recorded before
        # enrichment existed, or wiped by the pre-fix bug, or failed to parse
        # last time) with whatever fetch budget this cycle has left.
        if detail_budget > 0 and (should_continue is None or should_continue()):
            backlog = [
                rec for rec in core.records_missing_listed_at(store)
                if rec["id"] not in attempted_ids
            ]
            if backlog:
                log(f"Backfilling listed times: {min(len(backlog), detail_budget)} of {len(backlog)} pending...")
                await core.enrich_listed_times(page, backlog, log=log, limit=detail_budget)
                healed = sum(1 for rec in backlog if rec.get("listed_at"))

        await browser.close()

    return new_count, healed
