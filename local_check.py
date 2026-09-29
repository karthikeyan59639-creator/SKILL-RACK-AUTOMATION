import sys
import ast
import re
import subprocess
from logger import log_info, log_warning, log_error

def run_local_check(code, sample_io) -> tuple[bool, str]:
    """
    Runs generated code locally against sample input/output in a subprocess with 5s timeout.
    Returns (passed: bool, message/feedback: str).
    """
    if code is None:
        return False, "Code is empty."
    if isinstance(code, (tuple, list)):
        code = code[0]
    code = str(code)
    if not code.strip():
        return False, "Code is empty."

    # 1. AST syntax parsing check
    try:
        ast.parse(code)
    except SyntaxError as se:
        feedback = f"Python SyntaxError: {se}"
        log_warning(f"[LOCAL CHECK] Code failed syntax check: {feedback}")
        return False, feedback

    # 1b. File operations check exemption:
    # SkillRack provides problem-specific files in its remote sandbox which do not exist locally
    if "open(" in code:
        log_info("[LOCAL CHECK] Code contains file operations ('open('). Passing local check on AST syntax.")
        return True, "Syntax check passed (file operation exempted from local execution)."

    # 2. Normalize sample_io list
    cases = []
    if isinstance(sample_io, list):
        cases = [c for c in sample_io if isinstance(c, dict) and "output" in c]
    elif isinstance(sample_io, dict):
        if "output" in sample_io:
            cases = [sample_io]

    if not cases:
        log_info("[LOCAL CHECK] No sample input/output found on problem; syntax check passed.")
        return True, "Syntax check passed (no sample I/O)."

    # 3. Test each sample case in subprocess
    for idx, case in enumerate(cases):
        raw_in = case.get("input", "")
        raw_exp = case.get("output", "")

        # Format input properly with trailing newline for input() calls
        sample_in = raw_in if raw_in.endswith("\n") else (raw_in + "\n" if raw_in else "")
        expected_norm = raw_exp.strip().replace("\r\n", "\n").replace("\u00a0", " ")

        log_info(f"[LOCAL CHECK] Running test case {idx+1}/{len(cases)} (Input: {repr(raw_in)[:40]})...")

        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                input=sample_in,
                capture_output=True,
                text=True,
                timeout=5
            )
        except subprocess.TimeoutExpired:
            feedback = (
                f"Local check execution timed out (5s limit exceeded).\n"
                f"Input:\n{raw_in}\n"
                f"Expected Output:\n{expected_norm}"
            )
            log_warning(f"[LOCAL CHECK] Test case {idx+1} timed out.")
            return False, feedback
        except Exception as proc_err:
            feedback = f"Subprocess launch error: {proc_err}"
            log_error(f"[LOCAL CHECK] {feedback}")
            return False, feedback

        actual_norm = proc.stdout.strip().replace("\r\n", "\n").replace("\u00a0", " ")
        stderr_clean = proc.stderr.strip()

        if proc.returncode != 0 or stderr_clean:
            feedback = (
                f"Local execution crashed with error code {proc.returncode}.\n"
                f"Input:\n{raw_in}\n"
                f"Expected Output:\n{expected_norm}\n"
                f"Your Program Output:\n{actual_norm}\n"
                f"Traceback:\n{stderr_clean}"
            )
            log_warning(f"[LOCAL CHECK] Test case {idx+1} failed with traceback:\n{stderr_clean}")
            return False, feedback

        if actual_norm != expected_norm:
            clean_exp = re.split(r"(?:^|\n)\s*(?:Explanation|Note):", expected_norm, flags=re.IGNORECASE)[0].strip()
            if actual_norm == clean_exp:
                continue
            feedback = (
                f"Local check output mismatch.\n"
                f"Input:\n{raw_in}\n"
                f"Expected Output:\n{expected_norm}\n"
                f"Your Program Output:\n{actual_norm}"
            )
            log_warning(
                f"[LOCAL CHECK] Test case {idx+1} output mismatch.\n"
                f"Expected: '{expected_norm}' | Actual: '{actual_norm}'"
            )
            return False, feedback

    log_info("[LOCAL CHECK] All sample input/output cases passed locally.")
    return True, "Passed all sample I/O cases locally."
