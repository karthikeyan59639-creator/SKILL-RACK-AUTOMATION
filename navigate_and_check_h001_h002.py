from playwright.sync_api import sync_playwright
from PIL import Image
import base64, io, re, json, time

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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(120000)

    print("\n[LOGIN] Navigating to SkillRack...", flush=True)
    for attempt in range(5):
        try:
            page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="domcontentloaded", timeout=60000)
            break
        except Exception as e:
            print(f"Retry login load {attempt+1}: {e}", flush=True)
            page.wait_for_timeout(2000)

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

    print("[NAV] Level 1 -> Code Tutor...", flush=True)
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

    # We are on the chapters list page!
    page.screenshot(path="chapters_actual_status.png", full_page=True)

    chapters_info = page.evaluate("""() => {
        let rows = Array.from(document.querySelectorAll('.card, tr, .ui-panel, div[class*="chapter"], div')).filter(el => {
            let t = el.innerText || '';
            return t.includes('Python3-H001') || t.includes('Python3-H002');
        });
        
        let results = [];
        let allText = document.body.innerText;
        return { allText: allText };
    }""")

    print("\n=== CHAPTERS PAGE TEXT ===")
    for line in chapters_info['allText'].split('\n'):
        if any(k in line for k in ['Python3-H00', 'Units', '%', 'Basics', 'Strings']):
            print("  ", line.strip(), flush=True)

    # Check if H001 is 100%
    text_dump = chapters_info['allText']
    if 'Python3-H001 Basics' in text_dump:
        # Check progress string
        match = re.search(r'Python3-H001 Basics[\s\S]*?(\d+)%', text_dump)
        pct = match.group(1) if match else 'Unknown'
        print(f"\n[STATUS] Python3-H001 Basics Completion: {pct}%\n", flush=True)

        if pct == '100':
            print("[MILESTONE] Python3-H001 Basics is 100% COMPLETE! Advancing to Python3-H002 Strings...", flush=True)
            # Find and click View button for Python3-H002 Strings
            h002_btn = page.locator("tr, .card, div").filter(has_text="Python3-H002 Strings").locator("button:has-text('View')").first
            if not h002_btn.is_visible():
                # Second view button on page
                h002_btn = page.locator("button:has-text('View')").nth(1)
            h002_btn.click()
            page.wait_for_timeout(4000)
            page.screenshot(path="h002_strings_entry.png", full_page=True)
            print("[SUCCESS] Entered Python3-H002 Strings! Screenshot saved to h002_strings_entry.png", flush=True)
        else:
            print(f"[REMAINING] H001 is at {pct}%. Opening H001 to complete remaining problem...", flush=True)
            page.locator("button:has-text('View')").first.click()
            page.wait_for_timeout(3000)

            # Check captcha
            if page.locator("#codeeditorpanel img").is_visible():
                img_el = page.locator("#codeeditorpanel img").first
                img_el.wait_for(state="visible", timeout=30000)
                ans = solve_captcha(img_el.get_attribute("src"))
                print(f"[CAPTCHA] Solved: {ans}", flush=True)
                page.locator("#capval").fill(ans)
                page.locator("#proceedbtn").click()
                page.wait_for_timeout(4000)

            page.locator("#ctutortxtCode").wait_for(state="visible", timeout=30000)
            page.screenshot(path="problem_10_loaded.png", full_page=True)

            prob_details = page.evaluate("""() => {
                let el = document.querySelector('#programgrid') || document.body;
                let edVal = window.ace ? ace.edit('ctutortxtCode').getValue() : '';
                let codeDiv = document.querySelector('#codediv');
                return {
                    leftText: el.innerText,
                    edVal: edVal,
                    suffixCode: codeDiv ? codeDiv.innerText.trim() : ''
                };
            }""")
            print("=== PROBLEM 10 DETAILS ===")
            print(prob_details['leftText'][:600])
            print("Suffix:", repr(prob_details['suffixCode']))
            print("Editor:", repr(prob_details['edVal']))

    browser.close()
