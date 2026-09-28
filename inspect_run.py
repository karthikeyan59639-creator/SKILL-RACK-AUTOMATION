from playwright.sync_api import sync_playwright
from PIL import Image
import base64, io, re

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
    if ',' in b64_str:
        b64_str = b64_str.split(',', 1)[1]
    b64_str = b64_str.strip()
    b64_str += '=' * (-len(b64_str) % 4)

    raw_bytes = base64.b64decode(b64_str)
    with open("current_captcha.png", "wb") as f:
        f.write(raw_bytes)

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
        print(f"Segment ({s},{e}) width {e-s+1} -> {best_char} (score {best_score}):")
        for line in pat_lines:
            print("  ", line)

    expr = ''.join(c for c in chars if c != '=')
    print("Parsed math expression:", expr)
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

    # Click first chapter View button
    page.locator("button:has-text('View')").first.click()
    page.wait_for_timeout(3000)

    # Solve captcha
    img_el = page.locator("#codeeditorpanel img").first
    img_el.wait_for(state="visible", timeout=30000)
    src = img_el.get_attribute("src")
    ans = solve_captcha(src)
    print("Captcha solution:", ans)
    page.locator("#capval").fill(ans)
    page.locator("#proceedbtn").click()
    page.wait_for_timeout(4000)

    # Check if editor revealed or error
    if page.locator("#ctutortxtCode").is_visible():
        print("SUCCESS! Editor revealed.")
        page.screenshot(path="editor_ready.png")

        # 1. Read left problem description
        prob_info = page.evaluate("""() => {
            let leftEl = document.querySelector('#programgrid') || document.querySelector('.ui-g-12.ui-md-6') || document.body;
            let currentCode = ace.edit('ctutortxtCode').getValue();
            return {
                leftText: leftEl.innerText,
                currentCode: currentCode
            };
        }""")
        print("=== PROBLEM STATEMENT ===")
        print(prob_info['leftText'][:600])
        print("=== CURRENT EDITOR CODE ===")
        print(repr(prob_info['currentCode']))

        # 2. Type necessary solution: city = "Chennai"
        print("Setting solution in editor...")
        page.evaluate("""() => {
            let ed = ace.edit('ctutortxtCode');
            ed.setValue('city = "Chennai"', 1);
            let ta = document.getElementById('txtCode');
            if (ta) ta.value = 'city = "Chennai"';
        }""")
        page.wait_for_timeout(1000)

        # 3. Click RUN button first
        print("Clicking RUN button...")
        run_btn = page.locator("button:has-text('Run')").first
        run_btn.click()

        print("Waiting 6 seconds after Run...")
        page.wait_for_timeout(6000)
        page.screenshot(path="after_run_result.png", full_page=True)

        run_output = page.evaluate("""() => {
            let visibleTexts = Array.from(document.querySelectorAll('*'))
                .filter(el => el.children.length === 0 && (el.innerText || '').trim().length > 0 && el.offsetParent !== null)
                .map(el => ({ tag: el.tagName, id: el.id, class: el.className, text: el.innerText.trim() }));
            return visibleTexts;
        }""")
        print("=== VISIBLE TEXTS AFTER RUN ===")
        for item in run_output:
            t = item['text'].lower()
            if any(k in t for k in ['test', 'pass', 'fail', 'output', 'congrat', 'error', 'result', 'actual', 'expected', 'chennai']):
                print(f"[{item['tag']} #{item['id']} .{item['class']}]: {item['text']}")

        # 4. Click SAVE button
        print("Clicking SAVE button...")
        save_btn = page.locator("button:has-text('Save')").first
        save_btn.click()

        print("Waiting 6 seconds after Save...")
        page.wait_for_timeout(6000)
        page.screenshot(path="after_save_result.png", full_page=True)

        after_save_info = page.evaluate("""() => {
            let buttons = Array.from(document.querySelectorAll('button, a, input[type="button"]'))
                .filter(b => b.offsetParent !== null && (b.innerText || b.value || '').trim().length > 0)
                .map(b => ({
                    tag: b.tagName,
                    id: b.id,
                    text: (b.innerText || b.value || '').trim(),
                    href: b.getAttribute('href'),
                    onclick: b.getAttribute('onclick')
                }));
            let messages = Array.from(document.querySelectorAll('.ui-growl, .ui-dialog, .ui-messages'))
                .filter(m => m.offsetParent !== null)
                .map(m => m.innerText.trim());
            return { buttons, messages };
        }""")
        print("=== BUTTONS AFTER SAVE ===")
        print(json.dumps(after_save_info['buttons'], indent=2))
        print("=== MESSAGES AFTER SAVE ===")
        print(json.dumps(after_save_info['messages'], indent=2))

    else:
        print("Editor not visible. Captcha error or still loading.")
        page.screenshot(path="editor_error.png")

    browser.close()

