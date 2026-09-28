import os, re, base64, io
from PIL import Image
from playwright.sync_api import sync_playwright
from config import (
    HEADLESS, DEFAULT_TIMEOUT, NAV_WAIT_UNTIL, SKILLRACK_URL,
    USERNAME, PASSWORD, STORAGE_STATE_FILE
)
from logger import log_info, log_error, log_warning

# OCR Template definitions (6x9 grid, 54 chars each) for Math Captcha solving
TEMPLATES = {
    '0': ('.####.' '.#..#.' '#....#' '#....#' '#....#' '#....#' '#....#' '.#..#.' '.####.'),
    '1': ('..##..' '...#..' '...#..' '...#..' '...#..' '...#..' '...#..' '...#..' '.####.'),
    '2': ('.####.' '#....#' '.....#' '....#.' '...#..' '..#...' '.#....' '######' '######'),
    '3': ('.####.' '#....#' '.....#' '...##.' '.....#' '.....#' '.....#' '#....#' '.####.'),
    '4': ('...##.' '..#.#.' '.#..#.' '#...#.' '######' '....#.' '....#.' '....#.' '....#.'),
    '5': ('######' '#.....' '#.....' '#####.' '.....#' '.....#' '.....#' '#....#' '.####.'),
    '6': ('.####.' '#.....' '#.....' '#####.' '#....#' '#....#' '#....#' '#....#' '.####.'),
    '7': ('######' '.....#' '....#.' '....#.' '...#..' '...#..' '..#...' '..#...' '.#....'),
    '8': ('.####.' '#....#' '#....#' '.####.' '.####.' '#....#' '#....#' '#....#' '.####.'),
    '9': ('.####.' '#....#' '#....#' '.####.' '.....#' '.....#' '.....#' '#....#' '.####.'),
    '+': ('......' '..##..' '..##..' '######' '######' '..##..' '..##..' '......' '......'),
    '-': ('......' '......' '......' '######' '######' '......' '......' '......' '......'),
    '=': ('......' '######' '######' '......' '######' '######' '......' '......' '......')
}

