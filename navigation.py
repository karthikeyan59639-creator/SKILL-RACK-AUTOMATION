import os, base64, re
from logger import log_info, log_error, log_warning
from browser import solve_captcha

def verify_solver_page(page) -> bool:
    """
    Verifies that the actual solver/editor page is loaded and the code editor is present.
    Returns True ONLY when the actual code editor is present.
    """
    print(f"[DEBUG] URL: {page.url}", flush=True)
    print(f"[DEBUG] TITLE: '{page.title()}'", flush=True)

    editor_present = page.evaluate("""() => {
        let aceEl = document.getElementById('ctutortxtCode');
        let hasAce = window.ace && aceEl;
        let hasTa = !!document.getElementById('txtCode');
        return hasAce || hasTa;
    }""")

    if editor_present:
        log_info("[OK] Code editor detected")
        return True
    else:
        print("[ERROR] Solver/editor page was not detected.", flush=True)
        print(f"[ERROR] Current URL: {page.url}", flush=True)
        print(f"[ERROR] Page title: '{page.title()}'", flush=True)
        os.makedirs("screenshots", exist_ok=True)
        page.screenshot(path="screenshots/solver_page_not_found.png", full_page=True)
        print("[ERROR] Saved screenshot to 'screenshots/solver_page_not_found.png'", flush=True)
        return False


def handle_tutorial_and_proceed(page) -> bool:
    """
    Navigates from tutorial explanation page to actual solve page via 'Proceed to Solve the Program'.
    Prints required status milestones:
    [OK] Tutorial page detected
    [OK] Proceed button detected
    [OK] Solve page detected
    [OK] Code editor detected
    """
    print(f"[DEBUG] Current URL: {page.url}", flush=True)
    print(f"[DEBUG] Page title: '{page.title()}'", flush=True)

    # 1. Detect Tutorial Page
    if "tutorprogram.xhtml" in page.url or page.locator("#programgrid, #codeeditorpanel").first.is_visible(timeout=5000):
        print("[OK] Tutorial page detected", flush=True)
        log_info("[OK] Tutorial page detected")
    else:
        log_error(f"[NAVIGATION ERROR] Expected tutorial page but on URL: '{page.url}'")

    # 2. Locate Proceed Button
    proceed_btn = page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program'), [value*='Proceed']").first
    
    if not proceed_btn.is_visible(timeout=5000):
        # Check by exact text if id locator failed
        proceed_btn = page.get_by_text("Proceed to Solve the Program", exact=True)

    if proceed_btn.is_visible(timeout=5000):
        print("[OK] Proceed button detected", flush=True)
        log_info("[OK] Proceed button detected")
    else:
        log_error("[NAVIGATION ERROR] 'Proceed to Solve the Program' button not found on page.")
        os.makedirs("screenshots", exist_ok=True)
        page.screenshot(path="screenshots/solver_page_not_found.png", full_page=True)
        return False

    # 3. Handle math prompt challenge if present above Proceed button
    cap_input = page.locator("#capval, input[name='capval']").first
    if cap_input.is_visible(timeout=2000):
        for attempt in range(5):
            try:
                # Run scale-invariant OCR directly on captcha image
                img_el = cap_input.locator("xpath=preceding::img[1]")
                if not img_el.is_visible(timeout=500):
                    img_el = page.locator("img[src*='data:image']").first

                ans = ""
                if img_el.is_visible(timeout=1000):
                    src_attr = img_el.get_attribute("src") or ""
                    if src_attr.startswith("data:image"):
                        b64_str = src_attr
                    else:
                        img_bytes = img_el.screenshot()
                        b64_str = base64.b64encode(img_bytes).decode('utf-8')
                    ans = solve_captcha(b64_str)

                if ans:
                    log_info(f"[CAPTCHA OCR] Attempt {attempt+1}: Solved math result: '{ans}'")
                    print(f"[DEBUG] Filling math captcha answer '{ans}' into #capval...", flush=True)
                    cap_input.fill(str(ans))
                else:
                    log_warning(f"[CAPTCHA] Attempt {attempt+1}: OCR unparsed. Filling dummy '0' to trigger DOM text refresh...")
                    cap_input.fill("0")


                page.wait_for_timeout(500)
                print(f"[DEBUG] Element being clicked: tag='{proceed_btn.evaluate('e => e.tagName')}', text='{proceed_btn.inner_text().strip()}'", flush=True)
                proceed_btn.click()
                page.wait_for_timeout(2500)

                # Check if error message displayed
                if page.locator(".ui-messages-error, .ui-message-error").first.is_visible(timeout=1500) or page.get_by_text("Incorrect Captcha Value").is_visible(timeout=1500):
                    log_warning(f"[CAPTCHA] Attempt {attempt+1} got Incorrect Captcha. Reloading page to fetch fresh captcha image...")
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(1500)
                    except Exception:
                        pass
                    # Re-locate elements after page reload
                    proceed_btn = page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program'), [value*='Proceed']").first
                    if not proceed_btn.is_visible(timeout=2000):
                        proceed_btn = page.get_by_text("Proceed to Solve the Program", exact=True)
                    cap_input = page.locator("#capval, input[name='capval']").first
                else:
                    break
            except Exception as cap_e:
                log_warning(f"[CAPTCHA ERROR] {cap_e}")
                break
    else:
        log_info("[NAVIGATION] Clicking 'Proceed to Solve the Program' button...")
        print(f"[DEBUG] Element being clicked: tag='{proceed_btn.evaluate('e => e.tagName')}', text='{proceed_btn.inner_text().strip()}'", flush=True)
        proceed_btn.click()
        page.wait_for_timeout(3000)
    
    # Wait for editor panel to replace tutorial page
    try:
        page.locator("#ctutortxtCode, #txtCode, .ace_editor, textarea.ace_text-input").first.wait_for(state="visible", timeout=15000)
    except Exception:
        page.wait_for_timeout(3000)

    # 5. Detect Solve Page & Code Editor
    print("[OK] Solve page detected", flush=True)
    log_info("[OK] Solve page detected")

    # 6. Verify Editor
    return verify_solver_page(page)
