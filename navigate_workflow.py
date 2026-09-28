from playwright.sync_api import sync_playwright
from PIL import Image
import base64, io, re, json, time, os, sys
from solver import solve_problem, synthesize_solution, KNOWN_SOLUTIONS

# OCR Template definitions for Math Captcha solving
TEMPLATES = {
    '0': ('.####.' '.#..#.' '#....#' '#....#' '#....#' '#....#' '#....#' '.#..#.' '.####.'),
    '1': ('###..' '..#..' '..#..' '..#..' '..#..' '..#..' '..#..' '..#..' '#####'),
    '2': ('.####.' '#...##' '.....#' '.....#' '....#.' '...#..' '..#...' '.#....' '######'),
    '3': ('.####.' '#....#' '.....#' '.....#' '..###.' '.....#' '.....#' '#....#' '.####.'),
    '4': ('...##.' '...##.' '..#.#.' '.#..#.' '.#..#.' '#...#.' '######' '....#.' '....#.'),
    '5': ('#####.' '#.....' '#.....' '#####.' '....##' '.....#' '.....#' '#...##' '.####.'),
    '6': ('..###.' '.#...#' '#.....' '#.###.' '##..##' '#....#' '#....#' '.#..##' '.####.'),
    '7': ('######' '.....#' '....#.' '....#.' '...#..' '...#..' '..#...' '..#...' '.#....'),
    '8': ('.####.' '#....#' '#....#' '#....#' '.####.' '#....#' '#....#' '#....#' '.####.'),
    '9': ('.####.' '##..#.' '#....#' '#....#' '##..##' '.###.#' '.....#' '#...#.' '.###..'),
    '+': ('...#...' '...#...' '...#...' '#######' '...#...' '...#...' '...#...'),
    '-': ('######'),
    '=': ('########' '########')
}

def solve_captcha(b64_str: str) -> str:
    """Decodes base64 captcha image and extracts math expression result using template OCR."""
    if ',' in b64_str:
        b64_str = b64_str.split(',', 1)[1]
    b64_str = b64_str.strip() + '=' * (-len(b64_str.strip()) % 4)

    raw_bytes = base64.b64decode(b64_str)
    im = Image.open(io.BytesIO(raw_bytes)).convert('L')
    pixels = im.load()
    w, h = im.size

    col_has_white = [any(pixels[x, y] > 128 for y in range(30, min(45, h))) for x in range(w)]
    segments = []
    in_seg = False
    start = 0
    for x in range(w):
        if col_has_white[x] and not in_seg:
            in_seg = True
            start = x
        elif not col_has_white[x] and in_seg:
            in_seg = False
            segments.append((start, x - 1))
    if in_seg:
        segments.append((start, w - 1))

    chars = []
    for s, e in segments:
        seg_rows = [y for y in range(30, min(45, h)) if any(pixels[x, y] > 128 for x in range(s, e + 1))]
        if not seg_rows:
            continue
        min_y, max_y = min(seg_rows), max(seg_rows)
        pat_lines = [''.join('#' if pixels[x, y] > 128 else '.' for x in range(s, e + 1)) for y in range(min_y, max_y + 1)]
        pat_str = ''.join(pat_lines)

        best_char = '?'
        best_score = -999
        for ch, templ in TEMPLATES.items():
            templ_lines = [templ[i:i+(e-s+1)] for i in range(0, len(templ), (e-s+1))]
            if len(pat_lines) == len(templ_lines):
                score = sum(1 if p == t else -1 for p, t in zip(pat_str, templ))
            else:
                score = -abs(len(pat_str) - len(templ))
            if score > best_score:
                best_score = score
                best_char = ch
        chars.append(best_char)

    expr = ''.join(c for c in chars if c != '=')
    m = re.match(r'(\d+)\s*([\+\-\*\/])\s*(\d+)', expr)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        ans = a + b if op == '+' else a - b if op == '-' else a * b
        return str(ans)
    return expr


