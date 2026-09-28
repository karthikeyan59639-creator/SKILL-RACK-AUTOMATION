import ast
import re
from logger import log_info, log_error, log_warning

def detect_editor_type(page) -> str:
    """Detects editor type on the active page."""
    try:
        res = page.evaluate("""() => {
            let aceEl = document.querySelector('[id*="ctutortxtCode"], .ace_editor');
            if (window.ace && aceEl) return 'ace';
            if (window.CodeMirror || document.querySelector('.CodeMirror')) return 'codemirror';
            if (window.monaco || document.querySelector('.monaco-editor')) return 'monaco';
            if (document.getElementById('txtCode') || document.querySelector('textarea.code_editor, textarea:not(.ace_text-input)')) return 'textarea';
            return 'unknown';
        }""")
        return res
    except Exception:
        return "unknown"


def verify_code_syntax_and_structure(code: str) -> tuple:
    """
    Verifies that the code is valid Python syntax, has balanced brackets/quotes,
    and contains no duplicated lines or broken statements.
    """
    if not code or not code.strip():
        return False, "Code is empty"

    # 1. AST Python syntax parsing
    try:
        ast.parse(code)
    except SyntaxError as se:
        return False, f"Python SyntaxError: {se}"

    # 2. Check for exact identical duplicate lines
    lines = [line.strip() for line in code.splitlines() if line.strip()]
    seen_lines = set()
    for l in lines:
        if l in seen_lines and len(l) > 3 and not l.startswith('#') and l not in ['pass', 'print()', 'else:', 'try:', 'except:']:
            return False, f"Exact duplicate line detected: '{l}'"
        seen_lines.add(l)

    # 3. Check bracket & quote balance
    for open_ch, close_ch in [('(', ')'), ('[', ']'), ('{', '}')]:
        if code.count(open_ch) != code.count(close_ch):
            return False, f"Unbalanced brackets '{open_ch}' vs '{close_ch}' ({code.count(open_ch)} vs {code.count(close_ch)})"

    return True, "OK"


