"""
Scraper.py
----------
CLI entry point: runs scan cycles continuously in the terminal and publishes
the feed to the GitHub Gist after each pass.

The searches and all scan logic live in scanner.py (shared with the GUI).
"""

import asyncio
import random
import time

import marketplace_core as core
import scanner


async def run_one_cycle():
    print(f"--- Starting Batch Scan at {time.strftime('%H:%M:%S')} ---")
    store = core.load_store()
    new_count, healed = await scanner.run_scan_cycle(store)
    print(f"Cycle complete. {new_count} new listing(s), {healed} listed-time(s) healed.")
    # Prune, save, and publish the whole feed to the Gist (skipped if unchanged).
    core.publish_store(store, changed=bool(new_count or healed))


if __name__ == "__main__":
    print("--- Marketplace Scraper Started (Gist publishing mode) ---")
    while True:
        try:
            asyncio.run(run_one_cycle())
        except Exception as e:
            print(f"Critical Error: {e}")

        sleep_time = random.randint(*scanner.CYCLE_SLEEP_RANGE)
        print(f"Sleeping for {sleep_time} seconds ({sleep_time / 60:.1f} minutes)...")
        time.sleep(sleep_time)