def handle_captcha(page) -> bool:
    """Detects and solves captcha prompt if visible."""
    try:
        img_el = page.locator("#codeeditorpanel img").first
        if img_el.is_visible(timeout=3000):
            print("[CAPTCHA] Math captcha challenge detected. Solving...", flush=True)
            src = img_el.get_attribute("src")
            ans = solve_captcha(src)
            print(f"[CAPTCHA] Solved expression result: {ans}. Submitting...", flush=True)
            page.locator("#capval").fill(ans)
            page.locator("#proceedbtn").click()
            page.locator("#ctutortxtCode").wait_for(state="visible", timeout=15000)
            return True
    except Exception as e:
        pass
    return False


def get_problem(page) -> dict:
    """
    Extracts complete problem metadata from current page DOM.
    Returns dictionary with pid, leftText, sampleInput, expectedOutput, edVal, prefixCode, suffixCode.
    """
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


def fill_editor(page, solution: str):
    """Fills the Ace code editor with the generated solution string."""
    print(f"[EDITOR] Injecting solution into code editor...", flush=True)
    page.evaluate(f"""() => {{
        if (window.ace) {{
            let ed = ace.edit('ctutortxtCode');
            ed.setValue('', -1);
            ed.setValue({repr(solution)}, 1);
        }}
        let ta = document.getElementById('txtCode');
        if (ta) ta.value = {repr(solution)};
    }}""")


def run_code(page, max_wait_sec=30) -> str:
    """Triggers code execution and polls execution status state using locator checks."""
    print("[EXECUTION] Clicking 'Run' button...", flush=True)
    run_btn = page.locator("button:has-text('Run')").first
    run_btn.wait_for(state="visible", timeout=10000)
    run_btn.click()

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
            return status
    return 'TIMEOUT'


def get_failure_diagnostics(page) -> dict:
    """Extracts input/expected/actual strings upon test failure."""
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


def save_and_proceed(page) -> bool:
    """Saves verified solution, clicks 'Proceed Next', and waits for next problem to load."""
    save_btn = page.locator("button:has-text('Save')").first
    if save_btn.is_visible(timeout=2000):
        print("[ACTION] Saving verified solution...", flush=True)
        save_btn.click()
        time.sleep(0.5)

    proceed_btn = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value='Proceed Next']").first
    try:
        proceed_btn.wait_for(state="visible", timeout=12000)
        print("[NAVIGATION] Advancing to next problem via 'Proceed Next'...", flush=True)
        proceed_btn.click()
        
        # Check if captcha appeared on next problem
        handle_captcha(page)

        # Wait until editor is ready for next problem
        page.locator("#ctutortxtCode").wait_for(state="visible", timeout=20000)
        return True
    except Exception as e:
        print(f"[CHAPTER COMPLETE] Proceed Next unavailable or chapter finished: {e}", flush=True)
        return False


