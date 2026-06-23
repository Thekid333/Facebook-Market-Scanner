"""
marketplace_core.py
-------------------
Shared logic for the Facebook Marketplace scanner.

This module is the bridge between the PC-side scraper and the iOS app.
Instead of emailing finds, the scraper now:

  1. Parses each listing card into a rich record (title, price, location,
     image, link, and the time it was first seen).
  2. Keeps a persistent rolling store of recent listings (listings_store.json).
  3. Publishes the whole store as `listings.json` to a secret GitHub Gist.

The iOS app then fetches that Gist from anywhere (free, no server to run) and
ranks the listings by recency + distance. See README for setup.

Both Scraper.py (CLI) and gui_scraper.py (GUI) import from here so the parsing
and publishing logic lives in exactly one place.
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests

try:
    # Optional: load a local .env if python-dotenv is installed.
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ----------------------------------------------------------------------------
# Files / config
# ----------------------------------------------------------------------------

STORE_FILE = "listings_store.json"        # Full records, keyed by item id (persistent)
LEGACY_SEEN_FILE = "seen_couches.json"    # Old format: a flat list of seen ids

# How long a listing stays in the published feed before it is pruned out.
RETENTION_DAYS = int(os.getenv("LISTING_RETENTION_DAYS", "7"))

# GitHub Gist publishing (the free "view anywhere" bridge to the app)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GIST_ID = os.getenv("GIST_ID", "").strip()
GIST_FILENAME = "listings.json"

# A descriptive User-Agent keeps GitHub happy.
_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "fb-marketplace-scanner",
}


def _iso_now():
    # Millisecond precision with an explicit offset, e.g. 2026-06-23T18:00:00.123+00:00.
    # This parses cleanly with both Python's fromisoformat() and Swift's
    # ISO8601DateFormatter (.withFractionalSeconds).
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ----------------------------------------------------------------------------
# Listing parsing
# ----------------------------------------------------------------------------

# "$1,200" or "Free"
_PRICE_RE = re.compile(r"(\$\d[\d,]*)|(\bFree\b)", re.IGNORECASE)

# "Denver, CO"  /  "Salt Lake City, UT"  (City, 2-letter state at the end of the card)
_LOCATION_RE = re.compile(r"([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)*,\s*[A-Z]{2})")

# "5 mi"  /  "12.3 miles"  /  "8 km"  (only present if a location is set in the search)
_DISTANCE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mi|miles|km)\b", re.IGNORECASE)


def _price_to_value(price_text):
    """Turn a price string into a number for sorting. 'Free' -> 0, unknown -> None."""
    if not price_text:
        return None
    if price_text.strip().lower() == "free":
        return 0
    digits = re.sub(r"[^\d]", "", price_text)
    return int(digits) if digits else None


def parse_listing(link, search_name):
    """
    Turn one BeautifulSoup <a> marketplace card into a record dict, or None.

    `link` is the <a href="/marketplace/item/...."> element.
    `search_name` is the friendly name of the search this came from.
    """
    href = link.get("href", "")
    if "/marketplace/item/" not in href:
        return None

    try:
        item_id = href.split("/item/")[1].split("/")[0].split("?")[0]
    except IndexError:
        return None
    if not item_id:
        return None

    img_tag = link.find("img")
    title = "Unknown Title"
    image_src = ""
    if img_tag:
        title = img_tag.get("alt", "Unknown Title")
        image_src = img_tag.get("src", "")

    all_text = link.get_text(separator=" ", strip=True)

    price = "See Listing"
    price_match = _PRICE_RE.search(all_text)
    if price_match:
        price = price_match.group(0)

    # Location: take the LAST "City, ST" match (it sits below the title on the card).
    location = ""
    loc_matches = _LOCATION_RE.findall(all_text)
    if loc_matches:
        location = loc_matches[-1].strip()

    # Distance straight from Facebook, if the search exposed it.
    distance_miles = None
    dist_match = _DISTANCE_RE.search(all_text)
    if dist_match:
        value = float(dist_match.group(1))
        unit = dist_match.group(2).lower()
        distance_miles = round(value * 0.621371, 1) if unit == "km" else value

    clean_href = href if href.startswith("http") else f"https://www.facebook.com{href}"

    return {
        "id": item_id,
        "title": title,
        "price": price,
        "price_value": _price_to_value(price),
        "location": location,
        "distance_miles": distance_miles,   # from FB directly; may be None
        "image": image_src,
        "link": href,
        "url": clean_href,
        "category": search_name,
        # first_seen is stamped by the store when the item is first recorded.
    }


# ----------------------------------------------------------------------------
# Persistent store (rolling window of recent listings)
# ----------------------------------------------------------------------------

def load_store():
    """
    Load the persistent listing store: { item_id: record }.

    Migrates the old `seen_couches.json` (a flat id list) the first time so that
    items you already saw don't all reappear as brand-new.
    """
    if os.path.exists(STORE_FILE):
        try:
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    # One-time migration from the legacy seen-id list.
    store = {}
    if os.path.exists(LEGACY_SEEN_FILE):
        try:
            with open(LEGACY_SEEN_FILE, "r", encoding="utf-8") as f:
                old_ids = json.load(f)
            # Stamp them in the past so they are treated as "already seen"
            # and get pruned out of the feed on the next cycle.
            old_time = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS + 1)).isoformat(timespec="milliseconds")
            for old_id in old_ids:
                store[str(old_id)] = {"id": str(old_id), "first_seen": old_time, "migrated": True}
        except (json.JSONDecodeError, OSError):
            pass
    return store


def save_store(store):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def record_listing(store, record):
    """
    Add a freshly parsed record to the store if new.
    Returns True if this listing is new (i.e. worth highlighting).
    """
    item_id = record["id"]
    if item_id in store:
        # Already known: refresh mutable fields but keep the original first_seen.
        existing = store[item_id]
        record["first_seen"] = existing.get("first_seen", _iso_now())
        store[item_id] = record
        return False

    record["first_seen"] = _iso_now()
    store[item_id] = record
    return True


def prune_store(store, retention_days=RETENTION_DAYS):
    """Drop listings older than the retention window. Returns the number removed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    to_delete = []
    for item_id, rec in store.items():
        first_seen = rec.get("first_seen")
        if not first_seen:
            continue
        try:
            seen_dt = datetime.fromisoformat(first_seen)
        except ValueError:
            continue
        if seen_dt < cutoff:
            to_delete.append(item_id)
    for item_id in to_delete:
        del store[item_id]
    return len(to_delete)


