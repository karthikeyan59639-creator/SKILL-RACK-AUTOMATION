import os
import base64, io, re
from PIL import Image
from playwright.sync_api import sync_playwright
from skill_automation.config import (
    HEADLESS, DEFAULT_TIMEOUT, NAV_WAIT_UNTIL, SKILLRACK_URL,
    USERNAME, PASSWORD, STORAGE_STATE_FILE
)
from skill_automation.logger import log_info, log_error, log_warning

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
    '+': ('...#...' '...#...' '...#...' '#######' '...#...' '...#...'),
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


class BrowserManager:
    def __init__(self, headless: bool = HEADLESS):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """Launches Playwright Chromium browser and initializes context."""
        log_info(f"[BROWSER] Starting Chromium (headless={self.headless})...")
        self.playwright = sync_playwright().start()
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )

        if os.path.exists(STORAGE_STATE_FILE):
            log_info(f"[BROWSER] Restoring session state from '{STORAGE_STATE_FILE}'")
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
        log_info(f"[BROWSER] Browser initialized successfully. Page closed: {self.page.is_closed()}")
        return self.page

    def login_and_navigate(self):
        """Authenticates user and navigates directly to Python Code Tutor."""
        log_info(f"[LOGIN] Navigating to {SKILLRACK_URL}...")
        try:
            self.page.goto(SKILLRACK_URL, wait_until=NAV_WAIT_UNTIL, timeout=DEFAULT_TIMEOUT)
        except Exception as e:
            log_warning(f"[LOGIN] Primary goto warning: {e}. Retrying with wait_until='commit'...")
            self.page.goto(SKILLRACK_URL, wait_until="commit", timeout=DEFAULT_TIMEOUT)

        login_user_input = self.page.locator("input[name='j_username']")
        login_link = self.page.locator("a:has-text('Login')")

        if login_user_input.is_visible(timeout=3000) or login_link.is_visible(timeout=3000):
            if not login_user_input.is_visible(timeout=1000) and login_link.is_visible(timeout=2000):
                login_link.click()
                login_user_input.wait_for(state="visible", timeout=10000)

            if login_user_input.is_visible(timeout=5000):
                log_info("[LOGIN] Submitting login credentials...")
                login_user_input.fill(USERNAME)
                self.page.locator("input[name='j_password']").fill(PASSWORD)
                login_btn = self.page.locator("input[type='submit'], input[value='Login'], button:has-text('Login')").first
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

        log_info("[NAVIGATION] Entering Programming Track...")
        self.page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml']").first.click()

        log_info("[NAVIGATION] Entering Level 1...")
        lvl1 = self.page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first
        lvl1.wait_for(state="visible", timeout=15000)
        lvl1.click()

        log_info("[NAVIGATION] Entering Code Tutor...")
        tutor = self.page.locator("a[href*='gt=CODETUTOR']").first
        tutor.wait_for(state="visible", timeout=15000)
        tutor.click()

        log_info("[NAVIGATION] Selecting Python Programming...")
        py_btn = self.page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
        py_btn.wait_for(state="visible", timeout=15000)
        py_btn.click()

        log_info("[NAVIGATION] Opening Hands-On Course Overview...")
        show_btn = self.page.locator("button:has-text('Show')").first
        show_btn.wait_for(state="visible", timeout=15000)
        show_btn.click()

    def handle_captcha_if_present(self) -> bool:
        """Solves math OCR captcha if visible."""
        try:
            img_el = self.page.locator("#codeeditorpanel img").first
            if img_el.is_visible(timeout=4000):
                log_info("[CAPTCHA] Math OCR challenge detected. Solving...")
                src = img_el.get_attribute("src")
                ans = solve_captcha(src)
                log_info(f"[CAPTCHA] Solved result: {ans}. Submitting...")
                self.page.locator("#capval").fill(ans)
                self.page.locator("#proceedbtn").click()
                self.page.wait_for_timeout(2000)
                return True
        except Exception as e:
            log_warning(f"[CAPTCHA] Captcha check info: {e}")
        return False

    def handle_captcha_and_wait_for_editor(self):
        """Waits for captcha or editor to be visible, solves captcha if present, and waits for editor."""
        log_info("[READY] Waiting for captcha prompt or code editor...")
        self.page.locator("#codeeditorpanel img, #ctutortxtCode").first.wait_for(state="visible", timeout=45000)
        
        if self.page.locator("#codeeditorpanel img").first.is_visible():
            self.handle_captcha_if_present()

        self.page.locator("#ctutortxtCode").wait_for(state="visible", timeout=35000)
        log_info("[READY] Code editor successfully revealed.")

    def close(self):
        """Safely closes context and browser."""
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
