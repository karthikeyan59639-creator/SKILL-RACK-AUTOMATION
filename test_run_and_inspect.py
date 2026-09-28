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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(120000)

    print("Step 1: Navigating to SkillRack login page...")
    page.goto("https://skillrack.com/faces/ui/profile.xhtml", wait_until="domcontentloaded", timeout=90000)
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

    # Check if captcha is present
    if page.locator("#codeeditorpanel img").is_visible():
        print("Captcha visible, solving...")
        img_el = page.locator("#codeeditorpanel img").first
        src = img_el.get_attribute("src")
        ans = solve_captcha(src)
        print("Captcha answer:", ans)
        page.locator("#capval").fill(ans)
        page.locator("#proceedbtn").click()
        page.wait_for_timeout(4000)

    print("Checking editor visibility...")
    page.locator("#ctutortxtCode, .ace_editor").first.wait_for(state="visible", timeout=30000)
    print("Editor is visible!")

    # Inspect the DOM around the editor and left panel
    info = page.evaluate("""() => {
        let leftTitle = document.querySelector('.ui-ribbon-group, .card-title, h4, h5, .ui-panel-title')?.innerText || '';
        let problemText = document.body.innerText;
        
        // Find ace editor content
        let editorContent = window.ace ? ace.edit('ctutortxtCode')?.getValue() : '';
        
        // Find any prefix/postfix code
        let preTags = Array.from(document.querySelectorAll('pre, code')).map(el => ({
            tag: el.tagName,
            id: el.id,
            className: el.className,
            text: el.innerText
        }));
        
        // Find all buttons on page
        let buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"], a.ui-button')).map(b => ({
            id: b.id,
            text: b.innerText || b.value,
            classes: b.className,
            onclick: b.getAttribute('onclick')
        }));

        // Find current URL
        let url = window.location.href;

        return {
            editorContent,
            preTags,
            buttons,
            url
        };
    }""")

    print("Current URL:", info['url'])
    print("Current Ace Editor Content:\n---START---\n" + info['editorContent'] + "\n---END---")
    print("Found Pre/Code tags:", json.dumps(info['preTags'], indent=2))
    print("Found Buttons:", json.dumps(info['buttons'], indent=2))

    # Now let's extract the problem description from the left column
    problem_details = page.evaluate("""() => {
        // Let's get the text of elements in the left panel
        let leftCols = Array.from(document.querySelectorAll('.ui-g-12, .ui-md-6, .ui-lg-6, [class*="col-"]'));
        let problemInfo = {};
        // Look for ProgramID
        let pidMatch = document.body.innerText.match(/ProgramID-\\s*(\\d+)/);
        problemInfo.programId = pidMatch ? pidMatch[1] : null;

        // Look for Exercise Problem title and text
        let allDivs = Array.from(document.querySelectorAll('div'));
        let exDiv = allDivs.find(d => d.innerText && d.innerText.includes('Exercise Problem'));
        if (exDiv) {
            problemInfo.exerciseText = exDiv.innerText;
        }
        return problemInfo;
    }""")
    print("Problem details:", json.dumps(problem_details, indent=2))

    # Take screenshot before typing
    page.screenshot(path="test_before_run.png")

    # Now let's type city = "Chennai" into Ace Editor
    print("Injecting city = 'Chennai' into Ace editor...")
    page.evaluate("""() => {
        let ed = ace.edit('ctutortxtCode');
        ed.setValue('city = "Chennai"', 1);
        let ta = document.getElementById('txtCode');
        if (ta) ta.value = 'city = "Chennai"';
    }""")
    page.wait_for_timeout(1000)

    # Click Run button
    print("Clicking Run button...")
    run_btn = page.locator("button:has-text('Run')").first
    run_btn.click()
    
    # Wait and inspect after clicking Run
    print("Waiting 5 seconds after Run...")
    page.wait_for_timeout(5000)

    page.screenshot(path="test_after_run.png")
    
    # Inspect what changed after Run
    after_run_info = page.evaluate("""() => {
        // Look for test cases, output, logs, dialogs
        let dialogs = Array.from(document.querySelectorAll('.ui-dialog, .ui-growl-message, [class*="alert"], [class*="result"]')).map(d => ({
            className: d.className,
            text: d.innerText,
            visible: window.getComputedStyle(d).display !== 'none'
        }));
        
        let allButtons = Array.from(document.querySelectorAll('button, a.ui-button')).map(b => ({
            id: b.id,
            text: b.innerText,
            classes: b.className,
            visible: window.getComputedStyle(b).display !== 'none'
        }));

        return { dialogs, allButtons, fullTextSnippet: document.body.innerText.slice(0, 2000) };
    }""")

    print("After Run Dialogs:", json.dumps(after_run_info['dialogs'], indent=2))
    print("After Run Buttons:", json.dumps(after_run_info['allButtons'], indent=2))

    browser.close()
