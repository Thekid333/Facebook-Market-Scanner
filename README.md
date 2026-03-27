# FB Marketplace Scraper Bot

A Python bot that monitors Facebook Marketplace for new listings matching your saved searches and instantly emails you a summary when new items appear. Includes both a headless CLI version and a GUI desktop app.

---

## Features

- Monitors multiple Marketplace search URLs simultaneously
- Detects new listings and skips already-seen items (persistent deduplication)
- Sends a single batch HTML email with item title, price, photo, and a direct link
- Randomized delays between requests to avoid bot detection
- Stealth mode via Playwright (hides `webdriver` flag)
- **GUI version** (`gui_scraper.py`) with a dark-mode on/off toggle and live status display
- **CLI version** (`Scraper.py`) for running in the background as a script

---

## Project Structure

```
.
├── Scraper.py          # Headless CLI scraper (runs continuously)
├── gui_scraper.py      # GUI desktop app with on/off toggle
├── setup_login.py      # One-time Facebook login session saver
├── fb_auth.json        # Saved login session (gitignored — do not commit)
├── seen_couches.json   # Deduplication database (gitignored)
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

Open `gui_scraper.py` (or `Scraper.py`) and edit the `SEARCH_URLS` dictionary. Each entry is a name paired with a Facebook Marketplace search URL. Uncomment any of the pre-built examples or paste in your own search URLs.

### 4. Configure email notifications

In the same file, update the email settings:

```python
SENDER_EMAIL    = "your_gmail@gmail.com"
SENDER_PASSWORD = "your_app_password"   # Use a Gmail App Password, not your real password
RECEIVER_EMAIL  = "where_to_send@gmail.com"
```

> **Important:** Never commit your app password to version control. Consider moving credentials to a `.env` file and loading them with `python-dotenv`.

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
3. BeautifulSoup parses the page HTML for Marketplace item links.
4. New item IDs (not in `seen_couches.json`) are collected with their title, price, image, and link.
5. After all searches complete, one summary email is sent with every new find.
6. The bot sleeps for a random interval (3–6 minutes) and repeats.

---

## Security Notes

- `fb_auth.json` contains your Facebook session cookies — **never commit this file.**
- Store email credentials in environment variables or a `.env` file rather than hardcoding them in source.
- If you accidentally commit credentials, revoke them immediately and generate new ones.
