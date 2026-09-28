import sys
import os
import re

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SECTIONS, HEADLESS, FIRST_TEST_ONLY, STOP_ON_FAILURE
from logger import log_info, log_error
from progress import ProgressManager
from browser import BrowserManager
from navigation import handle_tutorial_and_proceed
from section_runner import SectionRunner

from problem_runner import ProblemRunner

def run_first_test_milestone(page, browser_mgr, progress_mgr):
    """
    Executes the single-problem first test:
    Open problem -> enter test code -> verify editor -> Run -> wait -> detect Congratulations -> save screenshot -> update progress -> STOP.
    """
    log_info("\n=======================================================")
    log_info(">>> EXECUTING FIRST TEST (SINGLE PROBLEM WORKFLOW) <<<")
    log_info("=======================================================\n")

    page.wait_for_load_state("domcontentloaded")
    
    # Check if on tutorial page or needs view button click
    if not ("tutorprogram.xhtml" in page.url or page.locator("#proceedbtn").is_visible(timeout=3000)):
        view_btn = page.locator("button, a, input").filter(has_text=re.compile(r"^\s*(View|Resume)\s*$", re.I)).first
        if view_btn.is_visible(timeout=5000):
            log_info("[CHAPTER] Opening active chapter via View/Resume button...")
            view_btn.click()
            page.wait_for_timeout(2000)

    # Execute single problem test for H002 Problem 1
    success = ProblemRunner.run_problem(page, browser_mgr, progress_mgr, "H002", 1)

    if success:
        log_info("\n=======================================================")
        log_info("[SUCCESS] FIRST TEST COMPLETED SUCCESSFULLY!")
        log_info("=======================================================\n")
    else:
        log_error("[FAILURE] First test single-problem execution failed.")

    return success


def main():
    log_info(f"\n=======================================================")
    log_info(f">>> SKILL RACK AUTOMATION PIPELINE (headless={HEADLESS})")
    log_info(f"=======================================================\n")

    progress_mgr = ProgressManager()
    start_sec, start_prob = progress_mgr.get_resume_target(SECTIONS)

    if start_sec:
        log_info(f"[RESUME] Found saved progress. Resuming at Section '{start_sec}' -> Problem {start_prob:02d}")
    else:
        log_info("[RESUME] Starting from configured SECTIONS list.")

    browser_mgr = BrowserManager(headless=HEADLESS)

    try:
        page = browser_mgr.start()
        browser_mgr.login_and_navigate()

        if FIRST_TEST_ONLY:
            run_first_test_milestone(page, browser_mgr, progress_mgr)
            return

        # Full Automation Pipeline Loop across Sections
        page.wait_for_load_state("domcontentloaded")
        view_btn = page.locator("button, a, input").filter(has_text=re.compile(r"^\s*(View|Resume)\s*$", re.I)).first
        if view_btn.is_visible(timeout=5000):
            view_btn.click()
            page.wait_for_timeout(2000)

        sections_to_run = SECTIONS
        if start_sec and start_sec in SECTIONS:
            start_idx = SECTIONS.index(start_sec)
            sections_to_run = SECTIONS[start_idx:]

        all_completed = True
        for section in sections_to_run:
            success = SectionRunner.run_section(page, browser_mgr, progress_mgr, section)
            if not success:
                all_completed = False
                log_error(f"[PIPELINE STOP] Automation stopped at Section '{section}' due to failure.")
                if STOP_ON_FAILURE:
                    break

        if all_completed:
            log_info("\n=======================================================")
            log_info("ALL REQUESTED SECTIONS COMPLETED")
            log_info("=======================================================\n")

    except Exception as e:
        log_error(f"[CRITICAL EXCEPTION] Main automation pipeline error: {e}")
        if 'page' in locals() and page and not page.is_closed():
            try:
                os.makedirs("screenshots", exist_ok=True)
                page.screenshot(path="screenshots/critical_error.png", full_page=True)
                log_info("[DIAGNOSTIC] Saved failure screenshot to 'screenshots/critical_error.png'")
            except Exception:
                pass
        raise
    finally:
        browser_mgr.close()
        log_info("[SHUTDOWN] Browser closed cleanly.")

if __name__ == "__main__":
    main()
