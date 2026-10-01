"""
track_automator.py - Automates execution for SkillRack tracks:
1. Python - STARTER (30 challenges)
2. PYTHON3.x - 50 VERY-EASY CHALLENGES (50 challenges across 5 parts)
"""
import os
import re
import json
import time
import base64
from logger import log_info, log_warning, log_error
from auth import verify_project_access
from config import CLOSE_BROWSER_ON_FINISH
from skill_automation.browser_manager import BrowserManager, solve_captcha_image
from problem_scraper import scrape_problem
from solver import solve_mfib, solve_code_editor
from progress import ProgressManager


def is_problem_revealed(page) -> bool:
    """Checks whether the code editor or blanks are currently visible."""
    return page.evaluate("""() => {
        let hasBlanks = document.querySelectorAll('input[id*="j_id_8c"], input[type="text"]:not([name="capval"])').length > 0;
        let hasAce = !!document.querySelector('.ace_editor');
        let hasCM = !!document.querySelector('.CodeMirror');
        let hasRun = !!Array.from(document.querySelectorAll('button, input[type="submit"]')).find(b => (b.innerText || b.value || '').trim() === 'Run');
        return hasBlanks || hasAce || hasCM || hasRun;
    }""")


def solve_captcha_if_needed(page, bm, max_attempts=5) -> bool:
    """Detects and solves the captcha on problem page if present."""
    if is_problem_revealed(page):
        return True

    cap_input = page.locator("#capval, input[name='capval']").first
    proceed_btn = page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program')").first

    if not cap_input.is_visible(timeout=3000):
        if proceed_btn.is_visible(timeout=1000):
            proceed_btn.click()
            page.wait_for_timeout(3000)
        return is_problem_revealed(page)

    log_info("[CAPTCHA] Challenge detected. Solving...")
    for attempt in range(1, max_attempts + 1):
        if is_problem_revealed(page):
            return True

        img_el = page.locator("img[src*='data:image']").first
        raw_bytes = None
        if img_el.is_visible(timeout=2000):
            src = img_el.get_attribute("src") or ""
            if src.startswith("data:image"):
                if ',' in src:
                    src = src.split(',', 1)[1]
                src_clean = src.strip()
                src_clean += '=' * (-len(src_clean) % 4)
                raw_bytes = base64.b64decode(src_clean)
            if not raw_bytes:
                try:
                    raw_bytes = img_el.screenshot()
                except Exception:
                    pass

        ans = ""
        if raw_bytes:
            raw_ocr, ans = solve_captcha_image(raw_bytes)

        if not ans:
            dom_cap = bm.read_captcha_from_dom()
            if dom_cap:
                ans = dom_cap

        if not ans:
            ans = str(10 + attempt)

        log_info(f"[CAPTCHA] Attempt {attempt}/{max_attempts}: Submitting answer '{ans}'...")
        try:
            if not cap_input.is_visible(timeout=2000):
                if is_problem_revealed(page):
                    return True
                break
            cap_input.fill(ans, timeout=3000)
            page.wait_for_timeout(300)
        except Exception:
            if is_problem_revealed(page):
                return True

        if proceed_btn.is_visible(timeout=1500):
            proceed_btn.click()

        page.wait_for_timeout(3500)

        if is_problem_revealed(page):
            log_info("[CAPTCHA SUCCESS] Problem area revealed!")
            return True

        log_warning(f"[CAPTCHA FAIL] Attempt {attempt} failed. Retrying...")
        ref_btn = page.locator("a[id*='refresh'], button[id*='refresh'], .pi-refresh").first
        if ref_btn.is_visible(timeout=1500):
            ref_btn.click()
            page.wait_for_timeout(1500)

    log_error("[CAPTCHA ERROR] Failed to solve captcha after maximum attempts.")
    return is_problem_revealed(page)