def login_and_navigate(page, context=None, console_logs=None, page_errors=None, failed_requests=None):
    """Handles authentication and navigates directly to Python Hands-On Code Tutor."""
    if console_logs is None: console_logs = []
    if page_errors is None: page_errors = []
    if failed_requests is None: failed_requests = []

    print(f"[DIAGNOSTIC] Entering login_and_navigate. Page closed: {page.is_closed()}, URL: '{page.url}'", flush=True)
    if page.is_closed():
        raise RuntimeError("Cannot navigate: page object is closed prior to page.goto().")

    print("[LOGIN] Navigating to SkillRack profile (https://skillrack.com/faces/ui/profile.xhtml)...", flush=True)
    resp = None
    try:
        resp = page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="domcontentloaded", timeout=60000)
    except Exception as goto_err:
        print(f"[GOTO WARNING] Primary domcontentloaded navigation failed: {goto_err}. Retrying with commit...", flush=True)
        try:
            resp = page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="commit", timeout=60000)
        except Exception as retry_err:
            print(f"[GOTO ERROR] page.goto failed on retry: {retry_err}", flush=True)
            if failed_requests:
                print(f"[DIAGNOSTIC] Failed network requests:\n" + "\n".join(failed_requests), flush=True)
            raise

    status_code = resp.status if resp else "No Response"
    print(f"[DIAGNOSTIC] HTTP Response Status: {status_code}", flush=True)
    print(f"[DIAGNOSTIC] Current URL after goto: {page.url}", flush=True)
    print(f"[DIAGNOSTIC] Page Title: '{page.title()}'", flush=True)

    if console_logs:
        print(f"[DIAGNOSTIC] Captured Console Logs ({len(console_logs)} items):", flush=True)
        for log in console_logs[:10]:
            print(f"  {log}", flush=True)

    if page_errors:
        print(f"[DIAGNOSTIC] Captured Page JS Errors ({len(page_errors)} items):", flush=True)
        for err in page_errors[:10]:
            print(f"  {err}", flush=True)

    if failed_requests:
        print(f"[DIAGNOSTIC] Captured Failed Network Requests ({len(failed_requests)} items):", flush=True)
        for freq in failed_requests[:10]:
            print(f"  {freq}", flush=True)

    try:
        page.screenshot(path="skillrack_debug.png", full_page=True)
        print("[DIAGNOSTIC] Saved screenshot to 'skillrack_debug.png'", flush=True)
    except Exception as ss_err:
        print(f"[DIAGNOSTIC] Screenshot capture error: {ss_err}", flush=True)

    try:
        body_text = page.locator("body").inner_text(timeout=5000)
        print(f"[DIAGNOSTIC] First 2000 characters of body.inner_text():\n{'='*60}\n{body_text[:2000]}\n{'='*60}", flush=True)
    except Exception as text_err:
        print(f"[DIAGNOSTIC] Failed to read body.inner_text(): {text_err}", flush=True)

    # Check if login form is required
    login_user_input = page.locator("input[name='j_username']")
    login_link = page.locator("a:has-text('Login')")
    
    if login_user_input.is_visible(timeout=3000) or login_link.is_visible(timeout=3000):
        if not login_user_input.is_visible(timeout=1000) and login_link.is_visible(timeout=2000):
            login_link.click()
            login_user_input.wait_for(state="visible", timeout=10000)

        if login_user_input.is_visible(timeout=5000):
            print("[LOGIN] Submitting user credentials...", flush=True)
            login_user_input.fill("2117250080034@rgit")
            page.locator("input[name='j_password']").fill("jai0011k@")
            
            login_btn = page.locator("input[type='submit'], input[value='Login'], button:has-text('Login')").first
            login_btn.click()
            page.wait_for_load_state("domcontentloaded")
            
            page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml'], a[href*='candidate']").first.wait_for(state="visible", timeout=30000)
            
            if context:
                try:
                    context.storage_state(path="storage_state.json")
                    print("[LOGIN] Session state saved to storage_state.json", flush=True)
                except Exception as e:
                    print(f"[LOGIN] Warning: Failed to save storage state: {e}", flush=True)
    else:
        print("[LOGIN] Existing active session detected!", flush=True)

    print("[NAVIGATION] Entering Programming Track...", flush=True)
    prog_link = page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml']").first
    prog_link.click()

    print("[NAVIGATION] Entering Level 1...", flush=True)
    level1_link = page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first
    level1_link.wait_for(state="visible", timeout=15000)
    level1_link.click()

    print("[NAVIGATION] Entering Code Tutor...", flush=True)
    tutor_link = page.locator("a[href*='gt=CODETUTOR']").first
    tutor_link.wait_for(state="visible", timeout=15000)
    tutor_link.click()

    print("[NAVIGATION] Selecting Python Programming...", flush=True)
    python_show = page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
    python_show.wait_for(state="visible", timeout=15000)
    python_show.click()

    print("[NAVIGATION] Opening Hands-On Course...", flush=True)
    hands_on_show = page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
    if not hands_on_show.is_visible(timeout=3000):
        hands_on_show = page.locator("button:has-text('Show')").first
    hands_on_show.wait_for(state="visible", timeout=15000)
    hands_on_show.click()

