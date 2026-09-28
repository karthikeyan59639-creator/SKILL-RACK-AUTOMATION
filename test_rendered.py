from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto('https://skillrack.com/faces/ui/profile.xhtml', wait_until='commit')
    page.locator("input[type='text'], input[type='password'], input[name='j_username']").first.wait_for(state="visible", timeout=30000)
    html = page.content()
    with open("full_page_rendered.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Full rendered HTML saved! Length:", len(html))
    browser.close()
