from playwright.sync_api import sync_playwright
import sys

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto("https://skillrack.com/faces/ui/profile.xhtml")

        print("Page title:", page.title(), flush=True)

        username_box = page.locator("input[name='j_username']")
        password_box = page.locator("input[name='j_password']")
        login_button = page.locator("input[type='submit']")

        print("Found username box:", username_box.is_visible(), flush=True)
        print("Found password box:", password_box.is_visible(), flush=True)
        print("Found login button:", login_button.is_visible(), flush=True)

        page.wait_for_timeout(2000)
        browser.close()

    print("SCRIPT FINISHED SUCCESSFULLY", flush=True)

except Exception as e:
    print("ERROR OCCURRED:", e, flush=True)
    sys.exit(1)