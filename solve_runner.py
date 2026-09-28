from playwright.sync_api import sync_playwright
from PIL import Image
import base64, io, re, json, time

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
    print("Parsed math expression:", expr)
    m = re.match(r'(\d+)\s*([\+\-\*\/])\s*(\d+)', expr)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        ans = a + b if op == '+' else a - b if op == '-' else a * b
        return str(ans)
    return expr

def navigate_with_retry(page, url, max_retries=3):
    for i in range(max_retries):
        try:
            print(f"Navigating to {url} (attempt {i+1})...")
            page.goto(url, wait_until="commit", timeout=30000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            return True
        except Exception as e:
            print(f"Attempt {i+1} error: {e}")
            page.wait_for_timeout(2000)
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(60000)

    # 1. Login
    navigate_with_retry(page, "https://skillrack.com/faces/ui/profile.xhtml")
    page.wait_for_timeout(2000)

    if not page.locator("input[name='j_username']").is_visible():
        if page.locator("a:has-text('Login')").is_visible():
            page.locator("a:has-text('Login')").click()
            page.wait_for_timeout(2000)

    page.locator("input[name='j_username']").fill("2117250080034@rgit")
    page.locator("input[name='j_password']").fill("jai0011k@")
    page.locator("input[type='submit']").click()
    page.wait_for_timeout(3000)

    # 2. Programming -> Level 1 -> Code Tutor -> Python Standard -> Hands-On
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

    # 3. Wait for either captcha OR editor
    print("Waiting for captcha or editor to appear...")
    page.wait_for_selector("#codeeditorpanel img, #ctutortxtCode, .ace_editor", timeout=45000)

    # Handle captcha if visible
    for attempt in range(5):
        if page.locator("#codeeditorpanel img").is_visible():
            print(f"Captcha visible (attempt {attempt+1}), solving...")
            img_el = page.locator("#codeeditorpanel img").first
            src = img_el.get_attribute("src")
            ans = solve_captcha(src)
            print("Captcha solution:", ans)
            page.locator("#capval").fill(ans)
            page.locator("#proceedbtn").click()
            page.wait_for_timeout(4000)
            if page.locator("#ctutortxtCode, .ace_editor").first.is_visible():
                print("Editor revealed!")
                break
            else:
                print("Incorrect captcha or not yet revealed, refreshing captcha...")
                page.locator("#codeeditorpanel img").first.click()
                page.wait_for_timeout(2000)
        else:
            break

    # 4. Confirm editor is visible
    page.locator("#ctutortxtCode, .ace_editor").first.wait_for(state="visible", timeout=30000)
    print("Editor is successfully visible!")

    # Check problem details
    details = page.evaluate("""() => {
        let editorCode = window.ace ? ace.edit('ctutortxtCode').getValue() : '';
        let leftPanel = document.querySelector('#programgrid') || document.body;
        return {
            editorCode,
            leftText: leftPanel.innerText
        };
    }""")
    print("=== Current Editor Code ===")
    print(repr(details['editorCode']))
    print("=== Left Text ===")
    print(details['leftText'][:600])

    # Inject solution: city = "Chennai"
    print("Setting city = 'Chennai' in editor...")
    page.evaluate("""() => {
        let ed = ace.edit('ctutortxtCode');
        ed.setValue('city = "Chennai"', 1);
        let ta = document.getElementById('txtCode');
        if (ta) ta.value = 'city = "Chennai"';
    }""")
    page.wait_for_timeout(1000)

    # 5. Click RUN button
    print("Clicking Run button...")
    page.locator("button:has-text('Run')").first.click()
    
    print("Waiting 6 seconds for run execution...")
    page.wait_for_timeout(6000)
    page.screenshot(path="inspect_after_run.png", full_page=True)

    # Inspect the page after Run
    run_state = page.evaluate("""() => {
        let allElements = Array.from(document.querySelectorAll('*')).filter(el => {
            let t = (el.innerText || '').toLowerCase();
            return el.children.length === 0 && (
                t.includes('congrat') || 
                t.includes('passed') || 
                t.includes('test case') || 
                t.includes('success') ||
                t.includes('output') ||
                t.includes('error')
            );
        }).map(el => ({
            tag: el.tagName,
            id: el.id,
            className: el.className,
            text: el.innerText
        }));

        let dialogs = Array.from(document.querySelectorAll('.ui-dialog, .ui-growl, .ui-messages, .ui-widget-content')).filter(d => d.offsetParent !== null).map(d => ({
            id: d.id,
            className: d.className,
            text: d.innerText
        }));

        return { elements: allElements.slice(0, 20), dialogs };
    }""")
    print("Run State Elements:", json.dumps(run_state['elements'], indent=2))
    print("Run Dialogs:", json.dumps(run_state['dialogs'], indent=2))

    # 6. Click SAVE button
    print("Clicking Save button...")
    page.locator("button:has-text('Save')").first.click()
    print("Waiting 6 seconds for save execution...")
    page.wait_for_timeout(6000)
    page.screenshot(path="inspect_after_save.png", full_page=True)

    save_state = page.evaluate("""() => {
        let buttons = Array.from(document.querySelectorAll('button, a.ui-button, a, input[type="button"], input[type="submit"]')).filter(b => b.offsetParent !== null).map(b => ({
            id: b.id,
            text: (b.innerText || b.value || '').trim(),
            className: b.className,
            href: b.getAttribute('href'),
            onclick: b.getAttribute('onclick')
        }));

        let dialogs = Array.from(document.querySelectorAll('.ui-dialog, .ui-growl, .ui-messages')).filter(d => d.offsetParent !== null).map(d => ({
            id: d.id,
            className: d.className,
            text: d.innerText
        }));

        return { buttons, dialogs };
    }""")
    print("Save State Buttons:", json.dumps(save_state['buttons'], indent=2))
    print("Save State Dialogs:", json.dumps(save_state['dialogs'], indent=2))

    browser.close()