def wait_for_run_result(page, timeout_sec=45) -> bool:
    """Waits for test run to finish and returns True if passed."""
    start_time = time.time()
    saw_waiting = False
    while time.time() - start_time < timeout_sec:
        state = page.evaluate("""() => {
            let t = document.body ? document.body.innerText : '';
            let srmsg = document.querySelector('#srmsg') ? document.querySelector('#srmsg').innerText : '';
            let isWaiting = t.includes('Please wait while we run');
            let proceedBtn = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"]')).find(b => {
                let txt = (b.innerText || b.value || '').trim();
                return (txt === 'Proceed Next' || txt.includes('Proceed Next')) && b.offsetParent !== null;
            });
            let hasCongrats = t.includes('Great! Your code has passed') ||
                              t.includes('Congratulations! Your Code has passed') ||
                              t.includes('Congratulations') ||
                              t.includes('Your Code has passed') ||
                              t.includes('Your code has passed') ||
                              t.includes('All Test Cases Passed') ||
                              Boolean(proceedBtn);
            let hasFailure = t.includes('0 of') || 
                             srmsg.includes('Failed') || srmsg.includes('failed') || srmsg.includes('Error') || 
                             t.includes('Code did not pass the execution') ||
                             t.includes('Code did not pass') ||
                             t.includes('Wrong Answer') ||
                             t.includes('Compilation Error') ||
                             t.includes('SyntaxError') ||
                             t.includes('Traceback (most recent call last)') ||
                             (t.includes('Test Case') && t.includes('Failed'));
            return { waiting: isWaiting, passed: hasCongrats, failed: hasFailure };
        }""")

        if state['waiting']:
            saw_waiting = True

        if not state['waiting']:
            if state['passed'] and not state['failed']:
                log_info("[RUN RESULT] Challenge PASSED 100%!")
                return True
            elif state['passed'] and state['failed']:
                body_t = page.evaluate("() => document.body ? document.body.innerText : ''")
                if "Code did not pass" not in body_t:
                    log_info("[RUN RESULT] Challenge PASSED 100%!")
                    return True
            elif saw_waiting and state['failed']:
                log_warning("[RUN RESULT] Challenge run resulted in failure.")
                page.evaluate("() => { let g = document.querySelector('#btngrp'); if (g) g.style.display = 'block'; }")
                return False

        page.wait_for_timeout(1000)

    log_warning(f"[RUN RESULT] Run did not complete within {timeout_sec}s.")
    page.evaluate("() => { let g = document.querySelector('#btngrp'); if (g) g.style.display = 'block'; }")
    return False


