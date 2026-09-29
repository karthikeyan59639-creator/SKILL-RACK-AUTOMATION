import time
from logger import log_info, log_warning, log_error

def normalize_code(code) -> str:
    """Normalizes line endings and trailing whitespace for reliable comparison."""
    if code is None:
        return ""
    if isinstance(code, (tuple, list)):
        code = code[0]
    if not isinstance(code, str):
        code = str(code)
    text = code.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def wait_for_editor_visible(page, timeout_ms: int = 120000):
    """
    Waits for the VISIBLE editor widget.
    Never waits on the raw hidden backing textarea (e.g. textarea#txtCode).
    """
    log_info(f"[EDITOR] Waiting for visible editor widget (timeout={timeout_ms}ms)...")
    editor_locator = page.locator(".CodeMirror:visible, .ace_editor:visible, #ctutortxtCode:visible").first
    editor_locator.wait_for(state="visible", timeout=timeout_ms)
    log_info("[EDITOR] Visible editor widget confirmed.")
    return editor_locator


def detect_editor(page) -> str:
    """
    Auto-detects the editor type on the active page by inspecting the live DOM:
    'codemirror', 'codemirror6', 'ace', 'monaco', 'textarea', or 'unknown'.
    """
    try:
        editor_type = page.evaluate("""() => {
            // 1. CodeMirror (v5) - Priority for SkillRack Code Tutor
            let cmEl = document.querySelector('.CodeMirror');
            if (cmEl) return 'codemirror';

            // 2. CodeMirror 6
            let cm6El = document.querySelector('.cm-editor');
            if (cm6El) return 'codemirror6';

            // 3. Ace Editor
            let aceEl = document.querySelector('.ace_editor, #ctutortxtCode');
            if (aceEl && (window.ace || (aceEl.env && aceEl.env.editor))) return 'ace';

            // 4. Monaco Editor
            let monacoEl = document.querySelector('.monaco-editor');
            if (monacoEl && window.monaco) return 'monaco';

            // 5. Visible Textarea fallback
            let ta = document.querySelector('textarea:not(.ace_text-input)');
            if (ta && ta.offsetParent !== null) return 'textarea';

            return 'unknown';
        }""")
        log_info(f"[EDITOR] Detected live editor type: '{editor_type}'")
        return editor_type
    except Exception as e:
        log_warning(f"[EDITOR] Detection evaluation warning: {e}")
        return "unknown"


def get_code(page) -> str:
    """
    Reads the current code content from the active editor.
    Inspects CodeMirror getValue(), Ace, Monaco, backing store, and visible DOM lines.
    """
    try:
        raw_code = page.evaluate("""() => {
            let cmEl = document.querySelector('.CodeMirror');
            let cmVisible = cmEl && cmEl.offsetParent !== null;

            let aceEl = document.querySelector('.ace_editor, #ctutortxtCode, [id*="ctutortxtCode"]');
            let aceVisible = aceEl && aceEl.offsetParent !== null;

            // If Ace is visible and CodeMirror is not visible, prioritize Ace
            if (aceVisible && !cmVisible && window.ace) {
                try {
                    let ed = ace.edit(aceEl.id || aceEl);
                    if (ed) return ed.getValue();
                } catch(e) {}
            }

            // 1. CodeMirror (v5)
            if (cmEl && (cmVisible || !aceVisible)) {
                if (cmEl.CodeMirror && typeof cmEl.CodeMirror.getValue === 'function') {
                    try { return cmEl.CodeMirror.getValue(); } catch(e) {}
                }
                let cmProp = Object.keys(cmEl).find(k => k.startsWith('CodeMirror') || (cmEl[k] && cmEl[k].getValue));
                if (cmProp && cmEl[cmProp]) {
                    try { return cmEl[cmProp].getValue(); } catch(e) {}
                }
            }

            // 2. Ace Editor
            if (aceEl) {
                if (aceEl.env && aceEl.env.editor) {
                    try { return aceEl.env.editor.getValue(); } catch(e) {}
                }
                if (window.ace) {
                    try {
                        let ed = ace.edit(aceEl.id || aceEl);
                        if (ed) return ed.getValue();
                    } catch(e) {}
                }
            }

            // 3. CodeMirror 6
            let cm6Content = document.querySelector('.cm-editor .cm-content');
            if (cm6Content) {
                try { return cm6Content.innerText; } catch(e) {}
            }

            // 4. Monaco Editor
            if (window.monaco && monaco.editor && monaco.editor.getModels().length > 0) {
                try { return monaco.editor.getModels()[0].getValue(); } catch(e) {}
            }

            // 5. Backing textarea / Plain textarea
            let ta = document.querySelector('#txtCode, textarea:not(.ace_text-input)');
            if (ta && ta.value) {
                return ta.value;
            }

            // 6. Visible DOM line text fallback (Ace lines or CodeMirror lines)
            let aceLines = Array.from(document.querySelectorAll('.ace_line')).map(l => l.innerText).filter(t => t !== undefined && t !== null).join('\\n');
            if (aceLines && aceLines.trim()) return aceLines.trim();

            let cmLines = Array.from(document.querySelectorAll('.CodeMirror-line')).map(l => l.innerText).filter(t => t !== undefined && t !== null).join('\\n');
            if (cmLines && cmLines.trim()) return cmLines.trim();

            return '';
        }""")
        return raw_code or ""
    except Exception as e:
        log_error(f"[EDITOR ERROR] Failed to read code from editor: {e}")
        return ""


