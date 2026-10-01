"""
c_orchestrator.py - Autonomous Solver for SkillRack C Programming Code Tutor
Navigates: CODETUTOR -> C Programming -> C - Programming Course (Hands-On) -> C-H001 to C-H029
Extracts problem, handles math captchas, synthesizes C code with Gemini, injects into Ace/CodeMirror,
executes via gcc 8.x, detects results, and advances sequentially.
"""
import os
import re
import json
import time
import base64
from datetime import datetime

from config import (
    HEADLESS, MAX_ATTEMPTS, ACTION_DELAY_MS,
    FAILURES_DIR, SCREENSHOTS_DIR, DEBUG_DIR,
    CLOSE_BROWSER_ON_FINISH
)
from logger import log_info, log_warning, log_error
from auth import verify_project_access
from skill_automation.browser_manager import BrowserManager, solve_captcha_image
from problem_scraper import scrape_problem, parse_problem_text
from editor import get_editor_context, set_code, get_code, wait_for_editor_visible, normalize_code
from runner import run_code_and_get_result
from solver import solve_c_problem, cache_passed_solution, get_cached_solution
from progress import ProgressManager


TOTAL_C_CHAPTERS = 29


def solve_captcha_if_needed(page, bm, max_attempts=5) -> bool:
    """Detects and solves the captcha on problem page if present."""
    cap_input = page.locator("#capval, input[name='capval']").first
    proceed_btn = page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program')").first

    # Check if editor is already visible
    has_editor = page.evaluate("""() => {
        let ace = document.querySelector('.ace_editor');
        let cm = document.querySelector('.CodeMirror');
        let txt = document.querySelector('#ctutortxtCode');
        return Boolean((ace && ace.offsetParent !== null) || (cm && cm.offsetParent !== null) || (txt && txt.offsetParent !== null));
    }""")
    if has_editor:
        return True

    if not cap_input.is_visible(timeout=2500):
        if proceed_btn.is_visible(timeout=1500):
            log_info("[CAPTCHA] Proceed button visible without captcha. Clicking...")
            proceed_btn.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2500)
        return True

    log_info("[CAPTCHA] Math challenge detected. Solving...")
    for attempt in range(1, max_attempts + 1):
        has_ed = page.evaluate("""() => {
            let ace = document.querySelector('.ace_editor');
            let cm = document.querySelector('.CodeMirror');
            let txt = document.querySelector('#ctutortxtCode');
            return Boolean((ace && ace.offsetParent !== null) || (cm && cm.offsetParent !== null) || (txt && txt.offsetParent !== null));
        }""")
        if has_ed:
            return True

        img_el = page.locator("img[src*='data:image']").first
        ans = ""
        if img_el.is_visible(timeout=2000):
            try:
                raw_bytes = img_el.screenshot()
                _, ans = solve_captcha_image(raw_bytes)
            except Exception as e:
                log_warning(f"[CAPTCHA] Screenshot error: {e}")

        if not ans:
            dom_cap = bm.read_captcha_from_dom()
            if dom_cap:
                ans = dom_cap

        if not ans:
            ans = str(10 + attempt)

        log_info(f"[CAPTCHA] Attempt {attempt}/{max_attempts}: Submitting '{ans}'...")
        try:
            if not cap_input.is_visible(timeout=2000):
                break
            cap_input.fill(ans, timeout=2000)
            page.wait_for_timeout(250)
            if proceed_btn.is_visible(timeout=1500):
                proceed_btn.click()
        except Exception as e:
            log_warning(f"[CAPTCHA] Click/fill exception: {e}")

        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)

        # Re-check editor presence
        has_ed_now = page.evaluate("""() => {
            let ace = document.querySelector('.ace_editor');
            let cm = document.querySelector('.CodeMirror');
            let txt = document.querySelector('#ctutortxtCode');
            return Boolean((ace && ace.offsetParent !== null) || (cm && cm.offsetParent !== null) || (txt && txt.offsetParent !== null));
        }""")
        if has_ed_now:
            log_info("[CAPTCHA SUCCESS] Editor widget revealed!")
            return True

        # If refresh button visible, click it
        ref_btn = page.locator("a[id*='refresh'], button[id*='refresh'], .pi-refresh").first
        if ref_btn.is_visible(timeout=1000):
            ref_btn.click()
            page.wait_for_timeout(1500)

    return False


