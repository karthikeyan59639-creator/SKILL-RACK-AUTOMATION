from playwright.sync_api import sync_playwright
from PIL import Image
import base64, io, re

# Pre-defined bitmap templates for SkillRack math captcha digits & operators
TEMPLATES = {
    '0': (
        '.####.'
        '.#..#.'
        '#....#'
        '#....#'
        '#....#'
        '#....#'
        '#....#'
        '.#..#.'
        '.####.'
    ),
    '1': (
        '###..'
        '..#..'
        '..#..'
        '..#..'
        '..#..'
        '..#..'
        '..#..'
        '..#..'
        '#####'
    ),
    '2': (
        '.####.'
        '#...##'
        '.....#'
        '.....#'
        '....#.'
        '...#..'
        '..#...'
        '.#....'
        '######'
    ),
    '3': (
        '.####.'
        '#....#'
        '.....#'
        '.....#'
        '..###.'
        '.....#'
        '.....#'
        '#....#'
        '.####.'
    ),
    '4': (
        '...##.'
        '...##.'
        '..#.#.'
        '.#..#.'
        '.#..#.'
        '#...#.'
        '######'
        '....#.'
        '....#.'
    ),
    '5': (
        '#####.'
        '#.....'
        '#.....'
        '#####.'
        '....##'
        '.....#'
        '.....#'
        '#...##'
        '.####.'
    ),
    '6': (
        '..###.'
        '.#...#'
        '#.....'
        '#.###.'
        '##..##'
        '#....#'
        '#....#'
        '.#..##'
        '.####.'
    ),
    '7': (
        '######'
        '.....#'
        '....#.'
        '....#.'
        '...#..'
        '...#..'
        '..#...'
        '..#...'
        '.#....'
    ),
    '8': (
        '.####.'
        '#....#'
        '#....#'
        '#....#'
        '.####.'
        '#....#'
        '#....#'
        '#....#'
        '.####.'
    ),
    '9': (
        '.####.'
        '##..#.'
        '#....#'
        '#....#'
        '##..##'
        '.###.#'
        '.....#'
        '#...#.'
        '.###..'
    ),
    '+': (
        '...#...'
        '...#...'
        '...#...'
        '#######'
        '...#...'
        '...#...'
        '...#...'
    ),
    '-': (
        '######'
    ),
    '=': (
        '########'
        '########'
    )
}

def solve_captcha(b64_str):
    """Decodes SkillRack's base64 captcha image and evaluates the math equation."""
    if ',' in b64_str:
        b64_str = b64_str.split(',', 1)[1]
    b64_str = b64_str.strip()
    b64_str += '=' * (-len(b64_str) % 4)

    im = Image.open(io.BytesIO(base64.b64decode(b64_str))).convert('L')
    pixels = im.load()
    w, h = im.size

    # The math expression is located in rows 30 to 44
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
    print("Parsed math expression:", expr)
    m = re.match(r'(\d+)\s*([\+\-\*\/])\s*(\d+)', expr)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        ans = a + b if op == '+' else a - b if op == '-' else a * b
        return str(ans)
    return expr

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    # Step 1: Login
    print("Step 1: Navigating to SkillRack login page...")
    page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2000)

    if not page.locator("input[name='j_username']").is_visible():
        if page.locator("a:has-text('Login')").is_visible():
            page.locator("a:has-text('Login')").click()
            page.wait_for_timeout(2000)

    page.locator("input[name='j_username']").wait_for(state="visible", timeout=30000)
    page.locator("input[name='j_username']").fill("2117250080034@rgit")
    page.locator("input[name='j_password']").fill("jai0011k@")
    page.locator("input[type='submit']").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Step 2: Click the second option in the menu (<> Programming)
    print("Step 2: Clicking Programming in menu...")
    page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml']").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Step 3: Click 'View' option in Level 1
    print("Step 3: Clicking View on Level 1...")
    page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Step 4: Click 'View' below Learn C, Java, Python, SQL and Data Structures
    print("Step 4: Clicking View below Learn C, Java, Python, SQL, Data Structures...")
    page.locator("a[href*='gt=CODETUTOR']").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Step 5: Click 'Show' below Python Programming Standard
    print("Step 5: Clicking Show below Python Programming Standard...")
    page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Step 6: Click 'Show' below Python 3.x - Programming Course (Hands-On)
    print("Step 6: Clicking Show below Python 3.x - Programming Course (Hands-On)...")
    page.locator("button:has-text('Show')").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Step 7: Click first 'View' option under Python3-H001 Basics
    print("Step 7: Clicking first View option (Python3-H001 Basics)...")
    page.locator("button:has-text('View')").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    # Step 8: Solve the math question (captcha)
    print("Step 8: Reading and solving the math question...")
    img_el = page.locator("#codeeditorpanel img").first
    src = img_el.get_attribute("src")
    captcha_answer = solve_captcha(src)
    print("Calculated answer:", captcha_answer)

    page.locator("#capval").fill(captcha_answer)
    page.wait_for_timeout(1000)

    # Step 9: Click 'Proceed to Solve the Program'
    print("Step 9: Clicking 'Proceed to Solve the Program'...")
    page.locator("#proceedbtn").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(4000)

    # Step 10: Type the solution into the Ace Code Editor
    # Problem: "Fill in the missing lines of code to define variables x and y so that the program prints 100."
    print("Step 10: Typing solution code into editor...")
    solution_code = "x = 10\ny = 10\nprint (x*y)"
    page.evaluate(f"""() => {{
        let ed = window.ace ? ace.edit('ctutortxtCode') : null;
        if (ed) {{
            ed.setValue({repr(solution_code)}, 1);
        }}
        let ta = document.getElementById('txtCode');
        if (ta) {{
            ta.value = {repr(solution_code)};
        }}
    }}""")
    page.wait_for_timeout(1000)

    # Step 11: Click 'Save' option
    print("Step 11: Clicking Save button...")
    page.locator("button:has-text('Save'), input[value='Save'], a:has-text('Save')").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    # Capture screenshot confirming the code was saved
    page.screenshot(path="after_save.png", full_page=True)
    print("Saved confirmation screenshot to after_save.png")

    # Keep browser visible for viewing
    page.wait_for_timeout(5000)
    browser.close()