def extract_middle_code(full_code: str, stub_code: str) -> str:
    """
    If stub_code contains prefix and/or suffix lines that are locked/pre-filled in the editor,
    extracts only the middle lines that need to be inserted.
    """
    if not stub_code or not full_code:
        return full_code

    stub_lines = [l.strip() for l in stub_code.splitlines() if l.strip()]
    full_lines = [l for l in full_code.splitlines() if l.strip()]

    # Find longest common prefix
    p = 0
    while p < len(stub_lines) and p < len(full_lines) and full_lines[p].strip() == stub_lines[p]:
        p += 1

    # Find longest common suffix
    s = 0
    while s < (len(stub_lines) - p) and s < (len(full_lines) - p) and full_lines[-(s + 1)].strip() == stub_lines[-(s + 1)]:
        s += 1

    middle = full_lines[p: len(full_lines) - s if s > 0 else None]
    if middle:
        return "\n".join(middle).strip()
    return full_code


def get_editor_context(page) -> dict:
    """
    Extracts the full code context from the active page:
    - prefix: static starter lines above the editor (e.g. from <pre> before editor in #codediv)
    - suffix: static starter lines below the editor (e.g. from <pre> after editor in #codediv)
    - editor_val: code currently inside the editable widget (Ace / CodeMirror)
    """
    try:
        data = page.evaluate(r"""() => {
            let allEditors = Array.from(document.querySelectorAll('.ace_editor, .CodeMirror, #ctutortxtCode'));
            let editorEl = allEditors.find(el => el.offsetParent !== null) || allEditors[0];

            let prefix = '';
            let suffix = '';

            if (editorEl) {
                let container = document.querySelector('#codeeditorpanel') || editorEl.closest('#codeeditorpanel, #codediv') || document.body;
                let preEls = Array.from(container.querySelectorAll('pre'));

                let beforeEditor = [];
                let afterEditor = [];

                for (let p of preEls) {
                    let pos = editorEl.compareDocumentPosition(p);
                    let txt = (p.innerText || p.textContent || '').replace(/^[\r\n]+/, '').replace(/[\r\n]+$/, '');
                    if (!txt) continue;

                    if (pos & Node.DOCUMENT_POSITION_PRECEDING) {
                        beforeEditor.push(txt);
                    } else if (pos & Node.DOCUMENT_POSITION_FOLLOWING) {
                        afterEditor.push(txt);
                    }
                }

                prefix = beforeEditor.join('\n').replace(/^[\r\n]+/, '').replace(/[\r\n]+$/, '');
                suffix = afterEditor.join('\n').replace(/^[\r\n]+/, '').replace(/[\r\n]+$/, '');
            }

            let editorVal = '';
            let cmEl = document.querySelector('.CodeMirror');
            if (cmEl && cmEl.offsetParent !== null && cmEl.CodeMirror) {
                try { editorVal = cmEl.CodeMirror.getValue(); } catch(e) {}
            }
            if (!editorVal) {
                let aceEl = document.querySelector('.ace_editor');
                if (aceEl && aceEl.offsetParent !== null && window.ace) {
                    try { editorVal = ace.edit(aceEl).getValue(); } catch(e) {}
                }
            }
            if (!editorVal) {
                let ta = document.querySelector('#txtCode');
                if (ta && ta.value) editorVal = ta.value;
            }

            return {
                prefix: prefix,
                suffix: suffix,
                editor_val: editorVal.trim()
            };
        }""")
        return data or {"prefix": "", "suffix": "", "editor_val": ""}
    except Exception as e:
        log_warning(f"[EDITOR] get_editor_context error: {e}")
        return {"prefix": "", "suffix": "", "editor_val": ""}


