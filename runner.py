import time
import re
from logger import log_info, log_warning, log_error

def run_code_and_get_result(page, timeout_sec: int = 180) -> dict:
    """
    1. Clicks Save button first (if present/visible on page) and waits.
    2. Clicks Run button and waits for the execution result panel.
    3. Detects pass/fail status from live DOM text and returns structured diagnostics.
    """
    # 1. Click Save first if present
    save_btn = page.locator("button:has-text('Save'):visible, input[value*='Save']:visible, #btnSave:visible").first
    if save_btn.is_visible(timeout=1500):
        try:
            log_info("[RUNNER] Clicking 'Save' button first...")
            save_btn.scroll_into_view_if_needed()
            save_btn.click()
            try:
                page.wait_for_function(
                    "() => (!window.PrimeFaces || !window.PrimeFaces.ajax || !window.PrimeFaces.ajax.Queue || window.PrimeFaces.ajax.Queue.isEmpty())",
                    timeout=4000
                )
            except Exception:
                page.wait_for_timeout(500)
        except Exception as save_err:
            log_warning(f"[RUNNER] Save button click notice: {save_err}")

    # 2. Locate Run button
    log_info("[RUNNER] Locating Run button...")
    try:
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass

    run_btn = page.locator("button:has-text('Run'):visible, input[value*='Run']:visible, #btnRun:visible, button:has-text('Test'):visible").first
    clicked = False
    try:
        run_btn.scroll_into_view_if_needed(timeout=2000)
        run_btn.wait_for(state="visible", timeout=2000)
        btn_tag = run_btn.evaluate("e => e.tagName")
        btn_text = run_btn.inner_text().strip()
        log_info(f"[RUNNER] Clicking Run control (<{btn_tag}> '{btn_text}')...")
        run_btn.click()
        clicked = True
    except Exception as e:
        log_warning(f"[RUNNER] Standard locator click notice: {e}. Trying direct DOM JS click...")
        try:
            clicked = page.evaluate("""() => {
                let btn = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]')).find(b => {
                    let txt = (b.innerText || b.value || '').trim();
                    return txt === 'Run' || txt.includes('Run');
                });
                if (btn) {
                    btn.scrollIntoView();
                    btn.click();
                    return true;
                }
                return false;
            }""")
            if clicked:
                log_info("[RUNNER] Direct DOM JS click succeeded.")
        except Exception as js_e:
            log_error(f"[RUNNER ERROR] Direct JS click failed: {js_e}")

    if not clicked:
        log_error("[RUNNER ERROR] Failed to locate or click Run button.")
        return {
            "passed": False,
            "status": "CLICK_FAILED",
            "input": "",
            "expected": "",
            "actual": "",
            "traceback": "Could not click Run button",
            "raw_text": ""
        }

    log_info("[RUNNER] Waiting for execution result panel...")
    start_time = time.time()

    # Short wait for execution request to begin and old result panel to refresh
    page.wait_for_timeout(1000)

    while time.time() - start_time < timeout_sec:
        try:
            status_info = page.evaluate("""() => {
            let bodyText = document.body ? document.body.innerText : '';

            // If still executing, keep waiting
            if (bodyText.includes('Please wait while we run the program')) {
                return { status: 'WAITING', text: bodyText };
            }

            // Success checks (check presence of Proceed Next button or Congratulations)
            let proceedBtn = Array.from(document.querySelectorAll('button, a, input[type="button"]')).find(b => {
                let txt = (b.innerText || b.value || '').trim();
                return (txt === 'Proceed Next' || txt.includes('Proceed Next')) && b.offsetParent !== null;
            });

            let hasCongrats = bodyText.includes('Congratulations! Your Code has passed') ||
                              bodyText.includes('Great! Your code has passed') ||
                              bodyText.includes('Congratulations') ||
                              bodyText.includes('Your Code has passed') ||
                              bodyText.includes('Your code has passed') ||
                              Boolean(proceedBtn);

            // Scoped failure check
            let hasFailure = bodyText.includes('Code did not pass the execution') ||
                             bodyText.includes('Code did not pass') ||
                             bodyText.includes('Wrong Answer') ||
                             bodyText.includes('Traceback (most recent call last)') ||
                             bodyText.includes('Compilation Error') ||
                             bodyText.includes('SyntaxError') ||
                             bodyText.includes('NameError') ||
                             bodyText.includes('IndentationError') ||
                             bodyText.includes('Failed Test Cases') ||
                             bodyText.includes('FAILED');

            if (hasCongrats && !bodyText.includes('Code did not pass the execution')) {
                return { status: 'PASSED', text: bodyText };
            }

            if (hasFailure) {
                return { status: 'FAILED', text: bodyText };
            }

            return { status: 'WAITING', text: bodyText };
        }""")
        except Exception as eval_err:
            page.wait_for_timeout(1000)
            continue

        state = status_info.get("status")
        raw_text = status_info.get("text", "")

        if state == "PASSED":
            log_info("[RUNNER SUCCESS] Congratulations / pass detected on platform!")
            return {
                "passed": True,
                "status": "PASSED",
                "input": "",
                "expected": "",
                "actual": "",
                "traceback": "",
                "raw_text": raw_text
            }

        elif state == "FAILED":
            log_warning("[RUNNER FAILURE] Code did not pass execution on platform.")
            diagnostics = extract_diagnostics(raw_text)
            log_info(
                f"[RUNNER DIAGNOSTICS] Input: '{diagnostics.get('input')}' | "
                f"Expected: '{diagnostics.get('expected')}' | "
                f"Actual: '{diagnostics.get('actual')}'"
            )
            return {
                "passed": False,
                "status": "FAILED",
                "input": diagnostics.get("input", ""),
                "expected": diagnostics.get("expected", ""),
                "actual": diagnostics.get("actual", ""),
                "traceback": diagnostics.get("traceback", ""),
                "raw_text": raw_text
            }

        page.wait_for_timeout(400)

    log_error(f"[RUNNER TIMEOUT] Execution result timed out after {timeout_sec} seconds.")
    raw_text = page.evaluate("() => document.body ? document.body.innerText : ''")
    diagnostics = extract_diagnostics(raw_text)
    return {
        "passed": False,
        "status": "TIMEOUT",
        "input": diagnostics.get("input", ""),
        "expected": diagnostics.get("expected", ""),
        "actual": diagnostics.get("actual", ""),
        "traceback": "Execution result timed out.",
        "raw_text": raw_text
    }


