import os
import json
from skill_automation.config import (
    SCREENSHOTS_DIR, DRY_RUN, STOP_ON_FAILURE,
    TAKE_SUCCESS_SCREENSHOTS, TAKE_FAILURE_SCREENSHOTS
)
from skill_automation.logger import log_info, log_error, log_warning
from skill_automation.editor import EditorHandler
from skill_automation.result_detector import ResultDetector
from skill_automation.solutions import get_solution

class ProblemRunner:
    @staticmethod
    def extract_problem_meta(page) -> dict:
        """Extracts current problem metadata from the webpage DOM."""
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
        """
        Executes a single problem workflow:
        Extract metadata -> Get Solution -> Fill Editor -> Verify Editor -> Run -> Detect Result -> Save Screenshot & Progress.
        """
        log_info(f"============================================================")
        log_info(f"[RUNNER] Starting {section} -> Problem {problem_num:02d}")
        log_info(f"============================================================")

        sec_dir = os.path.join(SCREENSHOTS_DIR, section)
        os.makedirs(sec_dir, exist_ok=True)

        # 1. Extract problem metadata
        prob_meta = ProblemRunner.extract_problem_meta(page)
        pid = prob_meta.get("pid")
        log_info(f"[PROBLEM] Section: {section} | Problem: {problem_num} | ProgramID: {pid}")

        if not pid:
            log_error(f"[PROBLEM ERROR] Could not extract ProgramID for {section} Problem {problem_num}.")
            return False

        # 2. Get code solution
        solution_code = get_solution(section, problem_num, prob_meta)
        if not solution_code:
            log_error(f"[PROBLEM FAIL] No solution available for {section} Problem {problem_num} (PID-{pid}).")
            fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
            page.screenshot(path=fail_ss, full_page=True)
            progress_mgr.mark_problem_status(section, problem_num, "failed", fail_ss, "No solution found")
            return False

        # 3. Enter code into editor
        log_info(f"[ACTION] Entering code into editor:\n{solution_code}")
        if not EditorHandler.fill_code(page, solution_code):
            log_error(f"[PROBLEM FAIL] Failed to fill editor for {section} Problem {problem_num}.")
            fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
            page.screenshot(path=fail_ss, full_page=True)
            progress_mgr.mark_problem_status(section, problem_num, "failed", fail_ss, "Editor fill failed")
            return False

        # 4. Verify code presence in editor
        if not EditorHandler.verify_code(page, solution_code):
            log_error(f"[PROBLEM FAIL] Editor verification failed for {section} Problem {problem_num}.")
            fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
            page.screenshot(path=fail_ss, full_page=True)
            progress_mgr.mark_problem_status(section, problem_num, "failed", fail_ss, "Editor code mismatch")
            return False

        # 5. Handle DRY_RUN mode
        if DRY_RUN:
            log_info(f"[DRY_RUN] Verification complete for {section} Problem {problem_num}. Skipping actual Run/Submit execution.")
            succ_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_dry_run.png")
            page.screenshot(path=succ_ss, full_page=True)
            progress_mgr.mark_problem_status(section, problem_num, "completed", succ_ss)
            return True

        # 6. Execute Run/Test control
        log_info("[ACTION] Executing Run/Test control...")
        run_btn = page.locator("button:has-text('Run')").first
        run_btn.wait_for(state="visible", timeout=10000)
        run_btn.click()

        # 7. Wait for and detect result
        status = ResultDetector.wait_and_detect(page, max_wait_sec=35)
        log_info(f"[RESULT] Execution result status: '{status}'")

        if status == "PASSED":
            log_info(f"[SUCCESS] >>> {section} Problem {problem_num:02d} (PID-{pid}) PASSED! <<<")
            succ_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_success.png")
            
            if TAKE_SUCCESS_SCREENSHOTS:
                page.screenshot(path=succ_ss, full_page=True)
                log_info(f"[SCREENSHOT] Saved success screenshot: '{succ_ss}'")

            progress_mgr.mark_problem_status(section, problem_num, "completed", succ_ss)

            # Save verified solution if Save button is present
            save_btn = page.locator("button:has-text('Save')").first
            if save_btn.is_visible(timeout=2000):
                save_btn.click()
                log_info("[ACTION] Saved solution state on portal.")

            # Click Proceed Next to load next problem
            proceed_btn = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value='Proceed Next']").first
            try:
                proceed_btn.wait_for(state="visible", timeout=12000)
                proceed_btn.click()
                log_info("[NAVIGATION] Clicked 'Proceed Next' to advance.")
                
                browser_mgr.handle_captcha_if_present()
                page.locator("#ctutortxtCode").wait_for(state="visible", timeout=20000)
            except Exception as nav_e:
                log_info(f"[NAVIGATION INFO] Next problem loaded or end of section: {nav_e}")

            return True
        else:
            log_error(f"[FAILURE] >>> {section} Problem {problem_num:02d} (PID-{pid}) FAILED! <<<")
            diag = ResultDetector.get_failure_diagnostics(page)
            log_error(f"[DIAGNOSTICS] Input: '{diag.get('inp')}' | Expected: '{diag.get('exp')}' | Actual: '{diag.get('act')}'")
            
            fail_ss = os.path.join(sec_dir, f"problem_{problem_num:02d}_failure.png")
            if TAKE_FAILURE_SCREENSHOTS:
                page.screenshot(path=fail_ss, full_page=True)
                log_error(f"[SCREENSHOT] Saved failure screenshot: '{fail_ss}'")

            err_summary = f"Execution status: {status} | Expected: {diag.get('exp')} | Actual: {diag.get('act')}"
            progress_mgr.mark_problem_status(section, problem_num, "failed", fail_ss, err_summary)

            if STOP_ON_FAILURE:
                log_error(f"[STOP_ON_FAILURE] Stopping automation workflow due to problem failure.")

            return False
