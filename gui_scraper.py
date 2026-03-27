import customtkinter as ctk
import threading
import asyncio
import json
import smtplib
import time
import os
import random
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# ==========================================
#              CONFIGURATION
# ==========================================

# --- MONITOR POSITION ---
# Change these numbers to move the browser!
# 2000,100 = Right Monitor
# -1500,100 = Left Monitor
# 100,100 = Top Left of Main Monitor
BROWSER_POSITION = "--window-position=2000,100"

SEARCH_URLS = {
    # "Free Items": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=0&daysSinceListed=1&sortBy=creation_time_descend&itemCondition=used_like_new%2Cused_good%2Cused_fair&query=Free&exact=false",
    # "Free Couch": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=5&daysSinceListed=1&sortBy=creation_time_descend&itemCondition=used_good%2Cused_fair%2Cused_like_new&query=Free%20Couch&exact=false",
    # "KitchenAid Mixer": "http://facebook.com/marketplace/112825518732186/search?maxPrice=100&daysSinceListed=1&sortBy=creation_time_descend&itemCondition=used_good%2Cused_fair%2Cused_like_new&query=KitchenAid%20Mixer&exact=false",
    # "Dyson V10": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=125&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&itemCondition=used_good%2Cused_fair%2Cused_like_new&query=Dyson%20V10&exact=false",
    # "Dyson V11": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=125&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&itemCondition=used_good%2Cused_fair%2Cused_like_new&query=Dyson%20V11&exact=false",
    # "Yeti Tundra": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=135&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&itemCondition=used_good%2Cused_fair%2Cused_like_new&query=YETI%20Tundra&exact=false",
    # "Herman Miller Aeron": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=250&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&itemCondition=used_like_new%2Cused_good%2Cused_fair&query=Herman%20Miller%20Aeron&exact=false",
    # "Garmin Fenix": "https://www.facebook.com/marketplace/112825518732186/search?maxPrice=150&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&itemCondition=used_like_new%2Cused_good%2Cused_fair&query=garmin%20fenix&exact=false",
    # "PS5": "https://www.facebook.com/marketplace/112825518732186/search?minPrice=150&maxPrice=230&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&itemCondition=used_like_new%2Cused_good%2Cused_fair&query=Ps5&exact=false",
    # "Nintendo Switch 2": "https://www.facebook.com/marketplace/112825518732186/search?minPrice=120&maxPrice=250&daysSinceListed=1&deliveryMethod=local_pick_up&sortBy=creation_time_descend&itemCondition=used_like_new%2Cused_good%2Cused_fair&query=nintendo%20switch%202&exact=false"
    "Washer and Dryer":"https://www.facebook.com/marketplace/112825518732186/search?sortBy=distance_ascend&query=Washer%20and%20Dryer&exact=false",
    "Washer and Dryer 2":"https://www.facebook.com/marketplace/112825518732186/search?sortBy=best_match&query=Washer%20and%20Dryer&exact=false",
    "Washer and Dryer 3":"https://www.facebook.com/marketplace/112825518732186/search?minPrice=0&deliveryMethod=local_pick_up&sortBy=creation_time_descend&query=Washer%20and%20Dryer&exact=false"
}

SEEN_DB_FILE = "seen_couches.json"
AUTH_FILE = "fb_auth.json"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "SENDER_EMAIL_PLACEHOLDER"
SENDER_PASSWORD = "SENDER_PASSWORD_PLACEHOLDER" 
RECEIVER_EMAIL = "RECEIVER_EMAIL_PLACEHOLDER"

# ==========================================
#              CORE LOGIC
# ==========================================

# Global Control Flags
IS_RUNNING = False

