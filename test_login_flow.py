from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = context.new_page()

    print("[1] Opening SkillRack login page...", flush=True)
    page.goto('https://skillrack.com/faces/ui/profile.xhtml', wait_until='commit')

    print("[2] Waiting for login form inputs...", flush=True)
    user_input = page.locator("input[name='j_username']")
    user_input.wait_for(state="visible", timeout=30000)

    print("[3] Filling User ID...", flush=True)
    user_input.fill("2117250080034@rgit")
    page.wait_for_timeout(500)

    print("[4] Filling Password...", flush=True)
    page.locator("input[name='j_password']").fill("jai0011k@")
    page.wait_for_timeout(500)

    print("[5] Clicking Login submit...", flush=True)
    page.locator("input[type='submit']").click()

    print("[6] Waiting for post-login page...", flush=True)
    # Wait for either Programming link or profile page
    page.wait_for_selector("a:has-text('Programming'), a[href*='trackshome.xhtml'], a:has-text('Logout')", timeout=30000)
    print("SUCCESS: Logged in! URL:", page.url, flush=True)

    print("[7] Navigating to Programming -> Level 1 -> Code Tutor...", flush=True)
    page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml']").first.click()
    page.wait_for_timeout(2000)

    page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first.click()
    page.wait_for_timeout(2000)

    page.locator("a[href*='gt=CODETUTOR']").first.click()
    page.wait_for_timeout(2000)

    python_show = page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
    if python_show.is_visible():
        python_show.click()
        page.wait_for_timeout(2000)

    page.locator("button:has-text('Show')").first.click()
    page.wait_for_timeout(2500)
    print("SUCCESS: Reached Hands-on chapters list! URL:", page.url, flush=True)
    page.screenshot(path="hands_on_reached.png")
    time.sleep(3)
    browser.close()
