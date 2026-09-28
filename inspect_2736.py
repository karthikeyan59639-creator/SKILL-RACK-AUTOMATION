from playwright.sync_api import sync_playwright
from PIL import Image
import base64, io, re, json

TEMPLATES = {
    '0': '.####..#..#.##....##....##....##....##....#.####.',
    '1': '###....#....#....#....#....#....#....#####',
    '2': '.####.#...##.....#.....#....#...#....#....######',
    '3': '.####.#....#.....#.....#..###......#.....##....#.####.',
    '4': '...##....##...#.#..#..#..#..##...#.######....#....#.',
    '5': '######.....#.....######....##.....#.....##...##.####.',
    '6': '..###..#...##.....#.###.##..###....##....#.#..##.####.',
    '7': '######.....#....#....#...#...#....#....#....#....',
    '8': '.####.#....##....##....#.####.#....##....##....#.####.',
    '9': '.####.##..#.##....##....###..##.###.#.....##...#.###..',
    '+': '...#......#......#...#######...#......#......#...',
    '-': '######',
    '=': '################'
}

TEMPLATES_EXACT = {
    '0': '.####..#..#.##....##....##....##....##....#.####.',
    '1': '###....#....#....#....#....#....#....#####',
    '2': '.####.#...##.....#.....#....#...#....#....######',
    '3': '.####.#....#.....#.....#..###......#.....##....#.####.',
    '4': '...##....##...#.#..#..#..#..##...#.######....#....#.',
    '5': '######.....#.....######....##.....#.....##...##.####.',
    '6': '..###..#...##.....#.###.##..###....##....#.#..##.####.',
    '7': '######.....#....#....#...#...#....#....#....#....',
    '8': '.####.#....##....##....#.####.#....##....##....#.####.',
    '9': '.####.##..#.##....##....###..##.###.#.....##...#.###..',
    '+': '...#......#......#...#######...#......#......#...',
    '-': '######',
    '=': '################'
}

TEMPLATES_TUPLE = {
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
        for ch, templ in TEMPLATES_TUPLE.items():
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

    for attempt in range(5):
        try:
            page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="commit", timeout=25000)
            page.wait_for_load_state("domcontentloaded", timeout=25000)
            break
        except Exception:
            page.wait_for_timeout(2000)

    page.wait_for_timeout(2000)
    if not page.locator("input[name='j_username']").is_visible():
        if page.locator("a:has-text('Login')").is_visible():
            page.locator("a:has-text('Login')").click()
            page.wait_for_timeout(2000)

    page.locator("input[name='j_username']").fill("2117250080034@rgit")
    page.locator("input[name='j_password']").fill("jai0011k@")
    page.locator("input[type='submit']").click()
    page.wait_for_timeout(3000)

    page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml']").first.click()
    page.wait_for_timeout(2000)

    page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first.click()
    page.wait_for_timeout(2000)

    page.locator("a[href*='gt=CODETUTOR']").first.click()
    page.wait_for_timeout(2000)

    page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first.click()
    page.wait_for_timeout(2000)

    page.locator("button:has-text('Show')").first.click()
    page.wait_for_timeout(2000)

    page.locator("button:has-text('View')").first.click()
    page.wait_for_timeout(3000)

    if page.locator("#codeeditorpanel img").is_visible():
        img_el = page.locator("#codeeditorpanel img").first
        img_el.wait_for(state="visible", timeout=30000)
        src = img_el.get_attribute("src")
        ans = solve_captcha(src)
        page.locator("#capval").fill(ans)
        page.locator("#proceedbtn").click()
        page.wait_for_timeout(4000)

    page.locator("#ctutortxtCode").wait_for(state="visible", timeout=30000)

    # Check if Hint button exists
    hint_btn = page.locator("button:has-text('Hint'), a:has-text('Hint')").first
    if hint_btn.is_visible():
        hint_btn.click()
        page.wait_for_timeout(2000)
        print("HINT CONTENT:")
        hint_text = page.evaluate("""() => {
            let dialog = document.querySelector('.ui-dialog, .ui-dialog-content, #hintdialog');
            return dialog ? dialog.innerText : document.body.innerText;
        }""")
        print(hint_text[:500])

    # Now let's test running code to see the Expected Output!
    print("Testing with mymessage = ''...")
    page.evaluate("""() => {
        let ed = ace.edit('ctutortxtCode');
        ed.setValue('mymessage = ""', 1);
        let ta = document.getElementById('txtCode');
        if (ta) ta.value = 'mymessage = ""';
    }""")
    page.wait_for_timeout(1000)
    page.locator("button:has-text('Run')").first.click()
    page.wait_for_timeout(6000)

    page.screenshot(path="test_2736_run.png", full_page=True)
    body_text = page.evaluate("() => document.body.innerText")
    print("BODY TEXT AFTER RUN:")
    for line in body_text.split('\n'):
        if any(k in line.lower() for k in ['expected', 'output', 'input', 'program output', 'message', 'error', 'hint']):
            print("  ->", line.strip(), flush=True)

    browser.close()