def solve_captcha(b64_str: str) -> str:
    """Decodes base64 captcha image and extracts math expression result using scale-invariant template OCR."""
    if ',' in b64_str:
        b64_str = b64_str.split(',', 1)[1]
    b64_str = b64_str.strip() + '=' * (-len(b64_str.strip()) % 4)

    raw_bytes = base64.b64decode(b64_str)
    im_raw = Image.open(io.BytesIO(raw_bytes))
    if im_raw.mode == 'RGBA':
        bg = Image.new('RGBA', im_raw.size, (0, 0, 0, 255))
        im = Image.alpha_composite(bg, im_raw).convert('L')
    else:
        im = im_raw.convert('L')

    pixels = im.load()
    w, h = im.size
    
    # Adaptively detect whether background is light or dark
    avg_luminance = sum(pixels[x, y] for x in range(w) for y in range(h)) / (w * h)
    is_light_bg = avg_luminance > 128
    is_text = (lambda val: val < 128) if is_light_bg else (lambda val: val > 128)
    print(f"[DEBUG CAPTCHA IMG]: size=({w}x{h}), avg_lum={avg_luminance:.1f}, light_bg={is_light_bg}", flush=True)

    # The captcha image contains user ID on top half (y: 0..h//2) and math prompt on bottom half (y: h//2..h)
    ymin = h // 2
    col_has_text = [any(is_text(pixels[x, y]) for y in range(ymin, h)) for x in range(w)]
    raw_segments = []
    in_seg = False
    start = 0
    for x in range(w):
        if col_has_text[x] and not in_seg:
            in_seg = True
            start = x
        elif not col_has_text[x] and in_seg:
            in_seg = False
            if x - start >= 2:  # Filter noise columns
                raw_segments.append((start, x - 1))
    if in_seg and (w - start >= 2):
        raw_segments.append((start, w - 1))

    # Merge closely adjacent raw segments (gap <= 2) that belong to the same digit or symbol
    merged_raw = []
    for s, e in raw_segments:
        if merged_raw and (s - merged_raw[-1][1] <= 2):
            merged_raw[-1] = (merged_raw[-1][0], e)
        else:
            merged_raw.append((s, e))

    segments = []
    for s, e in merged_raw:
        seg_w = e - s + 1
        c_vals = [sum(1 for y in range(ymin, h) if is_text(pixels[x, y])) for x in range(s, e + 1)]
        if seg_w >= 28:
            # 3 merged characters
            w3 = seg_w // 3
            t1 = min(range(max(2, w3 - 3), min(seg_w - 4, w3 + 4)), key=lambda idx: c_vals[idx])
            t2 = min(range(max(t1 + 3, 2 * w3 - 3), min(seg_w - 2, 2 * w3 + 4)), key=lambda idx: c_vals[idx])
            segments.append((s, s + t1))
            segments.append((s + t1 + 1, s + t2))
            segments.append((s + t2 + 1, e))
        elif seg_w >= 15:
            # 2 merged characters
            w2 = seg_w // 2
            r_start = max(3, w2 - 3)
            r_end = min(seg_w - 3, w2 + 4)
            t1 = min(range(r_start, max(r_start + 1, r_end)), key=lambda idx: c_vals[idx])
            segments.append((s, s + t1))
            segments.append((s + t1 + 1, e))
        else:
            segments.append((s, e))

    num_segs = len(segments)
    chars = []
    for idx, (s, e) in enumerate(segments):
        seg_w = e - s + 1
        if seg_w < 3 and idx < num_segs - 1:
            continue
        seg_rows = [y for y in range(ymin, h) if any(is_text(pixels[x, y]) for x in range(s, e + 1))]
        if not seg_rows:
            continue
        pix_count = sum(1 for x in range(s, e + 1) for y in range(ymin, h) if is_text(pixels[x, y]))
        if pix_count < 6 and idx < num_segs - 1:
            continue
        min_y, max_y = min(seg_rows), max(seg_rows)

        # Crop character segment and resize to 6x9 grid for scale-invariant matching
        cropped = im.crop((s, min_y, e + 1, max_y + 1)).resize((6, 9), Image.Resampling.NEAREST)
        cpixels = cropped.load()
        pat_lines = [''.join('#' if is_text(cpixels[x, y]) else '.' for x in range(6)) for y in range(9)]
        pat_str = ''.join(pat_lines)

        seg_w = e - s + 1
        seg_h = max_y - min_y + 1
        aspect_ratio = seg_h / float(max(1, seg_w))

        # Positional & template candidate matching
        if idx == num_segs - 1:
            chars.append('=')
            continue
        
        candidate_chars = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '+', '-']

        best_char = '?'
        best_score = -9999
        for ch in candidate_chars:
            templ = TEMPLATES[ch]
            score = sum(1 if p == t else -1 for p, t in zip(pat_str, templ))
            if score > best_score:
                best_score = score
                best_char = ch

        # Aspect-ratio refinement for operators vs digits
        if aspect_ratio < 0.55:
            best_char = '-'
        elif best_char in ['+', '-'] and aspect_ratio >= 0.7:
            best_char = '+'
        elif seg_w <= 4 and aspect_ratio >= 1.6 and best_char in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
            best_char = '1'

        chars.append(best_char)

    expr = ''.join(c for c in chars if c != '=')
    print(f"[DEBUG OCR] Extracted character string: '{expr}' from {len(segments)} segments", flush=True)
    m = re.search(r'(\d+)\s*([\+\-\*\/])\s*(\d+)', expr)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        ans = a + b if op == '+' else a - b if op == '-' else a * b
        return str(ans)
    return ""