def wait_for_stale_pid_change(page, prev_pid: str, timeout_sec: int = 25) -> str:
    """Waits until the ProgramID badge text changes from prev_pid, or chapter ends/tutorial appears."""
    if not prev_pid:
        return ""
    log_info(f"[GUARD] Waiting for ProgramID to change from '{prev_pid}'...")
    start = time.time()
    while time.time() - start < timeout_sec:
        # Check if chapter finished
        if is_chapter_finished(page) or "codeprogramgroup.xhtml" in page.url:
            return ""
        # Check if tutorial proceed button appeared
        tut_btn = page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program')").first
        if tut_btn.is_visible(timeout=300):
            log_info("[GUARD] Tutorial proceed button detected during transition.")
            return "tutorial"

        cur_pid = page.evaluate("""() => {
            let text = document.body ? document.body.innerText : '';
            let m = text.match(/ProgramID-\\s*(\\d+)/);
            return m ? m[1] : '';
        }""")
        if cur_pid and cur_pid != prev_pid:
            log_info(f"[GUARD] ProgramID changed: '{prev_pid}' -> '{cur_pid}'")
            return cur_pid
        page.wait_for_timeout(400)

    log_warning(f"[GUARD] ProgramID did not change from '{prev_pid}' within {timeout_sec}s.")
    return ""


def navigate_to_c_hands_on_overview(page) -> bool:
    """Navigates to CODETUTOR -> C Programming -> C - Programming Course (Hands-On)."""
    log_info("[NAV] Loading fresh CODETUTOR overview...")
    page.goto("https://skillrack.com/faces/candidate/codeprogramgroup.xhtml?gt=CODETUTOR")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)

    # Expand C Programming
    c_btn = page.locator("tr").filter(has_text="C Programming").locator("button").first
    try:
        c_btn.wait_for(state="visible", timeout=8000)
        log_info("[NAV] Expanding 'C Programming'...")
        c_btn.click()
    except Exception as e:
        log_warning(f"[NAV] C Programming button wait failed: {e}")

    # Expand C - Programming Course (Hands-On)
    try:
        hands_on_btn = page.locator("tr").filter(has_text="C - Programming Course (Hands-On)").locator("button").first
        hands_on_btn.wait_for(state="visible", timeout=12000)
        log_info("[NAV] Expanding 'C - Programming Course (Hands-On)'...")
        hands_on_btn.click()
    except Exception as e:
        log_error(f"[NAV] Could not locate 'C - Programming Course (Hands-On)' Show button: {e}")
        return False

    # Wait for cards to appear
    try:
        first_card = page.locator(".ui-datagrid-column").first
        first_card.wait_for(state="visible", timeout=15000)
        return True
    except Exception as e:
        log_error(f"[NAV] Chapter cards did not appear within 15s: {e}")
        return False


def is_chapter_finished(page) -> bool:
    """Checks if the chapter completion banner or screen is currently visible."""
    return page.evaluate("""() => {
        let text = document.body ? document.body.innerText : '';
        return text.includes('successfully completed the programming course') ||
               text.includes('successfully completed') ||
               text.includes('Course Completed') ||
               text.includes('completed this chapter') ||
               text.includes('completed all the programs in this chapter') ||
               text.includes('All units in this chapter have been completed') ||
               text.includes('All programs in this track are completed');
    }""")