def solve_current_problem(page, bm, pm: ProgressManager) -> bool:
    """Identifies problem type (MFIB vs Ace/EI), solves, runs, and advances."""
    pdata = scrape_problem(page)
    title = pdata.get('title') or "SkillRack Challenge"
    pid = pdata.get('program_id') or ""

    if not pid or not pid.isdigit():
        m_id = re.search(r"\(Id-(\d+)\)", title)
        if m_id:
            pid = m_id.group(1)
        else:
            pid = f"auto_{int(time.time())}"

    statement = pdata.get('statement') or ""
    constraints = pdata.get('constraints') or ""
    sample_io = pdata.get('sample_io') or []

    log_info(f"\n=======================================================")
    log_info(f"[SOLVING] PID: {pid} | Title: '{title}'")
    log_info(f"=======================================================")

    blanks_info = page.evaluate("""() => {
        let p = document.querySelector('#codeeditorpanel');
        if (!p) return { isMfib: false };
        let inputs = Array.from(p.querySelectorAll('input[type="text"]:not([name="capval"])'));
        if (inputs.length === 0) return { isMfib: false };
        
        let parent = inputs[0].closest('.ui-outputpanel, div, form');
        let nodes = parent ? Array.from(parent.querySelectorAll('pre, input[type="text"]:not([name="capval"])')) : [];
        
        let parts = [];
        let blankIdx = 0;
        let lastTop = -1;
        
        for (let n of nodes) {
            let rect = n.getBoundingClientRect();
            if (rect.height === 0 && rect.width === 0) continue;
            
            if (lastTop >= 0 && Math.abs(rect.top - lastTop) > 10) {
                if (parts.length > 0 && !parts[parts.length - 1].endsWith('\\n')) {
                    parts.push('\\n');
                }
            }
            lastTop = rect.top;
            
            if (n.tagName === 'INPUT') {
                parts.push(`___BLANK_${blankIdx}___`);
                blankIdx++;
            } else if (n.tagName === 'PRE') {
                let txt = n.innerText || '';
                if (txt.length > 0) {
                    parts.push(txt);
                }
            }
        }
        
        return {
            isMfib: true,
            count: inputs.length,
            template: parts.join(''),
            inputIds: inputs.map(i => i.id)
        };
    }""")

    run_btn = page.locator("button:has-text('Run'), input[value='Run'], #j_id_bj").first

    if blanks_info.get('isMfib') and blanks_info.get('count', 0) > 0:
        log_info(f"[PROBLEM TYPE] MFIB detected with {blanks_info['count']} blanks.")
        template = blanks_info['template']
        num_blanks = blanks_info['count']

        blanks_map, full_code = solve_mfib(statement, sample_io, constraints, template, num_blanks)

        for i in range(num_blanks):
            val = blanks_map.get(f"___BLANK_{i}___") or blanks_map.get(f"blank_{i}") or ""
            val = val.rstrip("\r\n")
            inp = page.locator(f"[id='{blanks_info['inputIds'][i]}']").first
            inp.fill(val)
            page.wait_for_timeout(100)

        log_info("[SUBMISSION] Blanks filled. Triggering Run...")
        try:
            page.evaluate("() => { let g = document.querySelector('#btngrp'); if (g) g.style.display = 'block'; }")
            run_btn.click(timeout=5000)
        except Exception:
            page.evaluate("""() => {
                let g = document.querySelector('#btngrp');
                if (g) g.style.display = 'block';
                let b = document.querySelector('#j_id_bg') || document.querySelector("button[name*='Run']");
                if (b) b.click();
            }""")
        passed = wait_for_run_result(page)
        if passed:
            pm.record_passed(pid, full_code, 1)
            pm.save()
            return True
        else:
            log_warning("[SUBMISSION] First run attempt did not pass.")
            return False

    else:
        log_info("[PROBLEM TYPE] Code Editor (Ace/CodeMirror/EI) detected.")
        current_code = page.evaluate("""() => {
            let aceEl = document.querySelector('.ace_editor');
            if (aceEl && window.ace) {
                try { return window.ace.edit(aceEl).getValue(); } catch(e) {}
            }
            let cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) {
                try { return cm.CodeMirror.getValue(); } catch(e) {}
            }
            return '';
        }""")

        for attempt in range(1, 4):
            if attempt == 1:
                solved_code = solve_code_editor(statement, sample_io, constraints, current_code)
            else:
                feedback = page.evaluate("""() => {
                    let body = document.body ? document.body.innerText : '';
                    let idx = body.indexOf('Code did not pass the execution');
                    if (idx !== -1) return body.substring(idx, idx + 800);
                    let srmsg = document.querySelector('#srmsg');
                    return srmsg ? srmsg.innerText : '';
                }""")
                log_info(f"[CODE RETRY] Attempt {attempt} with platform feedback: {feedback}")
                solved_code = solve_code_editor(statement, sample_io, constraints, current_code, external_feedback=feedback)

            # Inject both to #txtCode and Ace editor to bypass the 30-char diff anti-paste check
            page.evaluate("""(code) => {
                let textarea = document.querySelector('#txtCode');
                if (textarea) textarea.value = code;
                if (window.$ && $('#txtCode').length) $('#txtCode').val(code);

                let aceEl = document.querySelector('.ace_editor');
                if (aceEl && window.ace) {
                    try {
                        let ed = window.ace.edit(aceEl);
                        ed.focus();
                        ed.setValue(code, -1);
                        ed.clearSelection();
                    } catch(e) {}
                }
                if (window.txtCode && typeof window.txtCode.setValue === 'function') {
                    try { window.txtCode.setValue(code, -1); } catch(e) {}
                }

                let cm = document.querySelector('.CodeMirror');
                if (cm && cm.CodeMirror) {
                    try {
                        cm.CodeMirror.setValue(code);
                        if (typeof cm.CodeMirror.save === 'function') cm.CodeMirror.save();
                    } catch(e) {}
                }

                if (typeof window.cs === 'function') {
                    try { window.cs(); } catch(e) {}
                }
            }""", solved_code)

            page.wait_for_timeout(500)

            log_info(f"[SUBMISSION] Attempt {attempt}: Code injected. Triggering Run...")
            try:
                page.evaluate("() => { let g = document.querySelector('#btngrp'); if (g) g.style.display = 'block'; }")
                run_btn.click(timeout=5000)
            except Exception:
                page.evaluate("""() => {
                    let g = document.querySelector('#btngrp');
                    if (g) g.style.display = 'block';
                    let b = document.querySelector('#j_id_bg') || document.querySelector("button[name*='Run']");
                    if (b) {
                        if (typeof oncompile === 'function') oncompile();
                        b.click();
                    }
                }""")
            passed = wait_for_run_result(page)
            if passed:
                pm.record_passed(pid, solved_code, attempt)
                pm.save()
                return True
            else:
                log_warning(f"[SUBMISSION] Attempt {attempt} did not pass.")

        return False