def extract_editor_code_from_full(full_code: str, prefix: str, suffix: str) -> str:
    """
    Extracts only the code that must go inside the editor widget
    by stripping the external prefix and suffix blocks.
    """
    if not prefix and not suffix:
        return full_code

    full_lines = [l.rstrip() for l in full_code.splitlines()]
    prefix_lines = [l.rstrip() for l in prefix.splitlines()] if prefix else []
    suffix_lines = [l.rstrip() for l in suffix.splitlines()] if suffix else []

    # Strip prefix lines from start
    p_len = 0
    if prefix_lines:
        while p_len < len(prefix_lines) and p_len < len(full_lines) and full_lines[p_len].strip() == prefix_lines[p_len].strip():
            p_len += 1

    # Strip suffix lines from end
    s_len = 0
    if suffix_lines:
        while s_len < len(suffix_lines) and s_len < (len(full_lines) - p_len) and full_lines[-(s_len + 1)].strip() == suffix_lines[-(s_len + 1)].strip():
            s_len += 1

    middle = full_lines[p_len : len(full_lines) - s_len if s_len > 0 else None]
    if p_len > 0 or s_len > 0:
        return "\n".join(middle).strip("\r\n")
    return full_code


def set_code(
    page,
    final_code: str,
    stub: str = None,
    before_lines: list = None,
    after_lines: list = None,
    middle_lines: list = None,
    max_retries: int = 3
) -> bool:
    """
    Writes the final code into the editor ONCE, replacing the entire content:
    cm.setValue(final); cm.save().
    If starter lines are locked/read-only, inserts only the new lines at correct line positions
    using cm.replaceRange(text, {line: n, ch: 0}) or ed.session.insert.
    Asserts readback equals final_code (normalized).
    Logs the stub, the inserted lines, and the final editor content.
    """
    if final_code is None:
        log_error("[EDITOR] set_code called with None final_code.")
        return False

    expected_norm = normalize_code(final_code)
    before_str = "\n".join(before_lines) if before_lines else ""
    after_str = "\n".join(after_lines) if after_lines else ""
    middle_str = "\n".join(middle_lines) if middle_lines else ""
    stub_norm = normalize_code(stub) if stub else "(empty)"

    for attempt in range(1, max_retries + 1):
        log_info(f"[EDITOR] Writing final code into editor (attempt {attempt}/{max_retries})...")

        # 1. Primary multi-engine JS replacement with cm.setValue(final); cm.save()
        try:
            page.evaluate("""({ newCode, beforeText, afterText, middleText }) => {
                let updated = false;

                // 1. CodeMirror (Priority on SkillRack Code Tutor)
                let cmEl = document.querySelector('.CodeMirror');
                let cmVisible = cmEl && cmEl.offsetParent !== null;
                let aceEl = document.querySelector('.ace_editor') || document.querySelector('#ctutortxtCode, [id*="ctutortxtCode"]');
                let aceVisible = aceEl && aceEl.offsetParent !== null;

                // 1. If Ace is visible, update Ace
                if (aceVisible && window.ace && aceEl) {
                    try {
                        let ed = ace.edit(aceEl.id || aceEl);
                        if (ed) {
                            ed.focus();
                            try {
                                ed.setValue(newCode, -1);
                                ed.clearSelection();
                                updated = true;
                            } catch(aceRoErr) {
                                if (middleText && middleText.trim()) {
                                    ed.session.insert({ row: 1, column: 0 }, middleText.trim() + '\\n');
                                }
                                if (beforeText && beforeText.trim()) {
                                    ed.session.insert({ row: 0, column: 0 }, beforeText.trim() + '\\n');
                                }
                                if (afterText && afterText.trim()) {
                                    let lastRow = ed.session.getLength();
                                    ed.session.insert({ row: lastRow, column: 0 }, '\\n' + afterText.trim());
                                }
                                updated = true;
                            }
                        }
                    } catch(e) {}
                }

                // 2. CodeMirror (v5) - if visible or Ace was not updated
                if (cmEl && (cmVisible || !updated)) {
                    let cm = cmEl.CodeMirror;
                    if (!cm) {
                        let cmProp = Object.keys(cmEl).find(k => k.startsWith('CodeMirror') || (cmEl[k] && cmEl[k].setValue));
                        if (cmProp) cm = cmEl[cmProp];
                    }
                    if (cm) {
                        let hasReadOnly = false;
                        let editableLines = [];
                        for (let i = 0; i < cm.lineCount(); i++) {
                            let marks = cm.findMarks({line: i, ch: 0}, {line: i, ch: (cm.getLine(i) || '').length});
                            let isRo = marks.some(m => m.readOnly);
                            if (isRo) {
                                hasReadOnly = true;
                            } else {
                                editableLines.push(i);
                            }
                        }

                        if (!hasReadOnly) {
                            try {
                                cm.setValue('');
                                cm.setValue(newCode);
                                if (typeof cm.save === 'function') cm.save();
                                updated = true;
                            } catch(roErr) {
                                hasReadOnly = true;
                            }
                        }

                        if (hasReadOnly) {
                            try {
                                let textToInsert = (middleText && middleText.trim()) ? middleText.trim() : "";
                                if (!textToInsert && editableLines.length > 0) {
                                    // If editable line is not line 0, any code (beforeText or newCode) belongs in the editable area!
                                    if (editableLines[0] > 0) {
                                        textToInsert = (beforeText && beforeText.trim()) ? beforeText.trim() : (newCode && newCode.trim() ? newCode.trim() : "");
                                    }
                                }
                                if (textToInsert && editableLines.length > 0) {
                                    let firstEd = editableLines[0];
                                    let lastEd = editableLines[editableLines.length - 1];
                                    cm.replaceRange(textToInsert, { line: firstEd, ch: 0 }, { line: lastEd, ch: (cm.getLine(lastEd) || '').length });
                                } else {
                                    if (beforeText && beforeText.trim() && (editableLines.length === 0 || editableLines.includes(0))) {
                                        cm.replaceRange(beforeText.trim() + '\\n', { line: 0, ch: 0 });
                                    }
                                    if (afterText && afterText.trim() && (editableLines.length === 0 || editableLines.includes(cm.lastLine()))) {
                                        let lastLine = cm.lastLine();
                                        let lastCh = (cm.getLine(lastLine) || '').length;
                                        cm.replaceRange('\\n' + afterText.trim(), { line: lastLine, ch: lastCh });
                                    }
                                }
                                if (typeof cm.save === 'function') cm.save();
                                updated = true;
                            } catch(e) {}
                        }
                    }
                }

                // 3. Ace Editor fallback if neither updated
                if (!updated && window.ace && aceEl) {
                    try {
                        let ed = ace.edit(aceEl.id || aceEl);
                        if (ed) {
                            ed.focus();
                            ed.setValue(newCode, -1);
                            ed.clearSelection();
                            updated = true;
                        }
                    } catch(e) {}
                }

                // 3. Monaco Editor
                if (window.monaco && monaco.editor && monaco.editor.getModels().length > 0) {
                    try {
                        monaco.editor.getModels()[0].setValue(newCode);
                        updated = true;
                    } catch(e) {}
                }

                // 4. Backing & Plain Textarea (Always synchronized)
                let ta = document.getElementById('txtCode') || document.querySelector('textarea:not(.ace_text-input)');
                if (ta) {
                    try {
                        ta.value = newCode;
                        ta.dispatchEvent(new Event('input', { bubbles: true }));
                        ta.dispatchEvent(new Event('change', { bubbles: true }));
                        updated = true;
                    } catch(e) {}
                }

                return updated;
            }""", {"newCode": final_code, "beforeText": before_str, "afterText": after_str, "middleText": middle_str})
        except Exception as eval_err:
            log_warning(f"[EDITOR] JS evaluation attempt {attempt} failed: {eval_err}")

        page.wait_for_timeout(350)

        # 2. Check readback
        actual_code = get_code(page)
        actual_norm = normalize_code(actual_code)

        if actual_norm == expected_norm:
            log_info("[EDITOR] Code verified successfully in editor.")
            log_info(f"[STUB]:\n{stub_norm}")
            log_info(f"[INSERTED LINES]: before={before_lines or []}, middle={middle_lines or []}, after={after_lines or []}")
            log_info(f"[FINAL EDITOR CONTENT]:\n{actual_norm}")
            return True

        # 3. Fallback: Click editor, Ctrl+A, Delete, keyboard.insert_text(code) (Never per-key typing)
        log_warning("[EDITOR] JS injection mismatch. Attempting keyboard.insert_text fallback...")
        try:
            editor_loc = page.locator(".CodeMirror:visible, .ace_editor:visible, #ctutortxtCode:visible").first
            if editor_loc.is_visible(timeout=3000):
                editor_loc.click()
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                page.wait_for_timeout(200)

                # Check what remains (immutable prefix lines that Ctrl+A/Delete cannot remove)
                rem_code = normalize_code(get_code(page))
                text_to_insert = final_code

                if stub and rem_code and rem_code in stub_norm:
                    # Locked lines present: insert only the middle/new content
                    middle = extract_middle_code(final_code, stub)
                    text_to_insert = middle
                elif rem_code and expected_norm.startswith(rem_code):
                    text_to_insert = expected_norm[len(rem_code):].lstrip("\n")

                if text_to_insert:
                    page.keyboard.insert_text(text_to_insert)

                page.wait_for_timeout(400)
                # Call cm.save() if CodeMirror and sync to #txtCode
                page.evaluate("""(newCode) => {
                    let cmEl = document.querySelector('.CodeMirror');
                    if (cmEl && cmEl.CodeMirror && typeof cmEl.CodeMirror.save === 'function') {
                        cmEl.CodeMirror.save();
                    }
                    let ta = document.getElementById('txtCode');
                    if (ta) {
                        ta.value = newCode;
                        ta.dispatchEvent(new Event('input', { bubbles: true }));
                        ta.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", final_code)
        except Exception as kb_err:
            log_warning(f"[EDITOR] Keyboard fallback action error: {kb_err}")

        # 4. Check readback again
        actual_code = get_code(page)
        actual_norm = normalize_code(actual_code)

        if actual_norm == expected_norm or (actual_norm.endswith(expected_norm) and not expected_norm.startswith(actual_norm)):
            log_info("[EDITOR] Code verified successfully via keyboard fallback.")
            log_info(f"[STUB]:\n{stub_norm}")
            log_info(f"[INSERTED LINES]: before={before_lines or []}, middle={middle_lines or []}, after={after_lines or []}")
            log_info(f"[FINAL EDITOR CONTENT]:\n{actual_norm}")
            return True
        else:
            log_warning(
                f"[EDITOR] Attempt {attempt} mismatch.\n"
                f"Expected:\n{expected_norm}\n"
                f"Actual in Editor:\n{actual_norm}"
            )
            page.wait_for_timeout(500)

    log_error(f"[EDITOR] Failed to verify code in editor after {max_retries} attempts.")
    return False
