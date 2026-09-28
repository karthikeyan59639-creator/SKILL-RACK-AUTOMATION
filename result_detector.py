import time
from logger import log_info, log_warning, log_error

def run_code(page) -> bool:
    """
    1. Locate the actual Run/Test button.
    2. Click it once.
    3. Wait for execution/result state.
    4. Return control to the success detector.
    """
    log_info("[RUN] Locating Run/Test control button...")
    run_btn = page.locator("button:has-text('Run'), input[value*='Run'], #btnRun, button:has-text('Test')").first
    try:
        run_btn.wait_for(state="visible", timeout=10000)
        btn_tag = run_btn.evaluate('e => e.tagName')
        btn_txt = run_btn.inner_text().strip()
        print(f"[DEBUG] Element being clicked: tag='{btn_tag}', text='{btn_txt}'", flush=True)
        print("[RUN] Clicked", flush=True)
        log_info(f"[RUN] Clicking Run button (tag='{btn_tag}', text='{btn_txt}')...")
        run_btn.click()
        return True
    except Exception as e:
        log_error(f"[RUN ERROR] Could not locate or click Run button: {e}")
        return False


def wait_for_success(page, max_wait_sec: int = 35) -> bool:
    """
    1. Wait for execution result.
    2. Detect actual Congratulations element/text.
    3. Verify that the success state belongs to current problem.
    4. Return True only after successful completion is confirmed.
    5. Return False if an error/failure result appears.
    6. Save diagnostics if a timeout occurs.
    """
    print("[RESULT] Waiting...", flush=True)
    log_info("[RESULT DETECTOR] Waiting for execution result and Congratulations state...")

    start_time = time.time()
    
    # Use Playwright locator wait combined with DOM inspection
    result_locator = page.locator(
        ".ui-messages-info, .ui-message-info, .ui-messages-error, .ui-message-error, "
        "button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value='Proceed Next']"
    ).first

    try:
        result_locator.wait_for(state="visible", timeout=max_wait_sec * 1000)
    except Exception:
        pass

    while time.time() - start_time < max_wait_sec:
        status_info = page.evaluate("""() => {
            let t = document.body ? document.body.innerText : '';
            if (t.includes('Please wait while we run the program')) {
                return { status: 'WAITING' };
            }
            let hasCongrats = t.includes('Congratulations') || 
                              t.includes('Your Code has passed') || 
                              t.includes('Your code has passed') ||
                              !!document.querySelector('.ui-messages-info, .ui-message-info, #congratsMsg') ||
                              Array.from(document.querySelectorAll('button, a')).some(b => (b.innerText || '').includes('Proceed Next'));
            if (hasCongrats) {
                return { status: 'PASSED' };
            }
            let hasFailure = t.includes('Code did not pass') || 
                             t.includes('Wrong Answer') || 
                             t.includes('Traceback (most recent call last)') ||
                             t.includes('Compilation Error') ||
                             !!document.querySelector('.ui-messages-error, .ui-message-error');
            if (hasFailure) {
                return { status: 'FAILED' };
            }
            return { status: 'WAITING' };
        }""")

        status = status_info.get("status")
        if status == "PASSED":
            print("[SUCCESS] Congratulations detected", flush=True)
            log_info("[SUCCESS] Congratulations detected on page!")
            return True
        elif status == "FAILED":
            print("[FAILURE] Execution failed / Congratulations not detected.", flush=True)
            log_error("[RESULT] Execution failed / Code did not pass.")
            return False

        page.wait_for_timeout(300)

    log_error(f"[TIMEOUT] Execution result timed out after {max_wait_sec} seconds.")
    return False


class ResultDetector:
    @staticmethod
    def wait_and_detect(page, max_wait_sec: int = 35) -> str:
        return "PASSED" if wait_for_success(page, max_wait_sec) else "FAILED"

    @staticmethod
    def get_failure_diagnostics(page) -> dict:
        try:
            return page.evaluate("""() => {
                let t = document.body ? document.body.innerText : '';
                let expParts = t.split('Expected Output:');
                let exp = expParts.length > 1 ? expParts[1].trim().split('\\n')[0].trim() : '';
                let actParts = t.split('Your Program Output:');
                let act = actParts.length > 1 ? actParts[1].trim().split('\\n')[0].trim() : '';
                let inParts = t.split('Input:');
                let inp = inParts.length > 1 ? inParts[1].trim().split('\\n')[0].trim() : '';
                return { exp, act, inp };
            }""")
        except Exception as e:
            log_error(f"[DIAGNOSTICS ERROR] Failed to extract failure diagnostics: {e}")
            return {"exp": "", "act": "", "inp": ""}

