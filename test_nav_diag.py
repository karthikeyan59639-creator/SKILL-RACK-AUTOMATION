from playwright.sync_api import sync_playwright

print("Starting Playwright navigation test...", flush=True)
with sync_playwright() as p:
    print("Launching chromium...", flush=True)
    browser = p.chromium.launch(headless=True)
    print("Creating context & page...", flush=True)
    page = browser.new_page()

    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}", flush=True))
    page.on("pageerror", lambda err: print(f"PAGEERROR: {err}", flush=True))
    page.on("requestfailed", lambda req: print(f"REQFAILED: {req.url} -> {req.failure}", flush=True))

    print("Executing page.goto('https://skillrack.com/faces/ui/profile.xhtml')...", flush=True)
    resp = page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="commit", timeout=30000)
    print(f"HTTP STATUS: {resp.status if resp else 'None'}", flush=True)
    print(f"URL: {page.url}", flush=True)
    print(f"TITLE: {page.title()}", flush=True)
    page.wait_for_timeout(2000)
    print("Body text snippet:\n", repr(page.locator("body").inner_text()[:300]), flush=True)
    page.screenshot(path="skillrack_debug.png", full_page=True)
    browser.close()
    print("Test finished successfully!", flush=True)
