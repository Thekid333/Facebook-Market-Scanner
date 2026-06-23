from playwright.sync_api import sync_playwright

# A persistent profile dir makes the browser behave like a real, returning user
# (keeps cookies/cache), which helps Facebook's login/2FA pages render normally.
USER_DATA_DIR = "./fb_profile"


def _launch(p, use_chrome):
    args = [
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
    ]
    kwargs = dict(
        user_data_dir=USER_DATA_DIR,
        headless=False,
        no_viewport=True,
        args=args,
    )
    if use_chrome:
        kwargs["channel"] = "chrome"  # use the real Google Chrome you have installed
    return p.chromium.launch_persistent_context(**kwargs)


def save_login_state():
    with sync_playwright() as p:
        # Prefer real Chrome; fall back to bundled Chromium if Chrome isn't found.
        try:
            context = _launch(p, use_chrome=True)
            print(">> Using your installed Google Chrome.")
        except Exception as e:
            print(f">> Chrome unavailable ({e}); using bundled Chromium instead.")
            context = _launch(p, use_chrome=False)

        page = context.pages[0] if context.pages else context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        print("--- FACEBOOK LOGIN SETUP ---")
        print("1. Log in manually (email, password, and 2FA).")
        print("2. If the 2FA page looks blank, click 'Try another way' and choose")
        print("   text message or authentication-app code (the plain input renders fine).")
        print("3. If any page is blank, press F5 / Ctrl+R to reload it.")
        print("4. DO NOT close the browser until you've pressed ENTER below.")
        print("5. Once you can see your Feed/Marketplace, come back here.")

        page.goto("https://www.facebook.com/")

        input("\n>>> Press ENTER in this terminal once you are fully logged in... <<<")

        context.storage_state(path="fb_auth.json")
        print("SUCCESS! Login saved to 'fb_auth.json'. You can close the browser.")

        context.close()


if __name__ == "__main__":
    save_login_state()
