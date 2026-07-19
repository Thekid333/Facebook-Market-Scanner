# FB Marketplace Scraper Bot

A Python bot that monitors Facebook Marketplace for new listings matching your saved
searches and **publishes them to a GitHub Gist** so the companion iOS app (the
[Appliance Checklist app](../Appliance-Delievery-App)'s **Snipe** tab) can show them
ranked by recency and distance — no email required. Includes both a headless CLI
version and a GUI desktop app.

> **New in this version:** email alerts are replaced by Gist publishing, and each
> listing now captures its **location** and a **first-seen timestamp** so the app can
> rank by distance and recency. See [`../SNIPE_SETUP.md`](../SNIPE_SETUP.md) for the
> full end-to-end setup.

---

## Features

- Monitors multiple Marketplace search URLs simultaneously
- Detects new listings and skips already-seen items (persistent deduplication)
- Captures each listing's title, price, **location**, photo, link, and **first-seen time**
- Publishes the rolling feed to a **GitHub Gist** (`listings.json`) for the iOS app — no email
- Randomized delays between requests to avoid bot detection
- Stealth mode via Playwright (hides `webdriver` flag)
- **GUI version** (`gui_scraper.py`) with a dark-mode on/off toggle and live status display
- **CLI version** (`Scraper.py`) for running in the background as a script

---

## Project Structure

```
.
├── marketplace_core.py # Shared parsing + store + Gist publishing logic
├── scanner.py          # Shared Playwright scan cycle + SEARCH_URLS config
├── Scraper.py          # CLI entry point (runs continuously in the terminal)
├── gui_scraper.py      # GUI entry point with on/off toggle
├── setup_login.py      # One-time Facebook login session saver
├── import_cookies.py   # Alternative: build fb_auth.json from browser cookies
├── fb_auth.json        # Saved login session (gitignored — do not commit)
├── listings_store.json # Rolling listing store w/ timestamps (gitignored)
├── .env                # GITHUB_TOKEN + GIST_ID (gitignored)
└── requirements.txt
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Save your Facebook login session

Run this once to log in manually and save your session cookies:

```bash
python setup_login.py
```

A browser window will open. Log in to Facebook, then press `Enter` in the terminal. Your session is saved to `fb_auth.json` (which is gitignored and stays local).

### 3. Configure your searches

Open `scanner.py` and edit the `SEARCH_URLS` dictionary. Each entry is a name paired with a Facebook Marketplace search URL — both the CLI and the GUI read this one dictionary. Uncomment any of the pre-built examples or paste in your own search URLs.

### 4. Configure Gist publishing (replaces email)

Copy `.env.example` to `.env` and add a GitHub token with the **`gist`** scope
(create one at <https://github.com/settings/tokens>):

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
GIST_ID=                       # leave blank on first run — it will be printed for you
LISTING_RETENTION_DAYS=7
```

On the first run the scraper creates a secret gist and prints its `GIST_ID`; paste that
back into `.env` (and into the app's Snipe settings). Full walkthrough:
[`../SNIPE_SETUP.md`](../SNIPE_SETUP.md).

> **Important:** `.env`, `fb_auth.json`, and `listings_store.json` are gitignored — never commit them.

---

## Running

### GUI App (recommended)
```bash
python gui_scraper.py
```
Toggle the switch to start/stop scanning. The app polls on a randomized 3–6 minute interval.

### CLI (headless)
```bash
python Scraper.py
```
Runs continuously in the terminal with the same polling interval.

---

## How It Works

1. Playwright launches a Chromium browser using your saved Facebook session.
2. Each search URL is visited in sequence; the page scrolls to load lazy-loaded listings.
3. BeautifulSoup parses each card into a record (title, price, location, image, link).
4. New items are added to `listings_store.json` with a first-seen timestamp; known items keep theirs.
5. Listings older than `LISTING_RETENTION_DAYS` are pruned, and the whole feed is published to the Gist.
6. The bot sleeps for a random interval (3–6 minutes) and repeats.

The iOS app then fetches the Gist and ranks everything — see [`../SNIPE_SETUP.md`](../SNIPE_SETUP.md).

---

## Security Notes

- `fb_auth.json` contains your Facebook session cookies — **never commit this file.**
- Keep your `GITHUB_TOKEN` in `.env` (gitignored), never hardcoded in source.
- The published gist is *secret* (unlisted), but anyone with its URL can read it — keep the URL private.
- If you accidentally commit a token, revoke it immediately and generate a new one.
