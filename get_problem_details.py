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

# The working template matching from inspect_run.py:
TEMPLATES_EXACT = {
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
        for ch, templ in TEMPLATES_EXACT.items():
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
    page.set_default_timeout(120000)

    print("Navigating to SkillRack...")
    page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="domcontentloaded", timeout=60000)
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

    # Click first chapter View button (Python3-H001 Basics)
    page.locator("button:has-text('View')").first.click()
    page.wait_for_timeout(3000)

    # Captcha handling
    if page.locator("#codeeditorpanel img").is_visible():
        img_el = page.locator("#codeeditorpanel img").first
        img_el.wait_for(state="visible", timeout=30000)
        src = img_el.get_attribute("src")
        ans = solve_captcha(src)
        print("Captcha solution:", ans)
        page.locator("#capval").fill(ans)
        page.locator("#proceedbtn").click()
        page.wait_for_timeout(4000)

    page.locator("#ctutortxtCode").wait_for(state="visible", timeout=30000)
    print("Editor revealed!")

    page.screenshot(path="current_problem.png", full_page=True)

    details = page.evaluate("""() => {
        let leftPanel = document.querySelector('#programgrid') || document.querySelector('.ui-g-12.ui-md-6') || document.body;
        let edVal = window.ace ? ace.edit('ctutortxtCode').getValue() : '';
        
        // Find pre and post code elements around editor
        let codeArea = document.querySelector('#codeeditorpanel') || document.body;
        let textSnippets = Array.from(codeArea.querySelectorAll('div, pre, span, p')).map(el => ({
            tag: el.tagName,
            id: el.id,
            className: el.className,
            text: el.innerText
        })).filter(x => x.text && x.text.trim().length > 0);

        return {
            leftText: leftPanel.innerText,
            editorCode: edVal,
            snippets: textSnippets.slice(0, 15)
        };
    }""")

    print("=== FULL LEFT PANEL ===")
    print(details['leftText'])
    print("=== CURRENT ACE EDITOR CODE ===")
    print(repr(details['editorCode']))
    print("=== CODE AREA SNIPPETS ===")
    print(json.dumps(details['snippets'], indent=2))

    browser.close()
