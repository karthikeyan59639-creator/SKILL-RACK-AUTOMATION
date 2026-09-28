import time
from skill_automation.config import SUCCESS_INDICATORS, FAILURE_INDICATORS
from skill_automation.logger import log_info, log_warning, log_error

class ResultDetector:
    @staticmethod
    def wait_and_detect(page, max_wait_sec: int = 35) -> str:
        """
        Polls the DOM state until execution completes.
        Returns: 'PASSED', 'FAILED', or 'TIMEOUT'.
        """
        log_info("[RESULT DETECTOR] Polling page DOM state for execution status...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait_sec:
            time.sleep(0.3)
            status = page.evaluate("""() => {
                let t = document.body ? document.body.innerText : '';
                if (t.includes('Please wait while we run the program')) {
                    return 'WAITING';
                }
                if (t.includes('Congratulations! Your Code has passed') || 
                    t.includes('Great! Your code has passed') || 
                    document.querySelector('button[value*="Proceed Next"]') ||
                    Array.from(document.querySelectorAll('button, a')).some(b => (b.innerText || '').includes('Proceed Next'))) {
                    return 'PASSED';
                }
                if (t.includes('Code did not pass the execution') || t.includes('Wrong Answer') || t.includes('Traceback (most recent call last)')) {
                    return 'FAILED';
                }
                return 'WAITING';
            }""")
            if status != 'WAITING':
                log_info(f"[RESULT DETECTOR] Execution finished with status: '{status}'")
                return status
                
        log_warning(f"[RESULT DETECTOR] Execution timed out after {max_wait_sec} seconds.")
        return 'TIMEOUT'

    @staticmethod
    def get_failure_diagnostics(page) -> dict:
        """Extracts input, expected output, and actual program output upon execution failure."""
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