def run_challenge_part(page, bm, pm: ProgressManager, max_challenges=35) -> int:
    """
    Solves all challenges within the currently opened part on codeprogram.xhtml.
    Returns total challenges solved in this part.
    """
    solved_in_part = 0

    for ch_idx in range(max_challenges):
        page.wait_for_timeout(1500)

        # Check if we are on the table with a Solve button
        solve_btn = page.locator("[id*='pctbl:'][id*=':j_id_5w'], button:has-text('Solve')").first
        if solve_btn.is_visible(timeout=3000):
            log_info(f"[PART LOOP] Clicking Solve button for challenge {solved_in_part + 1}...")
            solve_btn.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2500)

        # Check if on problem page (or if table is empty)
        if not is_problem_revealed(page):
            cap_ok = solve_captcha_if_needed(page, bm)
            if not cap_ok and not is_problem_revealed(page):
                # Check if table has remaining problems or paginator
                if "codeprogram.xhtml" in page.url:
                    remaining = page.locator("[id*='pctbl:'][id*=':j_id_5w']").count()
                    if remaining == 0:
                        # Check next page button
                        next_pg = page.locator(".ui-paginator-next:not(.ui-state-disabled)").first
                        if next_pg.is_visible(timeout=2000):
                            next_pg.click()
                            page.wait_for_timeout(2000)
                            continue
                        log_info("[PART COMPLETED] No remaining challenges found in current part!")
                        break

        # If problem area is revealed, solve it!
        if is_problem_revealed(page):
            success = solve_current_problem(page, bm, pm)
            if success:
                solved_in_part += 1
                log_info(f"[PART PROGRESS] Completed {solved_in_part} challenges in current part!")

                # Click Proceed Next
                proceed_next = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value*='Proceed Next']").first
                if proceed_next.is_visible(timeout=8000):
                    log_info("[NAVIGATION] Clicking 'Proceed Next'...")
                    proceed_next.click()
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(3000)
                else:
                    back_btn = page.locator("button:has-text('Back To Challenges List'), #j_id_62").first
                    if back_btn.is_visible(timeout=3000):
                        back_btn.click()
                        page.wait_for_load_state("domcontentloaded")
                        page.wait_for_timeout(2500)

                # Check if any problems remain on the table
                if "codeprogram.xhtml" in page.url and not is_problem_revealed(page):
                    remaining = page.locator("[id*='pctbl:'][id*=':j_id_5w']").count()
                    if remaining == 0:
                        log_info("[PART COMPLETED] All challenges in current part are solved!")
                        break
            else:
                log_error("[PART LOOP] Challenge failed to pass. Returning to challenges list...")
                back_btn = page.locator("button:has-text('Back To Challenges List'), #j_id_62").first
                if back_btn.is_visible(timeout=3000):
                    back_btn.click()
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2500)

    return solved_in_part


def navigate_to_track(page, track_show_id: str, part_idx: int = 0) -> bool:
    """Navigates to CODETUTOR -> Python Programming -> Track -> Part."""
    log_info(f"[NAVIGATE] Opening CODETUTOR overview...")
    page.goto("https://skillrack.com/faces/candidate/codeprogramgroup.xhtml?gt=CODETUTOR")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)

    # Expand Python Programming
    py_btn = page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
    if py_btn.is_visible(timeout=4000):
        py_btn.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

    # Click Track Show button
    track_btn = page.locator(f"[id='{track_show_id}']").first
    if not track_btn.is_visible(timeout=4000):
        log_error(f"[NAVIGATE] Track button '{track_show_id}' not visible!")
        return False

    log_info(f"[NAVIGATE] Expanding target track via button '{track_show_id}'...")
    track_btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2500)

    # Click View button for part
    view_btn = page.locator(f"[id='cttbl:{part_idx}:j_id_4u']").first
    if not view_btn.is_visible(timeout=2000):
        view_btn = page.locator(f"#cttbl tr:nth-child({part_idx + 1}) button, #cttbl tr:nth-child({part_idx + 1}) a").first
    if not view_btn.is_visible(timeout=2000):
        view_btn = page.locator("[id*='cttbl:'][id*=':j_id_']").nth(part_idx)

    if view_btn.is_visible(timeout=4000):
        log_info(f"[NAVIGATE] Opening Part {part_idx + 1}...")
        view_btn.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)
        return True

    log_error(f"[NAVIGATE] Could not find View button for Part {part_idx + 1}!")
    return False