def log_status(msg):
    """Prints to console for debugging."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def load_seen_items():
    try:
        with open(SEEN_DB_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_seen_items(seen_set):
    with open(SEEN_DB_FILE, "w") as f:
        json.dump(list(seen_set), f)

def send_summary_email(all_items):
    if not all_items: return
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"🚀 Found {len(all_items)} New Items (Batch Summary)"

    html_body = "<h2>New Marketplace Finds</h2>"
    for item in all_items:
        html_body += f"""
        <div style="border: 1px solid #ddd; padding: 10px; margin-bottom: 15px; border-radius: 5px;">
            <h3 style="margin-top: 0;">{item['title']}</h3>
            <p><b>Category:</b> {item['category']}<br>
               <b>Price:</b> <span style="color: green; font-weight: bold;">{item['price']}</span></p>
            <p><a href="https://facebook.com{item['link']}" style="background-color: #1877f2; color: white; padding: 8px 12px; text-decoration: none; border-radius: 4px;">View on Facebook</a></p>
            <img src="{item['img']}" style="max-width: 250px; height: auto; border-radius: 4px;">
        </div>
        """
    msg.attach(MIMEText(html_body, 'html'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        log_status(f"--> SUMMARY Email sent with {len(all_items)} items.")
    except Exception as e:
        log_status(f"!! Failed to send email: {e}")

async def run_scraper_cycle():
    """Runs ONE complete pass through all URLs."""
    log_status("Starting Batch Scan...")
    global_found_items = []

    async with async_playwright() as p:
        # ---------------------------------------------------------
        # THIS IS WHERE WE USE THE POSITION VARIABLE FROM THE TOP
        # ---------------------------------------------------------
        browser = await p.chromium.launch(
            headless=False,
            args=[BROWSER_POSITION] 
        )
        
        context = None
        if os.path.exists(AUTH_FILE):
            # We load the login, but also set size to look normal
            context = await browser.new_context(storage_state=AUTH_FILE, viewport={'width': 1280, 'height': 800})
        else:
            context = await browser.new_context()

        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        seen_items = load_seen_items()
        new_items_found_in_db = False

        # Loop through searches
        for search_name, url in SEARCH_URLS.items():
            # Check if user turned off switch mid-scan
            if not IS_RUNNING: 
                log_status("Stop signal received. Aborting current batch.")
                break 

            log_status(f"Scanning: {search_name}...")
            try:
                await page.goto(url, timeout=60000)
                try: await page.keyboard.press('Escape')
                except: pass
                
                await page.wait_for_timeout(random.randint(2000, 4000)) 
                await page.mouse.wheel(0, 1500)
                await page.wait_for_timeout(2000)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                links = soup.find_all('a', href=True)

                for link in links:
                    href = link['href']
                    if '/marketplace/item/' in href:
                        try: item_id = href.split('/item/')[1].split('/')[0]
                        except: continue
                        
                        if item_id not in seen_items:
                            title = "Unknown"
                            img_src = ""
                            price = "See Listing"

                            img_tag = link.find('img')
                            if img_tag:
                                title = img_tag.get('alt', 'Unknown Title')
                                img_src = img_tag.get('src', '')

                            all_text = link.get_text(separator=" ", strip=True)
                            price_match = re.search(r'(\$\d[\d,]*)|(Free)', all_text)
                            if price_match: price = price_match.group(0)

                            log_status(f"  + HIT: {title}")
                            global_found_items.append({
                                "title": title, "price": price, "link": href, 
                                "img": img_src, "category": search_name
                            })
                            seen_items.add(item_id)
                            new_items_found_in_db = True
                
                # Pause between searches
                await page.wait_for_timeout(random.randint(3000, 6000))

            except Exception as e:
                log_status(f"Error scanning {search_name}: {e}")
                continue

        if new_items_found_in_db:
            save_seen_items(seen_items)

        if len(global_found_items) > 0 and IS_RUNNING:
            send_summary_email(global_found_items)
        
        await browser.close()
    log_status("Batch Scan Complete.")

def background_loop(status_callback):
    """The infinite loop that runs in the background thread."""
    while True:
        if IS_RUNNING:
            try:
                status_callback("Scanning...")
                asyncio.run(run_scraper_cycle())
                
                if IS_RUNNING:
                    sleep_time = random.randint(180, 360)
                    status_callback(f"Sleeping for {sleep_time}s...")
                    # We sleep in small chunks so we can stop faster if user clicks OFF
                    for _ in range(sleep_time):
                        if not IS_RUNNING: break
                        time.sleep(1)
            except Exception as e:
                status_callback(f"Error: {str(e)[:30]}...") # Show error in GUI
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
        self.geometry("400x300")
        
        # UI Elements
        self.label_title = ctk.CTkLabel(self, text="Marketplace Scraper", font=("Arial", 20, "bold"))
        self.label_title.pack(pady=20)

        self.switch_var = ctk.StringVar(value="off")
        self.switch = ctk.CTkSwitch(
            self, 
            text="Scraper OFF", 
            command=self.toggle_switch,
            variable=self.switch_var, 
            onvalue="on", 
            offvalue="off",
            font=("Arial", 14)
        )
        self.switch.pack(pady=20)

        self.status_label = ctk.CTkLabel(self, text="Status: Stopped", text_color="gray")
        self.status_label.pack(pady=10)

        self.log_textbox = ctk.CTkTextbox(self, height=100)
        self.log_textbox.pack(pady=10, padx=20, fill="x")
        self.log_textbox.insert("0.0", "Ready to start.\n")

        # Start background thread immediately
        self.thread = threading.Thread(target=background_loop, args=(self.update_status,))
        self.thread.daemon = True
        self.thread.start()

    def update_status(self, text):
        """Updates the status label from the background thread safely."""
        self.status_label.configure(text=f"Status: {text}")

    def toggle_switch(self):
        global IS_RUNNING
        if self.switch_var.get() == "on":
            IS_RUNNING = True
            self.switch.configure(text="Scraper ON")
            self.status_label.configure(text_color="green")
            self.log_textbox.insert("end", ">> Starting...\n")
        else:
            IS_RUNNING = False
            self.switch.configure(text="Scraper OFF")
            self.status_label.configure(text_color="red", text="Status: Stopping (Wait for scan)...")
            self.log_textbox.insert("end", ">> Stopping...\n")

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = ScraperApp()
    app.mainloop()