def solve_current_c_exercise(page, bm, progress_mgr: ProgressManager) -> tuple[bool, str]:
    """
    Scrapes, solves via Gemini C model, injects, runs, and checks outcome for current exercise.
    Returns (success: bool, pid: str).
    """
    pdata = scrape_problem(page)
    pid = pdata.get("program_id", "")
    title = pdata.get("title", "C Exercise")
    statement = pdata.get("statement", "")
    sample_io = pdata.get("sample_io", [])
    constraints = pdata.get("constraints", "")

    if not pid:
        m = re.search(r"ProgramID-\s*(\d+)", page.evaluate("() => document.body ? document.body.innerText : ''"))
        pid = m.group(1) if m else f"auto_{int(time.time())}"

    log_info("\n" + "=" * 65)
    log_info(f"[SOLVING C EXERCISE] PID: {pid} | Title: '{title}'")
    log_info("=" * 65)

    # Check if already completed / Proceed Next visible
    proceed_next = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value*='Proceed Next']").first
    if proceed_next.is_visible(timeout=1000):
        log_info("[EXERCISE] 'Proceed Next' is already active! Marking as passed.")
        progress_mgr.record_passed(pid, "ALREADY_SOLVED", 0)
        progress_mgr.save()
        return True, pid

    # Check cached solution
    cached_code = get_cached_solution(pid)
    if cached_code:
        log_info(f"[SOLVER CACHE] Reusing cached passed solution for PID-{pid}...")
        set_code(page, cached_code)
        res = run_code_and_get_result(page, timeout_sec=35)
        if res.get("passed"):
            return True, pid

    # Read editor context (prefix, suffix, editor_val)
    ctx = get_editor_context(page)
    prefix = ctx.get("prefix", "")
    suffix = ctx.get("suffix", "")
    current_code = ctx.get("editor_val", "")

    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log_info(f"[SOLVER] Generating C solution (attempt {attempt}/{MAX_ATTEMPTS})...")
        solved_code = solve_c_problem(
            statement=statement,
            title=title,
            sample_io=sample_io,
            constraints=constraints,
            prefix=prefix,
            suffix=suffix,
            current_code=current_code,
            max_retries=2,
            external_feedback=feedback
        )

        if not solved_code:
            log_warning(f"[SOLVER] Attempt {attempt} produced empty code. Retrying...")
            continue

        log_info(f"[INJECT] Writing C solution into editor...")
        set_ok = set_code(page, solved_code)
        if not set_ok:
            log_warning(f"[INJECT] Code injection could not be verified in editor. Continuing to Run...")

        page.wait_for_timeout(400)

        # Run code on SkillRack
        run_res = run_code_and_get_result(page, timeout_sec=40)
        if run_res.get("passed"):
            log_info(f"[SUCCESS] Exercise PID-{pid} PASSED on attempt {attempt}!")
            progress_mgr.record_passed(pid, solved_code, attempt)
            progress_mgr.save()
            cache_passed_solution(pid, solved_code)
            return True, pid
        else:
            feedback = page.evaluate("""() => {
                let body = document.body ? document.body.innerText : '';
                let idx = body.indexOf('Code did not pass the execution');
                if (idx !== -1) return body.substring(idx, idx + 800);
                let srmsg = document.querySelector('#srmsg');
                return srmsg ? srmsg.innerText : '';
            }""")
            log_warning(f"[RETRY] Attempt {attempt} failed on judge. Platform feedback:\n{feedback[:300]}")

    log_error(f"[FAILURE] Exercise PID-{pid} failed after {MAX_ATTEMPTS} attempts.")
    return False, pid


def run_c_chapter(page, bm, progress_mgr: ProgressManager, chapter_idx: int, chapter_title: str, btn_id: str = "") -> int:
    """
    Opens chapter_idx, solves all its exercises sequentially until the chapter completes.
    Returns the count of exercises solved in this chapter.
    """
    log_info("\n" + "#" * 70)
    log_info(f"  STARTING CHAPTER: {chapter_title}")
    log_info("#" * 70 + "\n")

    # Locate the View button
    view_btn = None
    if btn_id:
        view_btn = page.locator(f"[id='{btn_id}']").first
    if not view_btn or not view_btn.is_visible(timeout=2000):
        view_btn = page.locator("[id*='cttbl:0:'] button:has-text('View'), [id*='cttbl:0:'] a:has-text('View')").first
    if not view_btn or not view_btn.is_visible(timeout=2000):
        view_btn = page.locator(".ui-datagrid-column").filter(has_text="C-H").first.locator("button:has-text('View')").first

    if not view_btn.is_visible(timeout=4000):
        log_error(f"[CHAPTER] Could not locate View button for '{chapter_title}'!")
        return 0

    log_info(f"[CHAPTER] Clicking View for '{chapter_title}'...")
    view_btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3000)

    # Solve captcha if needed
    solve_captcha_if_needed(page, bm)

    solved_count = 0
    prev_pid = None

    while True:
        # Check if chapter completion screen appeared
        if is_chapter_finished(page):
            log_info(f"[CHAPTER COMPLETE] Chapter '{chapter_title}' finished all units!")
            break

        # Check if on course overview or redirected back
        if "codeprogramgroup.xhtml" in page.url:
            log_info(f"[CHAPTER COMPLETE] Returned to course overview. Chapter finished!")
            break

        # Solve captcha / tutorial proceed button if visible
        solve_captcha_if_needed(page, bm)

        # Ensure editor is visible
        try:
            wait_for_editor_visible(page, timeout_ms=10000)
        except Exception:
            tut_proceed = page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program'), button:has-text('Proceed')").first
            if tut_proceed.is_visible(timeout=2000):
                tut_proceed.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)

        # Solve current problem
        passed, pid = solve_current_c_exercise(page, bm, progress_mgr)
        if passed:
            solved_count += 1
            prev_pid = pid

            # Click Proceed Next
            proceed_next = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value*='Proceed Next']").first
            if proceed_next.is_visible(timeout=6000):
                log_info("[NAV] Clicking 'Proceed Next'...")
                proceed_next.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2500)

                # Check if tutorial proceed button appeared
                tut_btn = page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program')").first
                if tut_btn.is_visible(timeout=2000):
                    tut_btn.click()
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2000)

                # Enforce stale state change
                new_pid = wait_for_stale_pid_change(page, prev_pid, timeout_sec=20)
                if not new_pid:
                    log_info(f"[CHAPTER FINISHED] No new PID detected after Proceed Next. Returning to overview for '{chapter_title}'.")
                    break
            else:
                log_info("[NAV] 'Proceed Next' not found. Checking if chapter completed...")
                if is_chapter_finished(page) or "codeprogramgroup.xhtml" in page.url:
                    break
                back_btn = page.locator("button:has-text('Back'), a:has-text('Back')").first
                if back_btn.is_visible(timeout=2000):
                    back_btn.click()
                    page.wait_for_load_state("domcontentloaded")
                    break
        else:
            log_warning(f"[CHAPTER] Exercise PID-{pid} could not be solved. Advancing to next if possible...")
            proceed_next = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value*='Proceed Next']").first
            if proceed_next.is_visible(timeout=3000):
                proceed_next.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2500)
            else:
                log_info("[CHAPTER] Cannot advance. Returning to chapter list...")
                break

    return solved_count