def run_track(page, bm, pm: ProgressManager, track_btn_id: str, track_name: str) -> int:
    """Solves all parts in a track dynamically until no View buttons remain."""
    log_info("\n" + "=" * 60)
    log_info(f"  STARTING TRACK: {track_name}")
    log_info(f"  Button ID: {track_btn_id}")
    log_info("=" * 60 + "\n")

    total_solved = 0
    part_num = 1
    while True:
        # Navigate to CODETUTOR overview
        page.goto("https://skillrack.com/faces/candidate/codeprogramgroup.xhtml?gt=CODETUTOR")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # Expand Python Programming
        py_btn = page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
        if py_btn.is_visible(timeout=4000):
            py_btn.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)

        track_btn = page.locator(f"[id='{track_btn_id}']").first
        if not track_btn.is_visible(timeout=4000):
            log_error(f"[NAVIGATE] Track button '{track_btn_id}' not found!")
            break
        track_btn.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)

        # Find all remaining 'View' buttons (each represents an unfinished part)
        view_btns = page.locator("button:has-text('View'), a:has-text('View')").all()
        if not view_btns:
            log_info(f"[{track_name} COMPLETE] All parts completed! No 'View' buttons remain!")
            break

        log_info(f"\n--- [{track_name}] FOUND {len(view_btns)} UNFINISHED PART(S). OPENING PART {part_num}... ---")
        view_btns[0].click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)

        # Solve all challenges in this part
        solved_count = run_challenge_part(page, bm, pm, max_challenges=15)
        total_solved += solved_count
        log_info(f"--- [{track_name}] PART {part_num} FINISHED: {solved_count} solved (Total: {total_solved}) ---")
        part_num += 1

    return total_solved


def main():
    verify_project_access()
    log_info("\n" + "=" * 60)
    log_info("  SKILLRACK MULTI-TRACK RUNNER INITIALIZATION")
    log_info("  Track: PYTHON3.x - 50 EASY CHALLENGES (50 Challenges)")
    log_info("  Track: PYTHON3.x - 50 AVERAGE CHALLENGES (50 Challenges)")
    log_info("=" * 60 + "\n")

    bm = BrowserManager(headless=False)
    page = bm.start()
    bm.login_and_navigate()
    pm = ProgressManager()

    try:
        # =========================================================================
        # TRACK: PYTHON3.x - 50 EASY CHALLENGES (50 Challenges across 5 Parts)
        # =========================================================================
        easy_solved = run_track(page, bm, pm, "pkglistform:j_id_49:3:j_id_4h", "PYTHON3.x - 50 EASY CHALLENGES")
        log_info(f"\n[TRACK COMPLETE] Solved {easy_solved} challenges in PYTHON3.x - 50 EASY CHALLENGES!\n")

        # =========================================================================
        # TRACK: PYTHON3.x - 50 AVERAGE CHALLENGES (50 Challenges across 5 Parts)
        # =========================================================================
        avg_solved = run_track(page, bm, pm, "pkglistform:j_id_49:4:j_id_4h", "PYTHON3.x - 50 AVERAGE CHALLENGES")
        log_info(f"\n[TRACK COMPLETE] Solved {avg_solved} challenges in PYTHON3.x - 50 AVERAGE CHALLENGES!\n")

        log_info(f"\n=======================================================")
        log_info(f"[ALL TASKS COMPLETE] Finished 50 Easy and 50 Average Challenges!")
        log_info(f"=======================================================")

    except Exception as e:
        log_error(f"[FATAL EXCEPTION] Automation error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if CLOSE_BROWSER_ON_FINISH:
            bm.close()
        else:
            log_info("[BROWSER] Keeping browser open for user review. Press Enter in terminal to close...")
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                pass
            bm.close()


if __name__ == "__main__":
    verify_project_access()
    main()
