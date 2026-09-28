import os, re, base64, io
from PIL import Image
from playwright.sync_api import sync_playwright
from skill_automation.browser import solve_captcha

def verify_code_editor(page):
    print(f"[DEBUG] Verification URL: {page.url}")
    print(f"[DEBUG] Verification Title: '{page.title()}'")

    editor_present = page.evaluate("""() => {
        let aceEl = document.getElementById('ctutortxtCode');
        let hasAce = window.ace && aceEl && aceEl.offsetWidth > 0;
        let hasTa = !!document.getElementById('txtCode');
        return hasAce || hasTa;
    }""")

    if editor_present:
        print("[DEBUG] SUCCESS: Code editor is present and visible on the page!")
        return True
    else:
        print("[ERROR] Code editor not found.")
        print(f"[ERROR] Current URL: {page.url}")
        print(f"[ERROR] Current title: '{page.title()}'")
        os.makedirs("screenshots", exist_ok=True)
        page.screenshot(path="screenshots/navigation_failure.png", full_page=True)
        print("[ERROR] Saved failure screenshot to 'screenshots/navigation_failure.png'")
        return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state='storage_state.json') if os.path.exists('storage_state.json') else browser.new_context()
    page = context.new_page()

    # 1. Login/Profile
    print("[DEBUG] Step 1: Navigating to Profile...")
    page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[DEBUG] URL: {page.url} | Title: '{page.title()}'")

    if page.locator("input[name='j_username']").is_visible():
        page.locator("input[name='j_username']").fill("2117250080034@rgit")
        page.locator("input[name='j_password']").fill("jai0011k@")
        page.locator("input[type='submit']").click()
        page.wait_for_timeout(3000)
        context.storage_state(path='storage_state.json')

    # 2. Programming Track
    print("[DEBUG] Step 2: Clicking Programming track...")
    prog = page.locator("a[href*='trackshome.xhtml']").first
    print(f"[DEBUG] Element: text='{prog.inner_text().strip()}', href='{prog.get_attribute('href')}'")
    prog.click()
    page.wait_for_timeout(1500)
    print(f"[DEBUG] URL: {page.url} | Title: '{page.title()}'")

    # 3. Level 1
    print("[DEBUG] Step 3: Clicking Level 1...")
    lvl1 = page.locator("a[href*='lev1.xhtml']").first
    print(f"[DEBUG] Element: text='{lvl1.inner_text().strip()}', href='{lvl1.get_attribute('href')}'")
    lvl1.click()
    page.wait_for_timeout(1500)
    print(f"[DEBUG] URL: {page.url} | Title: '{page.title()}'")

    # 4. Code Tutor
    print("[DEBUG] Step 4: Clicking Code Tutor...")
    tutor = page.locator("a[href*='codeprogramgroup.xhtml?gt=CODETUTOR']").first
    print(f"[DEBUG] Element: text='{tutor.inner_text().strip()}', href='{tutor.get_attribute('href')}'")
    tutor.click()
    page.wait_for_timeout(1500)
    print(f"[DEBUG] URL: {page.url} | Title: '{page.title()}'")

    # 5. Python Programming Show button
    print("[DEBUG] Step 5: Clicking Python Programming Show button...")
    py_row = page.locator("tr").filter(has_text="Python Programming")
    py_show = py_row.locator("button:has-text('Show'), input[value='Show'], a:has-text('Show')").first
    print(f"[DEBUG] Element: tag='{py_show.evaluate('e => e.tagName')}', text='{py_show.inner_text().strip()}'")
    py_show.click()
    page.wait_for_timeout(1500)
    print(f"[DEBUG] URL: {page.url} | Title: '{page.title()}'")

    # 6. Hands-On Course Show button
    print("[DEBUG] Step 6: Opening Hands-On Course Overview...")
    hands_on_btn = page.locator("button:has-text('Show'), input[value='Show']").first
    print(f"[DEBUG] Element: tag='{hands_on_btn.evaluate('e => e.tagName')}', text='{hands_on_btn.inner_text().strip()}'")
    hands_on_btn.click()
    page.wait_for_timeout(2000)
    print(f"[DEBUG] URL: {page.url} | Title: '{page.title()}'")

    # 7. Chapter View button (EXCLUDING LeaderBoard)
    print("[DEBUG] Step 7: Opening active chapter View button (EXCLUDING LeaderBoard)...")
    view_btn = page.locator("button, a, input").filter(has_text=re.compile(r"^\s*(View|Resume)\s*$", re.I)).first
    print(f"[DEBUG] Element: tag='{view_btn.evaluate('e => e.tagName')}', text='{view_btn.inner_text().strip()}'")
    view_btn.click()
    page.wait_for_timeout(3000)

    # Solve captcha on tutorprogram.xhtml if visible
    try:
        img_el = page.locator("#codeeditorpanel img").first
        if img_el.is_visible(timeout=3000):
            print("[DEBUG] Captcha detected on tutorprogram.xhtml. Solving captcha...")
            src = img_el.get_attribute("src")
            ans = solve_captcha(src)
            print(f"[DEBUG] Solved captcha result: '{ans}'")
            page.locator("#capval").fill(ans)
            page.locator("#proceedbtn").click()
            page.wait_for_timeout(3000)
    except Exception as cap_e:
        print(f"[DEBUG] Captcha check info: {cap_e}")

    # 8. Verify Code Editor
    print("[DEBUG] Step 8: Verifying Code Editor...")
    editor_ok = verify_code_editor(page)

    browser.close()