def enter_code(page, code: str, problem_meta: dict = None) -> bool:
    """
    1. Locates the actual code editor.
    2. Focuses it.
    3. Clears existing code / template appropriately.
    4. Bulk injects supplied code (Ace, CodeMirror, Monaco, Textarea).
    5. Verifies editor contains expected code.
    6. Verifies syntax, bracket balance, and absence of duplicate statements.
    7. Returns True only when verification succeeds.
    """
    if not code:
        log_error("[EDITOR ERROR] Cannot enter solution: empty code string provided.")
        return False

    # 1. Pre-verify code syntax before editor entry
    valid, v_msg = verify_code_syntax_and_structure(code)
    if not valid:
        log_error(f"[EDITOR PRE-VERIFY FAIL] Solution code failed syntax/structure check: {v_msg}")
        return False

    log_info("[EDITOR] Waiting for code editor to be visible and interactable...")
    try:
        editor_ready = page.evaluate("""() => {
            let aceEl = document.querySelector('#ctutortxtCode, [id*="ctutortxtCode"], .ace_editor');
            let isAce = window.ace && aceEl;
            let isCm = window.CodeMirror || document.querySelector('.CodeMirror');
            let isMonaco = window.monaco || document.querySelector('.monaco-editor');
            let isTa = document.getElementById('txtCode') || document.querySelector('textarea.code_editor, textarea:not(.ace_text-input)');
            return !!(isAce || isCm || isMonaco || isTa);
        }""")
        if not editor_ready:
            page.locator("#ctutortxtCode, [id*='ctutortxtCode'], .ace_editor, .CodeMirror, .monaco-editor, #txtCode, textarea").first.wait_for(state="attached", timeout=10000)
    except Exception as e:
        log_error(f"[EDITOR ERROR] Code editor element was not ready: {e}")
        return False

    editor_type = detect_editor_type(page)
    log_info(f"[EDITOR] Found editor of type: '{editor_type}'")

    try:
        # Focus, clear, and enter supplied code into editor via multi-engine JS evaluator
        page.evaluate("""(newCode) => {
            // 1. Ace Editor
            let ed = null;
            let aceDiv = document.querySelector('.ace_editor');
            if (aceDiv && window.ace) {
                try { ed = ace.edit(aceDiv); } catch(e) {}
            }
            if (!ed) {
                let aceEl = document.querySelector('#ctutortxtCode, [id*="ctutortxtCode"]');
                if (aceEl && aceEl.env && aceEl.env.editor) ed = aceEl.env.editor;
                else if (aceEl && window.ace) {
                    try { ed = ace.edit(aceEl.id || aceEl); } catch(e) {}
                }
            }
            if (ed) {
                try {
                    ed.focus();
                    ed.setValue(newCode, -1);
                    ed.clearSelection();
                    return;
                } catch(e) {}
            }

            // 2. Textarea / Underlying Inputs (only when Ace is not active)
            let ta = document.getElementById('txtCode') || document.querySelector('textarea:not(.ace_text-input)');
            if (ta) {
                try {
                    ta.focus();
                    ta.value = newCode;
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                    ta.dispatchEvent(new Event('change', { bubbles: true }));
                    return;
                } catch(e) {}
            }

            // 3. CodeMirror
            let cmEl = document.querySelector('.CodeMirror');
            if (cmEl && cmEl.CodeMirror) {
                try { cmEl.CodeMirror.setValue(newCode); return; } catch(e) {}
            }

            // 4. Monaco Editor
            if (window.monaco && monaco.editor && monaco.editor.getModels().length > 0) {
                try { monaco.editor.getModels()[0].setValue(newCode); return; } catch(e) {}
            }
        }""", code)

        page.wait_for_timeout(500)

        # Read back code from editor to verify insertion
        actual_code = page.evaluate("""() => {
            let aceDiv = document.querySelector('.ace_editor');
            if (aceDiv && window.ace) {
                try {
                    let ed = ace.edit(aceDiv);
                    if (ed && ed.getValue()) return ed.getValue();
                } catch(e) {}
            }
            let aceEl = document.querySelector('#ctutortxtCode, [id*="ctutortxtCode"]');
            if (aceEl && aceEl.env && aceEl.env.editor) {
                try {
                    let val = aceEl.env.editor.getValue();
                    if (val) return val;
                } catch(e) {}
            }
            let cmEl = document.querySelector('.CodeMirror');
            if (cmEl && cmEl.CodeMirror) {
                try { return cmEl.CodeMirror.getValue(); } catch(e) {}
            }
            if (window.monaco && monaco.editor && monaco.editor.getModels().length > 0) {
                try { return monaco.editor.getModels()[0].getValue(); } catch(e) {}
            }
            let textareas = document.querySelectorAll('#ctutortxtCode, [id*="ctutortxtCode"], #txtCode, textarea');
            for (let ta of textareas) {
                if (ta.value && ta.value.trim()) return ta.value;
            }
            return '';
        }""")

        expected_clean = code.strip()
        actual_clean = actual_code.strip()

        if expected_clean != actual_clean:
            log_error(f"[EDITOR VERIFY] MISMATCH:\nExpected:\n{expected_clean}\nActual in Editor:\n{actual_clean}")
            return False

        # Verify read-back content syntax
        rb_valid, rb_msg = verify_code_syntax_and_structure(actual_clean)
        if not rb_valid:
            log_error(f"[EDITOR READBACK VERIFY FAIL] Content in editor failed verification: {rb_msg}")
            return False

        log_info("[EDITOR VERIFY] SUCCESS: Solution code verified present, syntactically valid, and structurally correct in editor.")
        return True

    except Exception as e:
        log_error(f"[EDITOR ERROR] Failed to enter solution code into editor: {e}")
        return False




def enter_solution(page, code: str, problem_meta: dict = None) -> bool:
    """Alias to enter_code for compatibility."""
    return enter_code(page, code, problem_meta)