def extract_diagnostics(text: str) -> dict:
    """Extracts Input, Expected Output, Actual Output, and Traceback from result text."""
    diagnostics = {"input": "", "expected": "", "actual": "", "traceback": ""}
    if not text:
        return diagnostics

    # 1. Input: stops before Expected Output
    inp_match = re.search(r"(?:Test\s*)?Input:\s*\n?(.*?)(?=(?:Expected\s+Output|Your\s+Program\s+Output|\n\s*[A-Z][a-z]+:|\Z))", text, re.IGNORECASE | re.DOTALL)
    if inp_match:
        diagnostics["input"] = inp_match.group(1).strip()

    # 2. Expected Output: stops before Your Program Output
    exp_match = re.search(r"Expected\s+Output:\s*\n?(.*?)(?=(?:Your\s+Program\s+Output|Actual\s+Output|\n\s*[A-Z][a-z]+:|\Z))", text, re.IGNORECASE | re.DOTALL)
    if exp_match:
        diagnostics["expected"] = exp_match.group(1).strip()

    # 3. Your Program Output
    act_match = re.search(r"Your\s+Program\s+Output:\s*\n?(.*?)(?=(?:Traceback|Input:|\n\s*[A-Z][a-z]+:|\Z))", text, re.IGNORECASE | re.DOTALL)
    if act_match:
        diagnostics["actual"] = act_match.group(1).strip()

    # 4. Traceback
    tb_match = re.search(r"(Traceback\s*\(most recent call last\):[\s\S]*?)(?=\n\n|\n[A-Z][a-z]+:|\Z)", text)
    if tb_match:
        diagnostics["traceback"] = tb_match.group(1).strip()

    return diagnostics
