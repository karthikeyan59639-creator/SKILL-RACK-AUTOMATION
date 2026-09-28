from skill_automation.logger import log_info, log_error, log_warning

class EditorHandler:
    @staticmethod
    def detect_editor_type(page) -> str:
        """Detects editor type on the active page."""
        try:
            is_ace = page.evaluate("() => typeof window.ace !== 'undefined' && !!document.getElementById('ctutortxtCode')")
            if is_ace:
                return "ace"
            if page.locator("textarea#txtCode, textarea.code_editor").is_visible(timeout=2000):
                return "textarea"
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def fill_code(page, code: str) -> bool:
        """Fills the code editor with the supplied code string."""
        editor_type = EditorHandler.detect_editor_type(page)
        log_info(f"[EDITOR] Detected editor type: '{editor_type}'")

        try:
            if editor_type == "ace" or True:  # Default to Ace JS evaluation for SkillRack
                page.evaluate(f"""() => {{
                    if (window.ace) {{
                        let ed = ace.edit('ctutortxtCode');
                        ed.setValue('', -1);
                        ed.setValue({repr(code)}, 1);
                    }}
                    let ta = document.getElementById('txtCode');
                    if (ta) ta.value = {repr(code)};
                }}""")
                return True
            elif editor_type == "textarea":
                ta = page.locator("textarea#txtCode, textarea.code_editor").first
                ta.fill(code)
                return True
        except Exception as e:
            log_error(f"[EDITOR ERROR] Failed to inject code into editor: {e}")
            return False

    @staticmethod
    def get_code(page) -> str:
        """Reads back the current text content inside the editor."""
        try:
            return page.evaluate("""() => {
                if (window.ace) {
                    try {
                        return ace.edit('ctutortxtCode').getValue();
                    } catch(e) {}
                }
                let ta = document.getElementById('txtCode');
                return ta ? ta.value : '';
            }""")
        except Exception as e:
            log_error(f"[EDITOR ERROR] Failed to read code from editor: {e}")
            return ""

    @staticmethod
    def verify_code(page, expected_code: str) -> bool:
        """Verifies that the code inside the editor matches the expected code."""
        actual_code = EditorHandler.get_code(page)
        expected_stripped = expected_code.strip()
        actual_stripped = actual_code.strip()

        if expected_stripped == actual_stripped:
            log_info("[EDITOR VERIFY] SUCCESS: Editor content matches supplied solution code exactly.")
            return True
        else:
            log_warning(f"[EDITOR VERIFY] MISMATCH:\nExpected:\n{expected_stripped}\nActual in Editor:\n{actual_stripped}")
            return False