def start_c_automation():
    """Main entry point to run autonomous solver across all C programming chapters."""
    verify_project_access()
    log_info("\n" + "=" * 70)
    log_info("  SKILLRACK C PROGRAMMING AUTONOMOUS CODE TUTOR SOLVER")
    log_info("  Track: C - Programming Course (Hands-On) [29 Chapters]")
    log_info(f"  Mode: Headless={HEADLESS} | Provider=Gemini")
    log_info("=" * 70 + "\n")

    bm = BrowserManager(headless=True)
    page = bm.start()
    bm.login_and_navigate()
    progress_mgr = ProgressManager()

    total_c_solved = 0

    try:
        while True:
            # Always ensure on hands-on overview
            ok = navigate_to_c_hands_on_overview(page)
            if not ok:
                log_error("[FATAL] Could not reach C Hands-On overview. Exiting...")
                break

            # Find next unfinished chapter in cttbl
            chapter_info = page.evaluate("""() => {
                let cards = Array.from(document.querySelectorAll('.ui-datagrid-column')).filter(el => {
                    let t = el.innerText || '';
                    let isCttbl = el.closest('[id*="cttbl"]') !== null || Boolean(el.querySelector('[id*="cttbl"]'));
                    return isCttbl && t.includes('C-H') && t.includes('Units:');
                });
                if (cards.length === 0) return null;

                let c = cards[0];
                let btn = c.querySelector('button');
                let t = (c.innerText || '').replace(/\\s+/g, ' ').trim();
                return {
                    index: 0,
                    title: t.substring(0, 60),
                    btnId: btn ? btn.id : '',
                    remainingCount: cards.length
                };
            }""")

            if not chapter_info:
                log_info("[ALL CHAPTERS COMPLETE] All C Programming chapters have reached 100%!")
                break

            ch_title = chapter_info['title']
            ch_idx = chapter_info['index']
            btn_id = chapter_info['btnId']
            rem_count = chapter_info['remainingCount']

            log_info(f"\n--- [NEXT UNFINISHED CHAPTER] ({rem_count} remaining in Currently Learning) ---")
            log_info(f"    Title: {ch_title}")
            log_info(f"    Card Index: {ch_idx} | Button ID: {btn_id}")

            solved_in_ch = run_c_chapter(page, bm, progress_mgr, ch_idx, ch_title, btn_id)
            total_c_solved += solved_in_ch
            log_info(f"[PROGRESS] Solved {solved_in_ch} in this chapter. Total C exercises solved: {total_c_solved}\n")

        log_info("\n" + "=" * 70)
        log_info(f"[ALL C CHAPTERS COMPLETED] Solved {total_c_solved} C exercises across all chapters!")
        log_info("=" * 70 + "\n")

    except Exception as e:
        log_error(f"[FATAL EXCEPTION] Automation error in C solver: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if CLOSE_BROWSER_ON_FINISH:
            bm.close()
        else:
            log_info("[BROWSER] Automation run complete. Keeping session for review.")
            bm.close()


if __name__ == "__main__":
    verify_project_access()
    start_c_automation()
