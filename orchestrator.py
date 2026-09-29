import os
import json
import time
import random
from config import (
    HEADLESS, MAX_ATTEMPTS, ACTION_DELAY_MS,
    FAILURES_DIR, SCREENSHOTS_DIR, DEBUG_DIR
)
from logger import log_info, log_warning, log_error
from skill_automation.browser_manager import BrowserManager
from problem_scraper import scrape_problem, parse_problem_text, extract_stub_from_raw_text
from editor import (
    get_code, set_code, wait_for_editor_visible, normalize_code,
    get_editor_context, extract_editor_code_from_full
)
from solver import generate_solution, cache_passed_solution
from local_check import run_local_check
from runner import run_code_and_get_result
from progress import ProgressManager

from playwright.sync_api import Error as PlaywrightError
try:
    from playwright._impl._errors import TargetClosedError
except ImportError:
    TargetClosedError = PlaywrightError


def apply_action_delay():
    """Applies small random delay between actions to avoid platform rate limiting."""
    base_sec = ACTION_DELAY_MS / 1000.0
    jitter = random.uniform(0.1, 0.3)
    time.sleep(base_sec + jitter)


def extract_current_pid(page) -> str:
    """Fast extraction of current ProgramID from the live page text."""
    try:
        text = page.evaluate("() => document.body ? document.body.innerText : ''")
        parsed = parse_problem_text(text)
        return parsed.get("program_id", "")
    except Exception:
        return ""


def wait_for_stale_state_change(page, prev_pid: str, timeout_sec: int = 60) -> str:
    """
    Stale-state guard:
    After navigation, waits until the ProgramID badge text changes from prev_pid.
    Asserts scraped program_id != previous program_id.
    """
    if not prev_pid:
        return extract_current_pid(page)

    log_info(f"[GUARD] Waiting for ProgramID to change from '{prev_pid}'...")
    start_time = time.time()

    while time.time() - start_time < timeout_sec:
        current_pid = extract_current_pid(page)
        if current_pid and current_pid != prev_pid:
            log_info(f"[GUARD] ProgramID successfully changed: '{prev_pid}' -> '{current_pid}'")
            return current_pid
        page.wait_for_timeout(350)

    log_warning(f"[GUARD] ProgramID did not change from '{prev_pid}' within {timeout_sec}s.")
    return extract_current_pid(page)


def advance_to_next(page, browser_mgr, current_pid: str) -> bool:
    """
    Advances to the next exercise using the 'Proceed Next' button or page controls.
    If no proceed button, navigates to chapter list and opens next unfinished exercise.
    Applies stale-state guard to ensure the next exercise has loaded.
    """
    log_info("[NAVIGATION] Attempting to advance to next exercise...")

    proceed_btn = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value*='Proceed Next'], button:has-text('Next Program'), a:has-text('Next Program')").first
    next_btn = page.locator("button:has-text('Next'), a:has-text('Next'), .ui-paginator-next").first

    clicked = False
    if proceed_btn.is_visible(timeout=15000):
        log_info("[NAVIGATION] Clicking 'Proceed Next' button...")
        proceed_btn.scroll_into_view_if_needed()
        proceed_btn.click()
        page.wait_for_timeout(2000)
        clicked = True
    elif next_btn.is_visible(timeout=5000):
        log_info("[NAVIGATION] Clicking 'Next' pagination button...")
        next_btn.scroll_into_view_if_needed()
        next_btn.click()
        page.wait_for_timeout(2000)
        clicked = True

    if not clicked:
        log_info("[NAVIGATION] No Proceed Next button found on current problem. Opening next unfinished chapter...")
        try:
            opened_ch = browser_mgr.open_next_unfinished_chapter()
            if not opened_ch:
                log_info("[NAVIGATION] All requested chapters appear completed.")
                return False
            browser_mgr.handle_captcha_and_wait_for_editor()
            new_pid = extract_current_pid(page)
            if new_pid and new_pid != current_pid:
                log_info(f"[NAVIGATION] Successfully advanced to chapter {opened_ch} (PID-{new_pid}).")
            return bool(opened_ch)
        except Exception as e:
            log_warning(f"[NAVIGATION] Next chapter navigation notice: {e}")
        return False

    page.wait_for_load_state("domcontentloaded")
    apply_action_delay()

    # Check if chapter completion screen appeared!
    is_completed_banner = page.evaluate("""() => {
        let t = document.body ? document.body.innerText : '';
        return t.includes('successfully completed the programming course') ||
               t.includes('successfully completed');
    }""")
    if is_completed_banner:
        log_info("[MILESTONE] >>> Chapter completed successfully banner detected! Transitioning to next chapter... <<<")
        opened_ch = browser_mgr.open_next_unfinished_chapter()
        if not opened_ch:
            log_info("[NAVIGATION] All requested chapters appear completed.")
            return False
        browser_mgr.handle_captcha_and_wait_for_editor()
        new_pid = extract_current_pid(page)
        if new_pid and new_pid != current_pid:
            log_info(f"[NAVIGATION] Successfully advanced to next chapter {opened_ch} (PID-{new_pid}).")
        return bool(opened_ch)

    # Handle tutorial page / proceed button or captcha if prompted
    browser_mgr.handle_captcha_and_wait_for_editor()

    # Enforce stale-state guard
    new_pid = wait_for_stale_state_change(page, current_pid, timeout_sec=45)
    if new_pid and new_pid != current_pid:
        assert new_pid != current_pid, f"Stale-state guard assertion failed: {new_pid} == {current_pid}"
        log_info(f"[NAVIGATION] Successfully advanced to new exercise (PID-{new_pid}).")
        return True
    else:
        log_info("[NAVIGATION] ProgramID unchanged. Opening next unfinished chapter...")
        try:
            opened_ch = browser_mgr.open_next_unfinished_chapter()
            if not opened_ch:
                log_info("[NAVIGATION] All requested chapters appear completed.")
                return False
            browser_mgr.handle_captcha_and_wait_for_editor()
            new_pid = extract_current_pid(page)
            if new_pid and new_pid != current_pid:
                log_info(f"[NAVIGATION] Successfully advanced to next chapter {opened_ch} (PID-{new_pid}).")
            return bool(opened_ch)
        except Exception as e:
            log_warning(f"[NAVIGATION] Next chapter navigation notice: {e}")
        return False


