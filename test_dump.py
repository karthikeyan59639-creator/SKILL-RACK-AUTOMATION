from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto('https://skillrack.com/faces/ui/profile.xhtml', wait_until='commit')
    time.sleep(6)
    html = page.content()
    with open("page_dump.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Page dump saved! Length:", len(html))
    browser.close()
