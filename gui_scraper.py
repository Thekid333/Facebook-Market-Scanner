import customtkinter as ctk
import threading
import asyncio
import os
import random
import time

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

import marketplace_core as core

# ==========================================
#              CONFIGURATION
# ==========================================

# --- MONITOR POSITION ---
# Change these numbers to move the browser!
# 2000,100 = Right Monitor   |   -1500,100 = Left Monitor   |   100,100 = Main
BROWSER_POSITION = "--window-position=2000,100"

# Friendly name -> Facebook Marketplace search URL.
SEARCH_URLS = {
    "Washer and Dryer": "https://www.facebook.com/marketplace/112825518732186/search?sortBy=distance_ascend&query=Washer%20and%20Dryer&exact=false",
    "Washer and Dryer (newest)": "https://www.facebook.com/marketplace/112825518732186/search?minPrice=0&deliveryMethod=local_pick_up&sortBy=creation_time_descend&query=Washer%20and%20Dryer&exact=false",
}

AUTH_FILE = "fb_auth.json"

# Global Control Flags
IS_RUNNING = False


def log_status(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


async def run_scraper_cycle(gui_log):
    """Runs ONE complete pass through all URLs, then publishes to the Gist."""
    log_status("Starting Batch Scan...")
    store = core.load_store()
    new_count = 0

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
            context = await browser.new_context()

        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        for search_name, url in SEARCH_URLS.items():
            if not IS_RUNNING:
                log_status("Stop signal received. Aborting current batch.")
                break

            log_status(f"Scanning: {search_name}...")
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
                        log_status(f"  + NEW: {record['title']}")
                        gui_log(f"+ {record['title']} ({record['price']})")

                # Open each new item's page to stamp its real listed time.
                if new_records:
                    await core.enrich_listed_times(page, new_records, log=log_status)

                await page.wait_for_timeout(random.randint(3000, 6000))

            except Exception as e:
                log_status(f"Error scanning {search_name}: {e}")
                continue

        await browser.close()

    # Publish the full feed to the Gist (replaces the old email step).
    if IS_RUNNING:
        core.publish_store(store, log=lambda m: (log_status(m), gui_log(m)))
    log_status(f"Batch Scan Complete. {new_count} new this pass.")


def background_loop(status_callback, gui_log):
    """The infinite loop that runs in the background thread."""
    while True:
        if IS_RUNNING:
            try:
                status_callback("Scanning...")
                asyncio.run(run_scraper_cycle(gui_log))

                if IS_RUNNING:
                    sleep_time = random.randint(180, 360)
                    status_callback(f"Sleeping {sleep_time}s...")
                    for _ in range(sleep_time):
                        if not IS_RUNNING:
                            break
                        time.sleep(1)
            except Exception as e:
                status_callback(f"Error: {str(e)[:30]}...")
                log_status(f"Critical Error: {e}")
                time.sleep(10)
        else:
            time.sleep(1)


# ==========================================
#              GUI INTERFACE
# ==========================================

class ScraperApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FB Scraper Bot")
        self.geometry("440x340")

        self.label_title = ctk.CTkLabel(self, text="Marketplace Scraper", font=("Arial", 20, "bold"))
        self.label_title.pack(pady=16)

        # Warn early if the Gist publishing isn't configured.
        gist_state = "Gist: configured ✓" if core.GITHUB_TOKEN else "Gist: NOT configured (set GITHUB_TOKEN in .env)"
        self.label_gist = ctk.CTkLabel(self, text=gist_state, text_color=("green" if core.GITHUB_TOKEN else "orange"))
        self.label_gist.pack()

        self.switch_var = ctk.StringVar(value="off")
        self.switch = ctk.CTkSwitch(
            self, text="Scraper OFF", command=self.toggle_switch,
            variable=self.switch_var, onvalue="on", offvalue="off", font=("Arial", 14),
        )
        self.switch.pack(pady=16)

        self.status_label = ctk.CTkLabel(self, text="Status: Stopped", text_color="gray")
        self.status_label.pack(pady=6)

        self.log_textbox = ctk.CTkTextbox(self, height=120)
        self.log_textbox.pack(pady=10, padx=20, fill="x")
        self.log_textbox.insert("0.0", "Ready. Listings publish to your Gist (no email).\n")

        self.thread = threading.Thread(
            target=background_loop, args=(self.update_status, self.gui_log), daemon=True
        )
        self.thread.start()

    def update_status(self, text):
        # Marshal onto the Tk main thread — the scraper runs on a background thread.
        self.after(0, lambda: self.status_label.configure(text=f"Status: {text}"))

    def gui_log(self, text):
        def _append():
            self.log_textbox.insert("end", f"{text}\n")
            self.log_textbox.see("end")
        self.after(0, _append)

    def toggle_switch(self):
        global IS_RUNNING
        if self.switch_var.get() == "on":
            IS_RUNNING = True
            self.switch.configure(text="Scraper ON")
            self.status_label.configure(text_color="green")
            self.gui_log(">> Starting...")
        else:
            IS_RUNNING = False
            self.switch.configure(text="Scraper OFF")
            self.status_label.configure(text_color="red", text="Status: Stopping (wait for scan)...")
            self.gui_log(">> Stopping...")


if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = ScraperApp()
    app.mainloop()
