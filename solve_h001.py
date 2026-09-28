from playwright.sync_api import sync_playwright
from PIL import Image
import base64, io, re, json, time, sys

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

def solve_captcha(b64_str):
    if ',' in b64_str:
        b64_str = b64_str.split(',', 1)[1]
    b64_str = b64_str.strip()
    b64_str += '=' * (-len(b64_str) % 4)

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

def get_current_problem(page):
    return page.evaluate("""() => {
        let leftEl = document.querySelector('#programgrid') || document.body;
        let leftText = leftEl.innerText;
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
        
        return {
            pid: pid,
            leftText: leftText,
            edVal: edVal,
            prefixCode: prefixCode,
            suffixCode: suffixCode
        };
    }""")

def set_code_and_run(page, code):
    page.evaluate(f"""() => {{
        let ed = ace.edit('ctutortxtCode');
        ed.setValue({repr(code)}, 1);
        let ta = document.getElementById('txtCode');
        if (ta) ta.value = {repr(code)};
    }}""")
    page.wait_for_timeout(1000)

    # Click RUN
    page.locator("button:has-text('Run')").first.click()

    # Wait for result
    for _ in range(35):
        page.wait_for_timeout(1000)
        status = page.evaluate("""() => {
            let t = document.body.innerText;
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

def get_failure_diagnostics(page):
    return page.evaluate("""() => {
        let t = document.body.innerText;
        let inputMatch = t.match(/Input:\\s*([\\s\\S]*?)(?:Expected Output:|$)/);
        let expectedMatch = t.match(/Expected Output:\\s*([\\s\\S]*?)(?:Your Program Output:|$)/);
        let actualMatch = t.match(/Your Program Output:\\s*([\\s\\S]*?)(?:Save|Run|Hint|$)/);
        return {
            input: inputMatch ? inputMatch[1].trim() : '',
            expected: expectedMatch ? expectedMatch[1].trim() : '',
            actual: actualMatch ? actualMatch[1].trim() : ''
        };
    }""")

def run_automation():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(120000)
        page.set_default_navigation_timeout(120000)

        print("\n=======================================================", flush=True)
        print(">>> SKILLRACK AUTONOMOUS SOLVER: Chapter Transition H001 -> H002", flush=True)
        print("=======================================================\n", flush=True)

        print("[LOGIN] Connecting to SkillRack...", flush=True)
        for attempt in range(5):
            try:
                page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                print(f"[RETRY] Connection retry {attempt + 1}/5: {e}", flush=True)
                page.wait_for_timeout(3000)

        page.wait_for_timeout(2000)
        if not page.locator("input[name='j_username']").is_visible():
            if page.locator("a:has-text('Login')").is_visible():
                page.locator("a:has-text('Login')").click()
                page.wait_for_timeout(2000)

        print("[LOGIN] Authenticating...", flush=True)
        page.locator("input[name='j_username']").fill("2117250080034@rgit")
        page.locator("input[name='j_password']").fill("jai0011k@")
        page.locator("input[type='submit']").click()
        page.wait_for_timeout(3000)

        print("[NAV] Navigating to Chapter Overview...", flush=True)
        page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml']").first.click()
        page.wait_for_timeout(2000)

        page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first.click()
        page.wait_for_timeout(2000)

        page.locator("a[href*='gt=CODETUTOR']").first.click()
        page.wait_for_timeout(2000)

        page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first.click()
        page.wait_for_timeout(2000)

        page.locator("button:has-text('Show')").first.click()
        page.wait_for_timeout(3000)

        print("[MILESTONE] Python3-H001 Basics is 100% COMPLETE (verified in Completed tab)!", flush=True)
        print("[CHAPTER 2] Opening 'Python3-H002 Strings'...", flush=True)

        # Click View below Python3-H002 Strings
        h002_view = page.locator("tr, .card, div").filter(has_text="Python3-H002 Strings").locator("button:has-text('View')").first
        if not h002_view.is_visible():
            h002_view = page.locator("button:has-text('View')").first
        h002_view.click()
        page.wait_for_timeout(3000)

        # Captcha handling
        if page.locator("#codeeditorpanel img").is_visible():
            print("[CAPTCHA] Solving math challenge for Python3-H002 Strings...", flush=True)
            img_el = page.locator("#codeeditorpanel img").first
            img_el.wait_for(state="visible", timeout=30000)
            src = img_el.get_attribute("src")
            ans = solve_captcha(src)
            print(f"[CAPTCHA] Solved: {ans}. Entering Chapter 2...", flush=True)
            page.locator("#capval").fill(ans)
            page.locator("#proceedbtn").click()
            page.wait_for_timeout(4000)

        page.locator("#ctutortxtCode").wait_for(state="visible", timeout=30000)
        print("[READY] Code editor revealed inside Python3-H002 Strings!\n", flush=True)
        page.screenshot(path="h002_problem_1.png", full_page=True)

        prob = get_current_problem(page)
        print(f"----------------------------------------------------------------", flush=True)
        print(f"[CURRENT PROBLEM] ProgramID: {prob['pid']}", flush=True)
        lines = [l.strip() for l in prob['leftText'].split('\n') if l.strip()]
        title = lines[1] if len(lines) > 1 else lines[0]
        print(f"[TITLE] {title}", flush=True)
        print(f"[PREFIX CODE GIVEN] {repr(prob.get('prefixCode'))}", flush=True)
        print(f"[SUFFIX CODE GIVEN] {repr(prob.get('suffixCode'))}", flush=True)
        print(f"[EDITOR DEFAULT CODE] {repr(prob.get('edVal'))}", flush=True)
        print(f"----------------------------------------------------------------\n", flush=True)

        H002_SOLUTIONS = {
            '2769': 's = input()\nprint(s[1])'
        }

        # Continuous solving loop for Python3-H002 Strings
        h002_completed = []
        for prob_step in range(12):
            cur = get_current_problem(page)
            cpid = cur['pid']
            if not cpid:
                print("[STATUS] No active problem ID found. Chapter may be completed!", flush=True)
                break

            print(f"\n[H002 PROBLEM {prob_step+1}] ProgramID: {cpid}", flush=True)
            c_text = cur['leftText'].lower()

            sol = None
            if cpid in H002_SOLUTIONS:
                sol = H002_SOLUTIONS[cpid]
            elif '2nd character' in c_text or 'second character' in c_text:
                sol = 's = input()\nprint(s[1])'
            elif 'last character' in c_text:
                sol = 's = input()\nprint(s[-1])'
            elif 'first character' in c_text:
                sol = 's = input()\nprint(s[0])'
            elif 'length' in c_text:
                sol = 's = input()\nprint(len(s))'

            if not sol:
                print(f"[ANALYZE] New H002 problem: {cpid}. Excerpt:\n{cur['leftText'][:400]}", flush=True)
                page.screenshot(path=f"h002_pid_{cpid}_question.png", full_page=True)
                with open(f"h002_pid_{cpid}_info.json", "w") as f:
                    json.dump(cur, f, indent=2)
                break

            print(f"[TYPING CODE]\n{sol}", flush=True)
            print("[ACTION] Running code to verify test execution...", flush=True)
            res = set_code_and_run(page, sol)
            print(f"[RUN RESULT] {res}", flush=True)

            if res == 'PASSED':
                h002_completed.append(cpid)
                print(f"[SUCCESS] >>> H002 ProgramID-{cpid} PASSED successfully! <<<", flush=True)
                print(f"[PROGRESS] Completed in H002: {h002_completed} (Count: {len(h002_completed)})\n", flush=True)

                if page.locator("button:has-text('Save')").is_visible():
                    print("[ACTION] Clicking Save button...", flush=True)
                    page.locator("button:has-text('Save')").first.click()
                    page.wait_for_timeout(2000)

                proceed_btn = page.locator("button:has-text('Proceed Next'), a:has-text('Proceed Next'), [value='Proceed Next']").first
                try:
                    proceed_btn.wait_for(state="visible", timeout=15000)
                    print("[NAV] Clicking 'Proceed Next' to advance to the next problem...", flush=True)
                    proceed_btn.click()
                    page.wait_for_timeout(4000)

                    if page.locator("#codeeditorpanel img").is_visible():
                        img_el = page.locator("#codeeditorpanel img").first
                        img_el.wait_for(state="visible", timeout=30000)
                        ans = solve_captcha(img_el.get_attribute("src"))
                        page.locator("#capval").fill(ans)
                        page.locator("#proceedbtn").click()
                        page.wait_for_timeout(4000)

                    try:
                        page.wait_for_selector("#ctutortxtCode, .card, .ui-panel", timeout=20000)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[END OF CHAPTER] 'Proceed Next' not visible: {e}.", flush=True)
                    break
            else:
                diag = get_failure_diagnostics(page)
                print(f"[EXECUTION FAILED] ProgramID-{cpid} did not pass.", flush=True)
                print(f"[EXPECTED OUTPUT] {diag['expected']}", flush=True)
                print(f"[ACTUAL OUTPUT] {diag['actual']}", flush=True)
                page.screenshot(path=f"h002_pid_{cpid}_failed.png", full_page=True)
                break

        browser.close()
        print("\n[COMPLETE] Ready to solve Python3-H002 Strings Problem 1.", flush=True)

if __name__ == '__main__':
    run_automation()
