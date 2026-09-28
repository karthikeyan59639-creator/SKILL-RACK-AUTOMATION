import os
from config import (
    SCREENSHOTS_DIR, STOP_ON_FAILURE, TOTAL_PROBLEMS_PER_SECTION,
    TAKE_SUCCESS_SCREENSHOTS, TAKE_FAILURE_SCREENSHOTS, FIRST_TEST_ONLY
)
from logger import log_info, log_error, log_warning
from editor import enter_code, detect_editor_type
from result_detector import run_code, wait_for_success, ResultDetector
from solutions import get_solution_code
from solver import refine_solution_from_failure
from navigation import handle_tutorial_and_proceed

class ProblemRunner:
    @staticmethod
    def extract_problem_meta(page) -> dict:
        return page.evaluate("""() => {
            let leftEl = document.querySelector('#programgrid') || document.body;
            let leftText = leftEl ? leftEl.innerText : '';
            let pidMatch = leftText.match(/ProgramID-\\s*(\\d+)/);
            let pid = pidMatch ? pidMatch[1] : null;

            let edEl = document.getElementById('ctutortxtCode');
            let edVal = '';
            if (window.ace && edEl) {
                try {
                    edVal = ace.edit('ctutortxtCode').getValue();
                } catch(e) {}
            }

            let codeDiv = document.querySelector('#codediv');
            let suffixCode = codeDiv ? codeDiv.innerText.trim() : '';

            let prefixCode = '';
            if (edEl && edEl.parentElement) {
                let siblings = Array.from(edEl.parentElement.children);
                let edIdx = siblings.indexOf(edEl);
                if (edIdx > 0) {
                    let prev = siblings[edIdx - 1];
                    if (prev && !prev.innerText.includes('Ambiance') && !prev.innerText.includes('Python3')) {
                        prefixCode = prev.innerText.trim();
                    }
                }
            }

            let sampleInp = '';
            let sampleExp = '';
            let inpMatch = leftText.match(/Input:\\s*\\n*([^\\n]+)/i);
            if (inpMatch) sampleInp = inpMatch[1].trim();

            let expMatch = leftText.match(/Expected Output:\\s*\\n*([^\\n]+)/i);
            if (expMatch) sampleExp = expMatch[1].trim();

            return {
                pid: pid,
                leftText: leftText,
                sampleInput: sampleInp,
                expectedOutput: sampleExp,
                edVal: edVal,
                prefixCode: prefixCode,
                suffixCode: suffixCode
            };
        }""")

    @staticmethod
    def run_problem(page, browser_mgr, progress_mgr, section: str, problem_num: int) -> bool:
        print(f"[SECTION] {section}", flush=True)
        print(f"[PROBLEM] {problem_num}/{TOTAL_PROBLEMS_PER_SECTION}", flush=True)
        log_info(f"============================================================")
        log_info(f"[RUNNER] Section: {section} | Problem: {problem_num}/{TOTAL_PROBLEMS_PER_SECTION}")
        log_info(f"============================================================")

        sec_dir = os.path.join(SCREENSHOTS_DIR, section)
        os.makedirs(sec_dir, exist_ok=True)

        # 1. Ensure navigation from tutorial to solve page if proceed button is present
        if page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program')").first.is_visible(timeout=3000):
            if not handle_tutorial_and_proceed(page):
                fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
                page.screenshot(path=fail_ss, full_page=True)
                print(f"[ERROR] Tutorial navigation failed for {section} Problem {problem_num}.", flush=True)
                print(f"[URL] {page.url}", flush=True)
                print(f"[TITLE] {page.title()}", flush=True)
                print(f"[SCREENSHOT] {fail_ss}", flush=True)
                return False

        # 2. Verify code editor present & extract metadata
        editor_type = detect_editor_type(page)
        if editor_type != "unknown" or page.locator("#ctutortxtCode, .ace_editor, textarea#txtCode").first.is_visible(timeout=5000):
            print("[EDITOR] Found", flush=True)
            log_info(f"[EDITOR] Found editor of type '{editor_type}'")
        else:
            fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
            page.screenshot(path=fail_ss, full_page=True)
            print(f"[ERROR] Code editor not found on page.", flush=True)
            print(f"[URL] {page.url}", flush=True)
            print(f"[TITLE] {page.title()}", flush=True)
            print(f"[SCREENSHOT] {fail_ss}", flush=True)
            return False

        prob_meta = ProblemRunner.extract_problem_meta(page)

        # 3. Initial Solution Generation
        solution_code = get_solution_code(section, problem_num, prob_meta)
        if not solution_code:
            fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
            page.screenshot(path=fail_ss, full_page=True)
            print(f"[ERROR] No solution code found in solutions.py for {section} Problem {problem_num}.", flush=True)
            print(f"[URL] {page.url}", flush=True)
            print(f"[TITLE] {page.title()}", flush=True)
            print(f"[SCREENSHOT] {fail_ss}", flush=True)
            progress_mgr.mark_problem_status(section, problem_num, "failed", fail_ss, "No solution code provided")
            return False

        MAX_ATTEMPTS = 3
        current_code = solution_code

        for attempt in range(1, MAX_ATTEMPTS + 1):
            log_info(f"[ATTEMPT {attempt}/{MAX_ATTEMPTS}] Processing {section} Problem {problem_num}...")
            
            # 4. Enter code into editor and verify
            log_info(f"[ACTION] Entering code into editor:\n{current_code}")
            if enter_code(page, current_code, prob_meta):
                print("[CODE] Entered", flush=True)
                print("[CODE] Verified", flush=True)
            else:
                fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
                page.screenshot(path=fail_ss, full_page=True)
                print(f"[ERROR] Failed to enter or verify code in editor for {section} Problem {problem_num}.", flush=True)
                print(f"[URL] {page.url}", flush=True)
                print(f"[TITLE] {page.title()}", flush=True)
                print(f"[SCREENSHOT] {fail_ss}", flush=True)
                progress_mgr.mark_problem_status(section, problem_num, "failed", fail_ss, "Editor entry/verification failed")
                return False

            # 5. Execute Run control
            if not run_code(page):
                fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
                page.screenshot(path=fail_ss, full_page=True)
                print(f"[ERROR] Failed to click Run control button.", flush=True)
                print(f"[URL] {page.url}", flush=True)
                print(f"[TITLE] {page.title()}", flush=True)
                print(f"[SCREENSHOT] {fail_ss}", flush=True)
                progress_mgr.mark_problem_status(section, problem_num, "failed", fail_ss, "Run control button click failed")
                return False

            # 6. Wait for and detect result (Congratulations state)
            success = wait_for_success(page, max_wait_sec=35)

            if success:
                succ_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_success.png")
                if TAKE_SUCCESS_SCREENSHOTS:
                    page.screenshot(path=succ_ss, full_page=True)
                    log_info(f"[SCREENSHOT] Saved success screenshot: '{succ_ss}'")

                progress_mgr.mark_problem_status(section, problem_num, "completed", succ_ss)
                print(f"[PROGRESS] {section} Problem {problem_num} completed", flush=True)

                # Click Save after Congratulations verification
                save_btn = page.locator("button:has-text('Save')").first
                if save_btn.is_visible(timeout=2000):
                    save_btn.click()
                    log_info("[SAVE] Clicked Save button.")

                if not FIRST_TEST_ONLY and problem_num < TOTAL_PROBLEMS_PER_SECTION:
                    print(f"[NEXT] Opening Problem {problem_num + 1}", flush=True)
                    proceed_btn = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value='Proceed Next']").first
                    try:
                        proceed_btn.wait_for(state="visible", timeout=12000)
                        proceed_btn.click()
                        log_info("[NAVIGATION] Clicked 'Proceed Next' to advance.")
                        page.wait_for_timeout(2000)
                    except Exception as nav_e:
                        log_info(f"[NAVIGATION INFO] Proceed Next click notice: {nav_e}")

                return True

            # Handle execution failure / self-correction
            diag = ResultDetector.get_failure_diagnostics(page)
            log_warning(f"[RETRY] Attempt {attempt} failed for {section} Problem {problem_num}. Diagnostic output: Expected: '{diag.get('exp')}', Actual: '{diag.get('act')}'")

            if attempt < MAX_ATTEMPTS:
                refined = refine_solution_from_failure(prob_meta, diag)
                if refined and refined != current_code:
                    log_info(f"[RETRY REFINEMENT] Refined code for Attempt {attempt+1}:\n{refined}")
                    current_code = refined
                    page.wait_for_timeout(1000)
                    continue

            # Final Failure Path after retries exhausted
            fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
            if TAKE_FAILURE_SCREENSHOTS:
                page.screenshot(path=fail_ss, full_page=True)

            err_summary = f"Execution failed or timed out after {attempt} attempts. Expected: {diag.get('exp')} | Actual: {diag.get('act')}"
            progress_mgr.mark_problem_status(section, problem_num, "failed", fail_ss, err_summary)

            print(f"[ERROR] Execution failed for {section} Problem {problem_num}.", flush=True)
            print(f"[URL] {page.url}", flush=True)
            print(f"[TITLE] {page.title()}", flush=True)
            print(f"[SCREENSHOT] {fail_ss}", flush=True)

            if STOP_ON_FAILURE:
                log_error("[STOP_ON_FAILURE] Stopping automation workflow due to problem failure.")

            return False
