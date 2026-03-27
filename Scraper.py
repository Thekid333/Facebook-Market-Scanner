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

# --- CONFIGURATION: NAMED SEARCHES ---
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
    "https://www.facebook.com/marketplace/112825518732186/search?sortBy=distance_ascend&query=Washer%20and%20Dryer&exact=false"
}

SEEN_DB_FILE = "seen_couches.json"
AUTH_FILE = "fb_auth.json"

# --- EMAIL SETTINGS ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "SENDER_EMAIL_PLACEHOLDER"
SENDER_PASSWORD = "SENDER_PASSWORD_PLACEHOLDER" 
RECEIVER_EMAIL = "RECEIVER_EMAIL_PLACEHOLDER"

# --- HELPER FUNCTIONS ---

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
    """
    Sends ONE email containing ALL items found across ALL searches.
    NO LIMITS: If it finds 50 items, it sends 50 items.
    """
    if not all_items:
        return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"🚀 Found {len(all_items)} New Items (Batch Summary)"

    html_body = "<h2>New Marketplace Finds</h2>"
    
    # Loop through EVERY item (No truncation)
    for item in all_items:
        html_body += f"""
        <div style="border: 1px solid #ddd; padding: 10px; margin-bottom: 15px; border-radius: 5px;">
            <h3 style="margin-top: 0;">{item['title']}</h3>
            <p>
                <b>Category:</b> {item['category']}<br>
                <b>Price:</b> <span style="color: green; font-weight: bold;">{item['price']}</span>
            </p>
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
        print(f"--> SUMMARY Email sent with {len(all_items)} items.")
    except Exception as e:
        print(f"!! Failed to send email: {e}")

# --- MAIN SCRAPER LOGIC ---

async def check_marketplace():
    print(f"--- Starting Batch Scan at {time.strftime('%H:%M:%S')} ---")
    
    # Global list to store EVERYTHING found in this 5-minute cycle
    global_found_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
    headless=False, 
    args=["--window-position=2000,100"] 
)
        context = None
        if os.path.exists(AUTH_FILE):
            context = await browser.new_context(storage_state=AUTH_FILE, viewport={'width': 1280, 'height': 800})
        else:
            print("WARNING: No login file found.")
            context = await browser.new_context()

        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        seen_items = load_seen_items()
        new_items_found_in_db = False

        # --- LOOP THROUGH ALL SEARCHES ---
        for search_name, url in SEARCH_URLS.items():
            print(f"Scanning: {search_name}...")
            
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
                        try:
                            item_id = href.split('/item/')[1].split('/')[0]
                        except IndexError:
                            continue
                        
                        if item_id not in seen_items:
                            img_tag = link.find('img')
                            if img_tag:
                                title = img_tag.get('alt', 'Unknown Title')
                                image_src = img_tag.get('src', '')
                                
                                # Price Logic
                                price = "See Listing" 
                                all_text = link.get_text(separator=" ", strip=True)
                                price_match = re.search(r'(\$\d[\d,]*)|(Free)', all_text)
                                if price_match:
                                    price = price_match.group(0)
                                
                                print(f"  + HIT: {title} ({price})")
                                
                                # Add to our GLOBAL list
                                global_found_items.append({
                                    "title": title,
                                    "price": price,
                                    "link": href,
                                    "img": image_src,
                                    "category": search_name
                                })
                                
                                seen_items.add(item_id)
                                new_items_found_in_db = True

                # Pause between URLS
                pause_time = random.randint(3000, 6000)
                await page.wait_for_timeout(pause_time)

            except Exception as e:
                print(f"Error scanning {search_name}: {e}")
                continue

        # --- END OF LOOP ---
        
        # 1. Update Database
        if new_items_found_in_db:
            save_seen_items(seen_items)

        # 2. Send ONE Email for the whole batch (NO LIMITS)
        if len(global_found_items) > 0:
            print(f"Preparing summary email for {len(global_found_items)} items...")
            send_summary_email(global_found_items)
        else:
            print("Cycle complete. No new items found.")

        await browser.close()

if __name__ == "__main__":
    print("--- Multi-Couch Scraper Started ---")
    while True:
        try:
            asyncio.run(check_marketplace())
        except Exception as e:
            print(f"Critical Error: {e}")
        
        sleep_time = random.randint(180, 360) 
        print(f"Sleeping for {sleep_time} seconds ({sleep_time/60:.1f} minutes)...")
        time.sleep(sleep_time)