import sys
import os

# Add parent directory to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from skill_automation.config import SECTIONS, HEADLESS, STOP_ON_FAILURE
from skill_automation.logger import log_info, log_error, log_warning
from skill_automation.progress import ProgressManager
from skill_automation.browser import BrowserManager
from skill_automation.section_runner import SectionRunner

def main():
    log_info(f"\n=======================================================")
    log_info(f">>> SKILL AUTOMATION PIPELINE (headless={HEADLESS})")
    log_info(f"=======================================================\n")

    progress_mgr = ProgressManager()
    start_sec, start_prob = progress_mgr.get_resume_target(SECTIONS)

    if start_sec:
        log_info(f"[RESUME] Found saved progress. Resuming at Section '{start_sec}' -> Problem {start_prob:02d}")
    else:
        log_info("[RESUME] No pending problems found in progress.json. Starting from beginning of SECTIONS list.")

    browser_mgr = BrowserManager(headless=HEADLESS)

    try:
        page = browser_mgr.start()
        browser_mgr.login_and_navigate()

        page.wait_for_load_state("domcontentloaded")
        log_info("[CHAPTER CHECK] Scanning for active chapter in portal...")
        
        view_btn = page.locator("button, a, input").filter(has_text=re.compile(r"^\s*(View|Resume)\s*$", re.I)).first
        if view_btn.is_visible(timeout=5000):
            log_info("[CHAPTER] Opening active chapter via View/Resume button...")
            view_btn.click()
            browser_mgr.handle_captcha_and_wait_for_editor()
            log_info("[READY] Code editor revealed. Starting problem runner pipeline...\n")

        # Iterate through configurable sections loop
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
        log_error(f"[CRITICAL EXCEPTION] Main automation pipeline encountered error: {e}")
        if 'page' in locals() and page and not page.is_closed():
            try:
                page.screenshot(path="screenshots/critical_error.png", full_page=True)
                log_info("[DIAGNOSTIC] Saved failure screenshot to 'screenshots/critical_error.png'")
            except Exception:
                pass
        raise
    finally:
        browser_mgr.close()
        log_info("[SHUTDOWN] Browser closed cleanly. Automation run finished.")

if __name__ == "__main__":
    main()