def run_orchestrator(headless: bool = HEADLESS):
    """
    Main Orchestration Loop:
    1. Log in and navigate, handle captcha, wait for editor.
    2. Read progress.json for resumability.
    3. Loop per exercise:
       - Read ORIGINAL stub BEFORE changing anything (editor.get_code()).
       - Generate solution in 'fill in missing lines' mode (before, after).
       - Deterministic Python assembly & verification (stub preservation, AST, local I/O).
       - Write final code into editor ONCE (cm.setValue; cm.save).
       - Click Save first, then Run.
       - Detect pass / fail outcome.
       - On fail: retry with original stub + diagnostics (max 3 attempts).
       - On 3 fails: save failure artifacts, record failed, and SKIP to next problem.
       - On pass: record passed, advance to next problem.
       - Stale-state guard asserts pid != prev_pid.
    4. Print summary report (passed, failed, skipped with program IDs).
    """
    log_info("\n" + "=" * 60)
    log_info(f">>> SKILLRACK AUTONOMOUS CODE TUTOR ORCHESTRATOR (headless={headless}) <<<")
    log_info("=" * 60 + "\n")

    progress_mgr = ProgressManager()
    browser_mgr = BrowserManager(headless=headless)
    prev_pid = None
    page = None

    passed_pids = []
    failed_pids = []
    skipped_pids = []

    try:
        page = browser_mgr.start()
        browser_mgr.login_and_navigate()
        browser_mgr.handle_captcha_and_wait_for_editor()

        log_info("\n[ORCHESTRATOR] Entering exercise solving loop...\n")

        while True:
            apply_action_delay()

            # Handle captcha if it reappeared on this exercise
            browser_mgr.handle_captcha_if_present()

            # Ensure visible editor widget before interacting
            wait_for_editor_visible(page)

            # 1. Scrape problem
            problem = scrape_problem(page)
            pid = problem.get("program_id", "")

            if not pid:
                log_warning("[ORCHESTRATOR] Could not locate active ProgramID on page.")
                page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "missing_pid.png"))
                break

            # Stale-state guard assertion
            if prev_pid is not None and pid == prev_pid:
                log_warning(f"[ORCHESTRATOR] Detected stale exercise (PID-{pid} matches previous). Attempting recovery...")
                new_pid = wait_for_stale_state_change(page, prev_pid, timeout_sec=20)
                if not new_pid or new_pid == prev_pid:
                    log_info("[ORCHESTRATOR] Attempting to advance to next unfinished chapter...")
                    opened = browser_mgr.open_next_unfinished_chapter()
                    if opened:
                        browser_mgr.handle_captcha_and_wait_for_editor()
                        new_pid = extract_current_pid(page)
                    if not opened:
                        log_info("[ORCHESTRATOR] No new exercise loaded across all tracks.")
                        break
                pid = new_pid or pid
                prev_pid = None
                problem = scrape_problem(page)
            log_info("-" * 60)
            log_info(f"[EXERCISE] Processing ProgramID-{pid} | Title: '{problem.get('title')}'")
            log_info("-" * 60)

            # 2. Resumability: Check if already passed in progress.json
            if progress_mgr.is_passed(pid):
                log_info(f"[RESUME] Exercise ProgramID-{pid} is already PASSED in progress.json. Skipping...")
                skipped_pids.append(pid)
                has_next = advance_to_next(page, browser_mgr, pid)
                if not has_next:
                    log_info("[ORCHESTRATOR] No subsequent exercise found after skip.")
                    break
                prev_pid = pid
                continue

            # 3. Read starter context from the page (prefix, suffix, editor)
            ctx = get_editor_context(page)
            prefix = ctx.get("prefix", "")
            suffix = ctx.get("suffix", "")
            editor_val = ctx.get("editor_val", "")

            if prefix or suffix:
                parts = []
                if prefix:
                    parts.append(prefix)
                if suffix:
                    parts.append(suffix)
                original_stub = "\n".join(parts)
            else:
                original_stub = ""

            if original_stub.strip().isdigit():
                original_stub = ""

            log_info(f"[STUB] Read starter stub from platform:\n{original_stub if original_stub else '(empty)'}")
            if prefix:
                log_info(f"[STUB PREFIX]:\n{prefix}")
            if suffix:
                log_info(f"[STUB SUFFIX]:\n{suffix}")

            # 4. Attempt loop (up to MAX_ATTEMPTS, each starting from ORIGINAL stub)
            passed = False
            last_feedback = None
            attempted_code = ""
            final_result = None

            for attempt in range(1, MAX_ATTEMPTS + 1):
                log_info(f"\n[ATTEMPT {attempt}/{MAX_ATTEMPTS}] Solving ProgramID-{pid} from ORIGINAL stub...")

                # 4a. Generate solution in fill-in-missing-lines mode
                final_code, before_lines, after_lines, middle_lines = generate_solution(
                    problem, original_stub, feedback=last_feedback, prefix=prefix, suffix=suffix
                )
                attempted_code = final_code

                if not final_code or not final_code.strip():
                    log_error(f"[SOLVER FAIL] Empty solution generated on attempt {attempt}.")
                    last_feedback = "Generated code was empty. Please provide valid Python 3 code."
                    continue

                log_info(f"[GENERATED CODE]:\n{final_code}")

                # Determine what code needs to go into the editor
                if prefix and suffix and middle_lines:
                    code_for_editor = "\n".join(middle_lines)
                elif prefix and not suffix and after_lines:
                    code_for_editor = "\n".join(after_lines)
                elif suffix and not prefix and before_lines:
                    code_for_editor = "\n".join(before_lines)
                elif prefix or suffix:
                    code_for_editor = extract_editor_code_from_full(final_code, prefix, suffix)
                else:
                    code_for_editor = final_code

                # 4b. Write code into editor ONCE and assert readback
                set_success = set_code(
                    page,
                    final_code=code_for_editor,
                    stub=original_stub,
                    before_lines=before_lines,
                    after_lines=after_lines,
                    middle_lines=middle_lines,
                    max_retries=3
                )
                if not set_success:
                    log_error(f"[EDITOR FAIL] Could not verify code insertion for ProgramID-{pid}.")
                    last_feedback = "Editor failed to accept code properly."
                    continue

                apply_action_delay()

                # 4c. Click Save first, then Run, and wait for result panel
                log_info(f"[ACTION] Running code for ProgramID-{pid}...")
                result = run_code_and_get_result(page, timeout_sec=120)
                final_result = result
                log_info(f"[RUN RESULT] Status: {result.get('status')}")

                if result.get("passed"):
                    passed = True
                    passed_pids.append(pid)
                    log_info(f"[SUCCESS] >>> ProgramID-{pid} PASSED on attempt {attempt}! <<<")
                    # Cache passed solution
                    cache_passed_solution(pid, final_code)
                    # Record passed in progress.json
                    progress_mgr.record_passed(pid, final_code, attempts=attempt)
                    break
                else:
                    log_warning(f"[ATTEMPT FAIL] ProgramID-{pid} failed execution on platform.")
                    exp_out = result.get('expected', '').strip()
                    if exp_out and not problem.get("sample_io"):
                        problem["sample_io"] = [{"input": result.get('input', '').strip(), "output": exp_out}]
                        log_info(f"[SOLVER UPDATE] Enriched sample_io with platform expected output: '{exp_out}'")
                    last_feedback = (
                        f"Code did not pass execution.\n"
                        f"Input: {result.get('input', '')}\n"
                        f"Expected Output: {result.get('expected', '')}\n"
                        f"Your Program Output: {result.get('actual', '')}\n"
                        f"Traceback: {result.get('traceback', '')}"
                    )
                    apply_action_delay()

            # 5. Handle Final Outcome for this exercise
            if not passed:
                log_error(f"[PROBLEM FAILED] ProgramID-{pid} failed after {MAX_ATTEMPTS} attempts. Saving artifacts and skipping...")
                failed_pids.append(pid)

                # Save failure artifacts to ./failures/<program_id>/
                fail_dir = os.path.join(FAILURES_DIR, str(pid))
                os.makedirs(fail_dir, exist_ok=True)

                ss_path = os.path.join(fail_dir, "failure.png")
                try:
                    page.screenshot(path=ss_path, full_page=True)
                    log_info(f"[FAILURE ARTIFACT] Saved screenshot to '{ss_path}'")
                except Exception as ss_e:
                    log_warning(f"[FAILURE ARTIFACT] Screenshot failed: {ss_e}")

                prob_path = os.path.join(fail_dir, "problem.json")
                try:
                    with open(prob_path, "w", encoding="utf-8") as f:
                        json.dump(problem, f, indent=2)
                    log_info(f"[FAILURE ARTIFACT] Saved problem details to '{prob_path}'")
                except Exception as p_e:
                    log_warning(f"[FAILURE ARTIFACT] Problem dump failed: {p_e}")

                stub_path = os.path.join(fail_dir, "stub.py")
                try:
                    with open(stub_path, "w", encoding="utf-8") as f:
                        f.write(original_stub or "")
                    log_info(f"[FAILURE ARTIFACT] Saved starter stub to '{stub_path}'")
                except Exception:
                    pass

                code_path = os.path.join(fail_dir, "attempted_code.py")
                try:
                    with open(code_path, "w", encoding="utf-8") as f:
                        f.write(attempted_code or "")
                    log_info(f"[FAILURE ARTIFACT] Saved attempted code to '{code_path}'")
                except Exception as c_e:
                    log_warning(f"[FAILURE ARTIFACT] Code dump failed: {c_e}")

                res_path = os.path.join(fail_dir, "result.txt")
                try:
                    with open(res_path, "w", encoding="utf-8") as f:
                        f.write(last_feedback or (final_result.get("raw_text") if final_result else ""))
                    log_info(f"[FAILURE ARTIFACT] Saved result text to '{res_path}'")
                except Exception:
                    pass

                progress_mgr.record_failed(pid, attempted_code, attempts=MAX_ATTEMPTS, error=last_feedback or "")

            # 6. Advance to next exercise (never get stuck, always advance)
            prev_pid = pid
            has_next = advance_to_next(page, browser_mgr, pid)
            if not has_next:
                log_info("[ORCHESTRATOR] Advance returned False. Checking next unfinished chapters with retries...")
                for retry_i in range(1, 4):
                    log_info(f"[ORCHESTRATOR] Retry {retry_i}/3 to find unfinished chapter...")
                    page.wait_for_timeout(3000)
                    opened = browser_mgr.open_next_unfinished_chapter()
                    if opened:
                        browser_mgr.handle_captcha_and_wait_for_editor()
                        has_next = True
                        prev_pid = None
                        break
                if not has_next:
                    log_info("[ORCHESTRATOR] All requested chapters and subsequent tracks are completed!")
                    break

    except TargetClosedError:
        log_error("[ORCHESTRATOR] the browser window was closed")
    except Exception as e:
        log_error(f"[ORCHESTRATOR CRITICAL] Unhandled exception: {e}")
        try:
            if page:
                ts = time.strftime("%Y%m%d_%H%M%S")
                os.makedirs(DEBUG_DIR, exist_ok=True)
                fail_path = os.path.join(DEBUG_DIR, f"failure_{ts}.png")
                page.screenshot(path=fail_path, full_page=True)
                log_info(f"[ORCHESTRATOR] Saved failure screenshot to '{fail_path}'")
        except Exception:
            pass
        raise
    finally:
        from config import CLOSE_BROWSER_ON_FINISH
        # Print summary report
        log_info("\n" + "=" * 60)
        log_info(">>> EXECUTION SUMMARY REPORT <<<")
        log_info(f"Passed:   {len(passed_pids)} (IDs: {passed_pids})")
        log_info(f"Failed:   {len(failed_pids)} (IDs: {failed_pids})")
        log_info(f"Skipped:  {len(skipped_pids)} (IDs: {skipped_pids})")
        log_info(f"Total:    {len(passed_pids) + len(failed_pids) + len(skipped_pids)}")
        log_info("=" * 60 + "\n")

        if CLOSE_BROWSER_ON_FINISH:
            log_info("[BROWSER] Closing browser as requested by configuration...")
            browser_mgr.close()
        else:
            log_info("[BROWSER] >>> Browser kept OPEN for user inspection (CLOSE_BROWSER_ON_FINISH=False) <<<")
            try:
                while True:
                    time.sleep(5)
                    if not page or page.is_closed():
                        break
            except (KeyboardInterrupt, SystemExit):
                pass
            except Exception:
                pass


if __name__ == "__main__":
    run_orchestrator()
