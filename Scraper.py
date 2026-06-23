import asyncio
import os
import random
import time

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

import marketplace_core as core

# --- CONFIGURATION: NAMED SEARCHES ---
# Each entry is a friendly name -> a Facebook Marketplace search URL.
# Tip: append &sortBy=creation_time_descend for the freshest items.
SEARCH_URLS = {
    # "Free Items": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=0&daysSinceListed=1&sortBy=creation_time_descend&query=Free&exact=false",
    # "KitchenAid Mixer": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=100&daysSinceListed=1&sortBy=creation_time_descend&query=KitchenAid%20Mixer&exact=false",
    # "Dyson V10": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=125&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&query=Dyson%20V10&exact=false",
    "Washer and Dryer": "https://www.facebook.com/marketplace/112825518732186/search?sortBy=distance_ascend&query=Washer%20and%20Dryer&exact=false",
}

AUTH_FILE = "fb_auth.json"


# --- MAIN SCRAPER LOGIC ---

async def check_marketplace():
    print(f"--- Starting Batch Scan at {time.strftime('%H:%M:%S')} ---")

    store = core.load_store()
    new_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--window-position=2000,100",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        if os.path.exists(AUTH_FILE):
            context = await browser.new_context(
                storage_state=AUTH_FILE, viewport={"width": 1280, "height": 800}
            )
        else:
            print("WARNING: No login file found. Run setup_login.py first.")
            context = await browser.new_context()

        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # --- LOOP THROUGH ALL SEARCHES ---
        for search_name, url in SEARCH_URLS.items():
            print(f"Scanning: {search_name}...")
            try:
                await page.goto(url, timeout=60000)
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass

                await page.wait_for_timeout(random.randint(2000, 4000))
                await page.mouse.wheel(0, 1500)
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
                        print(f"  + NEW: {record['title']} ({record['price']}) {record['location']}")

                # Open each new item's page to stamp its real listed time.
                if new_records:
                    await core.enrich_listed_times(page, new_records)

                await page.wait_for_timeout(random.randint(3000, 6000))

            except Exception as e:
                print(f"Error scanning {search_name}: {e}")
                continue

        await browser.close()

    # Prune, save, and publish the whole feed to the Gist (replaces email).
    print(f"Cycle complete. {new_count} new listing(s) this pass.")
    core.publish_store(store)


if __name__ == "__main__":
    print("--- Marketplace Scraper Started (Gist publishing mode) ---")
    while True:
        try:
            asyncio.run(check_marketplace())
        except Exception as e:
            print(f"Critical Error: {e}")

        sleep_time = random.randint(180, 360)
        print(f"Sleeping for {sleep_time} seconds ({sleep_time / 60:.1f} minutes)...")
        time.sleep(sleep_time)