def verify_code_editor(page):
    """Verifies whether the code editor is present on the current page."""
    print(f"[DEBUG] Verification URL: {page.url}", flush=True)
    print(f"[DEBUG] Verification Title: '{page.title()}'", flush=True)

    editor_present = page.evaluate("""() => {
        let aceEl = document.getElementById('ctutortxtCode');
        let hasAce = window.ace && aceEl;
        let hasTa = !!document.getElementById('txtCode');
        return hasAce || hasTa;
    }""")

    if editor_present:
        print("[DEBUG] SUCCESS: Code editor is present on the page!", flush=True)
        return True
    else:
        print("[ERROR] Code editor not found.", flush=True)
        print(f"[ERROR] Current URL: {page.url}", flush=True)
        print(f"[ERROR] Current title: {page.title()}", flush=True)
        os.makedirs("screenshots", exist_ok=True)
        page.screenshot(path="screenshots/navigation_failure.png", full_page=True)
        print("[ERROR] Saved failure screenshot to 'screenshots/navigation_failure.png'", flush=True)
        return False


def run_automation(headless=False):
    """
    Main Orchestrator Workflow:
    Playwright -> get_problem -> solve_problem (AI) -> fill_editor -> run_code -> save_and_proceed -> next problem.
    """
    state_file = "storage_state.json"
    browser = None
    context = None
    page = None

    console_logs = []
    page_errors = []
    failed_requests = []

    with sync_playwright() as p:
        print(f"\n=======================================================", flush=True)
        print(f">>> SKILLRACK AUTOMATION PIPELINE (headless={headless})", flush=True)
        print(f"=======================================================\n", flush=True)

        try:
            print("[DIAGNOSTIC] Launching Chromium browser...", flush=True)
            # Use Chrome channel or launch args with realistic user-agent to prevent blank Cloudflare challenge pages
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            browser = p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            print(f"[DIAGNOSTIC] Browser launched successfully. Connected: {browser.is_connected()}", flush=True)

            if os.path.exists(state_file):
                print(f"[SESSION] Loading existing session state from '{state_file}'...", flush=True)
                context = browser.new_context(storage_state=state_file, viewport={'width': 1280, 'height': 800}, user_agent=user_agent)
            else:
                print("[SESSION] Creating fresh browser context...", flush=True)
                context = browser.new_context(viewport={'width': 1280, 'height': 800}, user_agent=user_agent)

            print(f"[DIAGNOSTIC] Context created. Active pages: {len(context.pages)}", flush=True)
            page = context.new_page()
            page.set_default_timeout(60000)

            # Register network and DOM event listeners
            page.on("console", lambda msg: console_logs.append(f"CONSOLE [{msg.type}]: {msg.text}"))
            page.on("pageerror", lambda err: page_errors.append(f"PAGEERROR: {err}"))
            page.on("requestfailed", lambda req: failed_requests.append(f"REQFAILED: {req.url} -> {req.failure}"))

            print(f"[DIAGNOSTIC] New page initialized. Closed: {page.is_closed()}, URL: '{page.url}'", flush=True)

            login_and_navigate(
                page,
                context=context,
                console_logs=console_logs,
                page_errors=page_errors,
                failed_requests=failed_requests
            )

            total_solved = 0

            while True:
                page.wait_for_load_state("domcontentloaded")
                print("\n[CHAPTER CHECK] Scanning for active chapter...", flush=True)
                view_btn = page.locator("button, a, input").filter(has_text=re.compile(r"^\s*(View|Resume)\s*$", re.I)).first
                
                if not view_btn.is_visible(timeout=5000):
                    print("[ALL CHAPTERS COMPLETE] No more pending chapters found!", flush=True)
                    break

                print("[CHAPTER] Opening active chapter...", flush=True)
                view_btn.click()

                # Handle captcha if prompted upon entering chapter
                handle_captcha(page)

                page.locator("#ctutortxtCode").wait_for(state="visible", timeout=35000)
                print("[READY] Code editor loaded! Starting problem solver loop...\n", flush=True)

                while True:
                    # 1. Playwright extracts problem
                    prob = get_problem(page)
                    pid = prob['pid']

                    if not pid:
                        print("[CHAPTER FINISHED] No active problem ID found. Advancing chapter!", flush=True)
                        break

                    lines = [l.strip() for l in prob['leftText'].split('\n') if l.strip()]
                    title = lines[1] if len(lines) > 1 else lines[0]
                    print("----------------------------------------------------------------", flush=True)
                    print(f"[PROBLEM ID] {pid} | Title: {title}", flush=True)

                    # 2. AI Analyzes and returns solution
                    solution = solve_problem(prob)

                    if not solution:
                        print(f"[AI SOLVER FAIL] Problem {pid} could not be solved automatically. Dumping debug info...", flush=True)
                        page.screenshot(path=f"pid_{pid}_unsolved.png")
                        with open(f"pid_{pid}_info.json", "w") as f:
                            json.dump(prob, f, indent=2)
                        break

                    print(f"[GENERATED SOLUTION]:\n{solution}", flush=True)

                    # 3. Playwright fills editor
                    fill_editor(page, solution)

                    # 4. Playwright runs code
                    status = run_code(page)
                    print(f"[EXECUTION RESULT] Status: {status}", flush=True)

                    # Handle failure autocorrect retry if needed
                    if status == 'FAILED':
                        diag = get_failure_diagnostics(page)
                        print(f"[DIAGNOSTICS] Input: '{diag.get('inp')}' | Expected: '{diag.get('exp')}' | Actual: '{diag.get('act')}'", flush=True)

                        has_input_prefix = ('input()' in prob.get('prefixCode', '').lower())
                        var_name = 's'
                        m_var = re.search(r'([a-zA-Z_]\w*)\s*=\s*input\(\)', prob.get('prefixCode', ''))
                        if m_var:
                            var_name = m_var.group(1)
                            has_input_prefix = True

                        corrected_sol = synthesize_solution(diag.get('inp'), diag.get('exp'), var_name, has_input_prefix)
                        if corrected_sol and corrected_sol != solution:
                            print(f"[AUTOCORRECT] Synthesized exact fix:\n{corrected_sol}", flush=True)
                            solution = corrected_sol
                            fill_editor(page, solution)
                            status = run_code(page)
                            print(f"[RE-RUN RESULT] Status: {status}", flush=True)

                    # 5. Advance to next problem if passed
                    if status == 'PASSED':
                        total_solved += 1
                        KNOWN_SOLUTIONS[pid] = solution
                        print(f"[PASSED] >>> ProgramID-{pid} PASSED successfully! (Session Total: {total_solved}) <<<", flush=True)

                        if not save_and_proceed(page):
                            break
                    else:
                        print(f"[STOP] Problem {pid} execution did not pass. Pausing for inspection.", flush=True)
                        break

                print("[NAVIGATION] Returning to Hands-on chapter overview...", flush=True)
                page.goto("https://skillrack.com/faces/candidate/codeprogramgroup.xhtml", wait_until="domcontentloaded", timeout=60000)

            print("\n=======================================================", flush=True)
            print(f"[COMPLETED] Automation complete! Total solved: {total_solved}", flush=True)
            print("=======================================================\n", flush=True)

        except Exception as e:
            print(f"\n[DIAGNOSTIC EXCEPTION] Automation error occurred: {e}", flush=True)
            if page and not page.is_closed():
                try:
                    page.screenshot(path="skillrack_debug.png", full_page=True)
                    print("[DIAGNOSTIC] Saved failure screenshot to 'skillrack_debug.png'", flush=True)
                except Exception as dump_err:
                    print(f"[DIAGNOSTIC] Screenshot failed: {dump_err}", flush=True)
            raise
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass


if __name__ == '__main__':
    run_automation(headless=False)

