"""
import_cookies.py
-----------------
Build fb_auth.json from cookies in your NORMAL browser — no automation browser,
so Facebook's 2FA never has to render inside Playwright.

Two ways to use it:

  A) AUTO (tries to read cookies straight from your browser):
       pip install browser_cookie3
       python import_cookies.py
     May fail on the very newest Chrome (app-bound cookie encryption). If so, use B.

  B) MANUAL (always works):
     1. In your normal browser, make sure you're logged into facebook.com.
     2. Press F12 -> Application tab -> Storage -> Cookies -> https://www.facebook.com
     3. Find the rows named  c_user  and  xs  and copy each "Value".
     4. Run:  python import_cookies.py --manual
        Paste the values when prompted.
"""

import json
import sys
import time

AUTH_FILE = "fb_auth.json"
FAR_FUTURE = time.time() + 365 * 24 * 3600


def _cookie(name, value, http_only=True):
    return {
        "name": name,
        "value": value,
        "domain": ".facebook.com",
        "path": "/",
        "expires": FAR_FUTURE,
        "httpOnly": http_only,
        "secure": True,
        "sameSite": "None",
    }


def _write(cookies):
    state = {"cookies": cookies, "origins": []}
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    names = ", ".join(sorted(c["name"] for c in cookies))
    print(f"\nSUCCESS! Wrote {AUTH_FILE} with cookies: {names}")
    print("Now run the scraper:  python gui_scraper.py")


def manual():
    print("--- MANUAL COOKIE IMPORT ---")
    print("In your normal browser (logged into Facebook):")
    print("  F12 -> Application -> Cookies -> https://www.facebook.com")
    print("Copy the 'Value' for c_user and xs.\n")
    c_user = input("Paste c_user value: ").strip()
    xs = input("Paste xs value: ").strip()
    datr = input("Paste datr value (optional, Enter to skip): ").strip()

    if not c_user or not xs:
        print("!! c_user and xs are both required. Aborting.")
        sys.exit(1)

    cookies = [
        _cookie("c_user", c_user, http_only=False),
        _cookie("xs", xs, http_only=True),
    ]
    if datr:
        cookies.append(_cookie("datr", datr, http_only=True))
    _write(cookies)


def auto():
    try:
        import browser_cookie3
    except ImportError:
        print("browser_cookie3 not installed. Either:")
        print("   pip install browser_cookie3      (then re-run)")
        print("   python import_cookies.py --manual  (no install needed)")
        sys.exit(1)

    loaders = [
        ("Chrome", browser_cookie3.chrome),
        ("Edge", browser_cookie3.edge),
        ("Firefox", browser_cookie3.firefox),
        ("Brave", browser_cookie3.brave),
    ]
    for name, loader in loaders:
        try:
            jar = loader(domain_name="facebook.com")
            cookies = [
                _cookie(c.name, c.value, http_only=False)
                for c in jar
                if c.name in ("c_user", "xs", "datr", "fr")
            ]
            have = {c["name"] for c in cookies}
            if "c_user" in have and "xs" in have:
                print(f">> Found Facebook cookies in {name}.")
                _write(cookies)
                return
        except Exception:
            continue

    print("Couldn't auto-read cookies (newest Chrome encrypts them).")
    print("Use the manual method instead:  python import_cookies.py --manual")
    sys.exit(1)


if __name__ == "__main__":
    if "--manual" in sys.argv:
        manual()
    else:
        auto()
