from playwright.sync_api import sync_playwright
import time

def save_login_state():
    with sync_playwright() as p:
        # Launch the browser (headless=False so you can see it)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("--- FACEBOOK LOGIN SETUP ---")
        print("1. The browser will open to Facebook.")
        print("2. Log in manually (enter email, password, and 2FA code).")
        print("3. DO NOT close the browser yet.")
        print("4. Once you are fully logged in and can see your Feed/Marketplace, come back here.")
        
        page.goto("https://www.facebook.com/")

        # Wait for user to press Enter in the terminal
        input("\n>>> Press ENTER in this terminal once you are fully logged in... <<<")

        # Save the cookies/storage state to a file
        context.storage_state(path="fb_auth.json")
        print("SUCCESS! Login saved to 'fb_auth.json'.")
        print("You can now close the browser.")
        
        browser.close()

if __name__ == "__main__":
    save_login_state()