def build_feed_payload(store):
    """Build the JSON string the app consumes, newest first."""
    listings = [rec for rec in store.values() if rec.get("title")]  # skip migrated id-only stubs
    listings.sort(key=lambda r: r.get("first_seen", ""), reverse=True)
    payload = {
        "generated_at": _iso_now(),
        "count": len(listings),
        "listings": listings,
    }
    return json.dumps(payload, indent=2)


# ----------------------------------------------------------------------------
# Publishing to GitHub Gist (free, viewable anywhere)
# ----------------------------------------------------------------------------

def publish_to_gist(payload_json, log=print):
    """
    Push the feed to a secret GitHub Gist.

    - If GIST_ID is set, PATCH that gist.
    - If GIST_ID is empty, create a new secret gist and print its id so you can
      paste it into .env (and into the iOS app's Snipe settings).

    Returns the gist id on success, or None on failure / if not configured.
    """
    if not GITHUB_TOKEN:
        log("!! GITHUB_TOKEN not set — skipping publish. (Add it to .env to enable the app feed.)")
        return None

    headers = dict(_GH_HEADERS)
    headers["Authorization"] = f"token {GITHUB_TOKEN}"
    body = {"files": {GIST_FILENAME: {"content": payload_json}}}

    try:
        if GIST_ID:
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers=headers, json=body, timeout=30,
            )
        else:
            body["description"] = "Facebook Marketplace feed for the Snipe app"
            body["public"] = False
            resp = requests.post(
                "https://api.github.com/gists",
                headers=headers, json=body, timeout=30,
            )

        if resp.status_code in (200, 201):
            gist_id = resp.json().get("id")
            if not GIST_ID:
                log("=" * 60)
                log(f"  NEW GIST CREATED. Add this to your .env:")
                log(f"  GIST_ID={gist_id}")
                log(f"  Paste the SAME id into the app's Snipe settings.")
                log("=" * 60)
            else:
                log(f"--> Published {GIST_FILENAME} to gist {gist_id}.")
            return gist_id

        log(f"!! Gist publish failed: HTTP {resp.status_code} {resp.text[:200]}")
        return None
    except requests.RequestException as e:
        log(f"!! Gist publish error: {e}")
        return None


def publish_store(store, log=print):
    """Convenience: prune, save, and publish the store in one call."""
    removed = prune_store(store)
    if removed:
        log(f"Pruned {removed} listing(s) older than {RETENTION_DAYS} days.")
    save_store(store)
    payload = build_feed_payload(store)
    return publish_to_gist(payload, log=log)