class BrowserManager:
    def __init__(self, headless: bool = HEADLESS):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        log_info(f"[BROWSER] Launching Chromium browser (headless={self.headless})...")
        self.playwright = sync_playwright().start()
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        for attempt in range(3):
            try:
                channel_opt = {}
                if attempt == 1:
                    channel_opt = {"channel": "chrome"}
                elif attempt == 2:
                    channel_opt = {"channel": "msedge"}
                self.browser = self.playwright.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                    **channel_opt
                )
                break
            except Exception as launch_err:
                if attempt == 2:
                    raise
                log_warning(f"[BROWSER LAUNCH RETRY] Attempt {attempt+1} failed: {launch_err}. Retrying in 1.5s...")
                import time
                time.sleep(1.5)

        if os.path.exists(STORAGE_STATE_FILE):
            log_info(f"[BROWSER] Restoring persistent session state from '{STORAGE_STATE_FILE}'")
            self.context = self.browser.new_context(
                storage_state=STORAGE_STATE_FILE,
                viewport={'width': 1280, 'height': 800},
                user_agent=user_agent
            )
        else:
            log_info("[BROWSER] Creating fresh browser context.")
            self.context = self.browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent=user_agent
            )

        self.page = self.context.new_page()
        self.page.set_default_timeout(DEFAULT_TIMEOUT)
        print(f"[DEBUG] Browser initialized | URL: {self.page.url} | Closed: {self.page.is_closed()}", flush=True)
        return self.page

    def login_and_navigate(self):
        log_info(f"[LOGIN] Navigating to {SKILLRACK_URL}...")
        try:
            self.page.goto(SKILLRACK_URL, wait_until=NAV_WAIT_UNTIL, timeout=DEFAULT_TIMEOUT)
        except Exception as e:
            log_warning(f"[LOGIN] Primary goto warning: {e}. Retrying with commit...")
            self.page.goto(SKILLRACK_URL, wait_until="commit", timeout=DEFAULT_TIMEOUT)

        print(f"[DEBUG] URL after goto: {self.page.url}", flush=True)
        print(f"[DEBUG] TITLE: '{self.page.title()}'", flush=True)

        login_user_input = self.page.locator("input[name='j_username']")
        login_link = self.page.locator("a:has-text('Login')")

        if login_user_input.is_visible(timeout=3000) or login_link.is_visible(timeout=3000):
            if not login_user_input.is_visible(timeout=1000) and login_link.is_visible(timeout=2000):
                print(f"[DEBUG] Clicking Login link: text='{login_link.inner_text().strip()}', href='{login_link.get_attribute('href')}'", flush=True)
                login_link.click()
                login_user_input.wait_for(state="visible", timeout=10000)

            if login_user_input.is_visible(timeout=5000):
                log_info("[LOGIN] Submitting user credentials...")
                login_user_input.fill(USERNAME)
                self.page.locator("input[name='j_password']").fill(PASSWORD)
                login_btn = self.page.locator("input[type='submit'], input[value='Login'], button:has-text('Login')").first
                print(f"[DEBUG] Clicking submit button: value='{login_btn.get_attribute('value')}'", flush=True)
                login_btn.click()
                self.page.wait_for_load_state("domcontentloaded")
                self.page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml'], a[href*='candidate']").first.wait_for(state="visible", timeout=30000)

                try:
                    self.context.storage_state(path=STORAGE_STATE_FILE)
                    log_info(f"[LOGIN] Session state persisted to '{STORAGE_STATE_FILE}'.")
                except Exception as s_err:
                    log_warning(f"[LOGIN] Could not save storage state: {s_err}")
        else:
            log_info("[LOGIN] Existing active authentication session detected!")

        print(f"[DEBUG] URL after authentication: {self.page.url}", flush=True)
        print(f"[DEBUG] TITLE: '{self.page.title()}'", flush=True)

        # 1. Programming Track
        prog = self.page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml']").first
        print(f"[DEBUG] Element being clicked: text='{prog.inner_text().strip()}', href='{prog.get_attribute('href')}'", flush=True)
        prog.click()
        self.page.wait_for_timeout(1000)
        print(f"[DEBUG] Current URL: {self.page.url} | Title: '{self.page.title()}'", flush=True)

        # 2. Level 1
        lvl1 = self.page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first
        print(f"[DEBUG] Element being clicked: text='{lvl1.inner_text().strip()}', href='{lvl1.get_attribute('href')}'", flush=True)
        lvl1.click()
        self.page.wait_for_timeout(1000)
        print(f"[DEBUG] Current URL: {self.page.url} | Title: '{self.page.title()}'", flush=True)

        # 3. Code Tutor
        tutor = self.page.locator("a[href*='codeprogramgroup.xhtml?gt=CODETUTOR']").first
        print(f"[DEBUG] Element being clicked: text='{tutor.inner_text().strip()}', href='{tutor.get_attribute('href')}'", flush=True)
        tutor.click()
        self.page.wait_for_timeout(1000)
        print(f"[DEBUG] Current URL: {self.page.url} | Title: '{self.page.title()}'", flush=True)

        # 4. Python Programming Show button
        py_row = self.page.locator("tr").filter(has_text="Python Programming")
        py_show = py_row.locator("button:has-text('Show'), input[value='Show']").first
        print(f"[DEBUG] Element being clicked: tag='{py_show.evaluate('e => e.tagName')}', text='{py_show.inner_text().strip()}'", flush=True)
        py_show.click()
        self.page.wait_for_timeout(1000)
        print(f"[DEBUG] Current URL: {self.page.url} | Title: '{self.page.title()}'", flush=True)

        # 5. Hands-On Course Show button
        hands_on = self.page.locator("button:has-text('Show'), input[value='Show']").first
        print(f"[DEBUG] Element being clicked: tag='{hands_on.evaluate('e => e.tagName')}', text='{hands_on.inner_text().strip()}'", flush=True)
        hands_on.click()
        self.page.wait_for_timeout(1500)
        print(f"[DEBUG] Current URL: {self.page.url} | Title: '{self.page.title()}'", flush=True)

        # 6. Active Chapter View button (EXCLUDING LeaderBoard)
        view_btn = self.page.locator("button, a, input").filter(has_text=re.compile(r"^\s*(View|Resume)\s*$", re.I)).first
        print(f"[DEBUG] Element being clicked: tag='{view_btn.evaluate('e => e.tagName')}', text='{view_btn.inner_text().strip()}'", flush=True)
        view_btn.click()
        self.page.wait_for_timeout(2000)
        print(f"[DEBUG] Current URL after entering tutorial page: {self.page.url}", flush=True)
        print(f"[DEBUG] Page title: '{self.page.title()}'", flush=True)

    def close(self):
        log_info("[BROWSER] Closing browser context...")
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
