import os
import base64
import io
import re
import time
from datetime import datetime
from PIL import Image, ImageOps
import pytesseract
from playwright.sync_api import sync_playwright, Error as PlaywrightError
try:
    from playwright._impl._errors import TargetClosedError
except ImportError:
    TargetClosedError = PlaywrightError

from config import (
    HEADLESS, DEFAULT_TIMEOUT, NAV_WAIT_UNTIL, SKILLRACK_URL,
    USERNAME, PASSWORD, STORAGE_STATE_FILE, DEBUG_DIR
)
from logger import log_info, log_error, log_warning

# Configure Tesseract Windows executable path if present
TESSERACT_CANDIDATE_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]
for t_path in TESSERACT_CANDIDATE_PATHS:
    if os.path.exists(t_path):
        pytesseract.pytesseract.tesseract_cmd = t_path
        break

# Template definitions for fallback math captcha OCR
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


def compute_math_expression(expr: str) -> str:
    """Parses standard math expression (e.g. 29+5=) and returns result."""
    if not expr:
        return ""
    m = re.search(r'(\d+)\s*([\+\-\*\/xX])\s*(\d+)', expr)
    if m:
        a = int(m.group(1))
        op = m.group(2)
        b = int(m.group(3))
        if op == '+':
            return str(a + b)
        elif op == '-':
            return str(a - b)
        elif op in ('*', 'x', 'X'):
            return str(a * b)
        elif op == '/':
            return str(a // b) if b != 0 else "0"
    return ""


def fallback_template_ocr(im: Image.Image) -> str:
    """Fallback template matcher for when Tesseract produces unparsed text."""
    try:
        w, h = im.size
        pixels = im.load()
        # Look in bottom half where math challenge glyphs are located
        bottom_rows = [y for y in range(h // 2, h) if any(pixels[x, y] > 128 for x in range(w))]
        if not bottom_rows:
            bottom_rows = [y for y in range(h) if any(pixels[x, y] > 128 for x in range(w))]
        if not bottom_rows:
            return ""

        min_y, max_y = min(bottom_rows), max(bottom_rows)
        col_has_white = [any(pixels[x, y] > 128 for y in range(min_y, max_y + 1)) for x in range(w)]

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
            seg_rows = [y for y in range(min_y, max_y + 1) if any(pixels[x, y] > 128 for x in range(s, e + 1))]
            if not seg_rows:
                continue
            sy, ey = min(seg_rows), max(seg_rows)
            pat_lines = [''.join('#' if pixels[x, y] > 128 else '.' for x in range(s, e + 1)) for y in range(sy, ey + 1)]
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

        raw_expr = ''.join(chars)
        return raw_expr
    except Exception as e:
        log_warning(f"[CAPTCHA OCR] Template matching fallback notice: {e}")
        return ""


def solve_captcha_image(raw_bytes: bytes) -> tuple[str, str]:
    """
    Auto-crops glyph bounding box, auto-detects polarity, upscales 4x,
    and runs pytesseract with --psm 7 and whitelist 0123456789+-*/x= .
    Returns (raw_ocr_text, computed_answer).
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    debug_path = os.path.join(DEBUG_DIR, f"captcha_{ts}.png")
    try:
        with open(debug_path, "wb") as f:
            f.write(raw_bytes)
    except Exception:
        pass

    try:
        im = Image.open(io.BytesIO(raw_bytes)).convert('L')
        w, h = im.size
        pixels = im.load()

        # 1. Native pixel-perfect template matching on bitmap
        tmpl_text = fallback_template_ocr(im)
        tmpl_ans = compute_math_expression(tmpl_text)

        # 2. Auto-crop to glyph bounding box
        corners = [pixels[0, 0], pixels[w - 1, 0], pixels[0, h - 1], pixels[w - 1, h - 1]]
        bg_is_dark = (sum(corners) / 4) < 128

        bottom_rows = [y for y in range(h // 2, h) if any((pixels[x, y] > 128 if bg_is_dark else pixels[x, y] < 128) for x in range(w))]
        bottom_cols = [x for x in range(w) if any((pixels[x, y] > 128 if bg_is_dark else pixels[x, y] < 128) for y in range(h // 2, h))]

        if bottom_rows and bottom_cols:
            crop_box = (
                max(0, min(bottom_cols) - 4),
                max(0, min(bottom_rows) - 4),
                min(w, max(bottom_cols) + 5),
                min(h, max(bottom_rows) + 5)
            )
        else:
            crop_box = (0, h // 2, w, h)

        cropped = im.crop(crop_box)
        if bg_is_dark:
            cropped = ImageOps.invert(cropped)

        # 3. Upscale 4x with Lanczos
        upscaled = cropped.resize((cropped.width * 4, cropped.height * 4), Image.Resampling.LANCZOS)

        # 4. Run pytesseract with --psm 7 and whitelist
        raw_ocr = pytesseract.image_to_string(
            upscaled,
            config='--psm 7 -c tessedit_char_whitelist=0123456789+-*/x='
        ).strip()
        tess_ans = compute_math_expression(raw_ocr)

        # Prioritize pixel-perfect template match when it yields a valid expression
        if tmpl_ans:
            raw_ocr = tmpl_text
            ans = tmpl_ans
        else:
            ans = tess_ans

        log_info(f"[CAPTCHA OCR] Image saved: '{debug_path}' | Raw text: '{raw_ocr}' | Answer: '{ans}'")
        return raw_ocr, ans
    except Exception as e:
        log_error(f"[CAPTCHA ERROR] OCR extraction failed: {e}")
        return "", ""


def solve_captcha(b64_str: str) -> str:
    if ',' in b64_str:
        b64_str = b64_str.split(',', 1)[1]
    b64_str = b64_str.strip() + '=' * (-len(b64_str.strip()) % 4)
    raw_bytes = base64.b64decode(b64_str)
    _, ans = solve_captcha_image(raw_bytes)
    return ans


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
            try:
                self.context = self.browser.new_context(
                    storage_state=STORAGE_STATE_FILE,
                    viewport={'width': 1366, 'height': 900},
                    user_agent=user_agent
                )
            except Exception as e:
                log_warning(f"[BROWSER] Failed to restore storage state ({e}), creating fresh context.")
                self.context = self.browser.new_context(
                    viewport={'width': 1366, 'height': 900},
                    user_agent=user_agent
                )
        else:
            log_info("[BROWSER] Creating fresh browser context.")
            self.context = self.browser.new_context(
                viewport={'width': 1366, 'height': 900},
                user_agent=user_agent
            )

        self.page = self.context.new_page()
        self.page.set_default_timeout(DEFAULT_TIMEOUT)
        log_info("[BROWSER] Browser initialized successfully.")
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

        # Check if already on tutor program page with visible editor
        if "tutorprogram.xhtml" in self.page.url and self.page.locator(".CodeMirror:visible, .ace_editor:visible").is_visible():
            log_info("[NAVIGATION] Already on Code Tutor exercise page.")
            return

        log_info("[NAVIGATION] Entering Programming Track...")
        prog_link = self.page.locator("a:has-text('Programming'), a[href*='trackshome.xhtml']").first
        if prog_link.is_visible(timeout=5000):
            prog_link.click()
            self.page.wait_for_load_state("domcontentloaded")

        log_info("[NAVIGATION] Entering Level 1...")
        lvl1 = self.page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first
        if lvl1.is_visible(timeout=15000):
            lvl1.click()
            self.page.wait_for_load_state("domcontentloaded")

        log_info("[NAVIGATION] Entering Code Tutor...")
        tutor = self.page.locator("a[href*='gt=CODETUTOR']").first
        if tutor.is_visible(timeout=15000):
            tutor.click()
            self.page.wait_for_load_state("domcontentloaded")

        log_info("[NAVIGATION] Selecting Python Programming...")
        py_btn = self.page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
        if py_btn.is_visible(timeout=15000):
            py_btn.click()
            self.page.wait_for_load_state("domcontentloaded")

        log_info("[NAVIGATION] Opening Hands-On Course Overview...")
        show_btn = self.page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
        if not show_btn.is_visible(timeout=3000):
            show_btn = self.page.locator("button:has-text('Show')").first
        if show_btn.is_visible(timeout=15000):
            show_btn.click()
            self.page.wait_for_load_state("domcontentloaded")

    def read_captcha_from_dom(self) -> str:
        """
        FIRST checks whether the captcha math expression exists as text in the DOM
        (element text, placeholder, or attribute) and parses it.
        """
        try:
            dom_text = self.page.evaluate("""() => {
                let area = document.querySelector('#codeeditorpanel') || document.body;
                let capInput = document.querySelector('#capval, input[name="capval"]');
                let texts = [];

                if (capInput) {
                    if (capInput.placeholder) texts.push(capInput.placeholder);
                    if (capInput.getAttribute('title')) texts.push(capInput.getAttribute('title'));
                    let prev = capInput.previousElementSibling;
                    if (prev && prev.innerText) texts.push(prev.innerText);
                    let parent = capInput.parentElement;
                    if (parent && parent.innerText) texts.push(parent.innerText);
                }

                let imgs = Array.from(document.querySelectorAll('#codeeditorpanel img, img[src*="data:image"]'));
                for (let img of imgs) {
                    if (img.alt) texts.push(img.alt);
                    if (img.title) texts.push(img.title);
                }

                return texts.join(' ');
            }""")
            if dom_text:
                m = re.search(r'(\d+)\s*([\+\-\*\/xX])\s*(\d+)', dom_text)
                if m:
                    ans = compute_math_expression(m.group(0))
                    if ans:
                        log_info(f"[CAPTCHA DOM] Found expression '{m.group(0)}' in DOM text! Computed answer: '{ans}'")
                        return ans
        except Exception as e:
            log_warning(f"[CAPTCHA DOM] DOM inspection notice: {e}")
        return ""

    def handle_captcha_if_present(self, max_retries: int = 5) -> bool:
        """
        Solves math captcha challenge with outcome verification and retry up to 5 times.
        Never reuses the same wrong answer. Saves images to ./debug/.
        """
        cap_input = self.page.locator("#capval, input[name='capval']").first
        if not cap_input.is_visible(timeout=2000):
            return False

        log_info("[CAPTCHA] Challenge detected. Solving with retry loop...")
        tried_answers = set()

        for attempt in range(1, max_retries + 1):
            log_info(f"[CAPTCHA] Attempt {attempt}/{max_retries}...")

            # 1. FIRST check DOM text
            ans = self.read_captcha_from_dom()

            # 2. If no DOM text, use image OCR path
            if not ans or ans in tried_answers:
                img_el = self.page.locator("#codeeditorpanel img, img[src*='data:image'], #capval ~ img").first
                raw_bytes = None
                if img_el.is_visible(timeout=2000):
                    src = img_el.get_attribute("src") or ""
                    if src.startswith("data:image"):
                        try:
                            if ',' in src:
                                src = src.split(',', 1)[1]
                            src_clean = src.strip()
                            src_clean += '=' * (-len(src_clean) % 4)
                            raw_bytes = base64.b64decode(src_clean)
                        except Exception as b64_err:
                            log_warning(f"[CAPTCHA] Base64 decode warning: {b64_err}. Falling back to element screenshot.")
                            raw_bytes = None
                    if not raw_bytes:
                        try:
                            raw_bytes = img_el.screenshot()
                        except Exception as ss_err:
                            log_warning(f"[CAPTCHA] Element screenshot warning: {ss_err}")
                            raw_bytes = None


                if raw_bytes:
                    raw_ocr, ocr_ans = solve_captcha_image(raw_bytes)
                    if ocr_ans and ocr_ans not in tried_answers:
                        ans = ocr_ans

            if not ans or ans in tried_answers:
                # Generate fallback guess avoiding already tried answers
                for candidate in range(10, 100):
                    if str(candidate) not in tried_answers:
                        ans = str(candidate)
                        break

            tried_answers.add(ans)
            log_info(f"[CAPTCHA] Submitting answer '{ans}' (tried: {tried_answers})...")

            cap_input.fill(ans)
            self.page.wait_for_timeout(300)

            proceed_btn = self.page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program'), button:has-text('Proceed'), [value*='Proceed']").first
            if proceed_btn.is_visible(timeout=2000):
                proceed_btn.click()
                self.page.wait_for_timeout(2500)

            # Outcome verification:
            # Check if editor widget is now visible
            editor_visible = self.page.locator(".CodeMirror:visible, .ace_editor:visible, #ctutortxtCode:visible").first.is_visible(timeout=3000)
            if editor_visible:
                log_info("[CAPTCHA SUCCESS] Editor widget became visible. Captcha successfully solved!")
                return True

            # Check if Incorrect Captcha error banner appeared
            has_error = self.page.evaluate("""() => {
                let t = document.body ? document.body.innerText : '';
                return t.includes('Incorrect Captcha Value') ||
                       t.includes('Invalid Captcha') ||
                       !!document.querySelector('.ui-messages-error, .ui-message-error');
            }""")

            if has_error or cap_input.is_visible():
                log_warning(f"[CAPTCHA FAIL] Attempt {attempt} got Incorrect Captcha. Refreshing captcha...")
                # Refresh captcha image if refresh icon exists or reload
                refresh_btn = self.page.locator("a[id*='refresh'], button[id*='refresh'], .pi-refresh, img[src*='refresh']").first
                if refresh_btn.is_visible(timeout=1500):
                    refresh_btn.click()
                    self.page.wait_for_timeout(1500)
                else:
                    try:
                        self.page.reload(wait_until="domcontentloaded", timeout=15000)
                        self.page.wait_for_timeout(2000)
                        cap_input = self.page.locator("#capval, input[name='capval']").first
                    except Exception:
                        pass

        log_error(f"[CAPTCHA ERROR] Failed to solve captcha after {max_retries} attempts.")
        return False

    def open_next_unfinished_chapter(self, target_chapters: list[str] = None) -> str:
        """
        Navigates to codeprogramgroup.xhtml (course overview) and inspects chapters.
        Finds the first chapter in target_chapters (default: H004 to H015) that is NOT 100%.
        Clicks its View button, solves any tutorial/captcha, and waits for editor.
        Returns the opened chapter code (e.g. 'H004') or '' if all are completed.
        """
        if not target_chapters:
            target_chapters = [
                "H001", "H002", "H003", "H004", "H005", "H006",
                "H007", "H008", "H009", "H010", "H011", "H012",
                "H013", "H014", "H015"
            ]

        # Ensure on codeprogramgroup.xhtml
        if "codeprogramgroup.xhtml" not in self.page.url:
            log_info("[NAVIGATION] Navigating to Hands-On Course Overview...")
            self.page.goto("https://skillrack.com/faces/candidate/trackshome.xhtml")
            self.page.wait_for_load_state("domcontentloaded")
            lvl1 = self.page.locator("a[href*='lev1.xhtml'], .card:has-text('Level 1') a:has-text('View')").first
            if lvl1.is_visible(timeout=5000):
                lvl1.click()
                self.page.wait_for_load_state("domcontentloaded")
            tutor = self.page.locator("a[href*='gt=CODETUTOR']").first
            if tutor.is_visible(timeout=5000):
                tutor.click()
                self.page.wait_for_load_state("domcontentloaded")
            py_btn = self.page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
            if py_btn.is_visible(timeout=5000):
                py_btn.click()
                self.page.wait_for_load_state("domcontentloaded")
            show_btn = self.page.locator("button:has-text('Show')").first
            if show_btn.is_visible(timeout=5000):
                show_btn.click()
                self.page.wait_for_load_state("domcontentloaded")
                self.page.wait_for_timeout(1500)

        for ch_code in target_chapters:
            ch_row = self.page.locator("[id*='cttbl']").filter(has_text=f"Python3-{ch_code}").first
            if ch_row.is_visible(timeout=1500):
                row_text = ch_row.inner_text()
                if "100%" in row_text:
                    log_info(f"[CHAPTER] Python3-{ch_code} is 100% complete. Advancing to next...")
                    continue

                btn = ch_row.locator("button:has-text('View'), input[value='View'], button, input[type='submit']").first
                if btn.is_visible(timeout=2000):
                    log_info(f"[CHAPTER] Opening unfinished chapter 'Python3-{ch_code}'...")
                    btn.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    self.page.wait_for_timeout(2000)
                    return ch_code

        # Next Courses Pipeline: STARTER -> 50 VERY-EASY -> 50 EASY -> 50 AVERAGE
        subsequent_tracks = [
            ("STARTER", "Python - STARTER"),
            ("VERY-EASY", "50 VERY-EASY CHALLENGES"),
            ("EASY", "50 EASY CHALLENGES"),
            ("AVERAGE", "50 AVERAGE CHALLENGES")
        ]
        for track_id, track_keyword in subsequent_tracks:
            card = self.page.locator("tr, div, .card, form").filter(has_text=track_keyword).first
            if card.is_visible(timeout=1500):
                card_text = card.inner_text()
                if "100%" in card_text:
                    log_info(f"[TRACK] '{track_keyword}' is 100% complete. Advancing to next track...")
                    continue
                show_btn = card.locator("button:has-text('Show'), input[value='Show']").first
                if show_btn.is_visible(timeout=1500):
                    show_btn.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    self.page.wait_for_timeout(1500)
                rows = self.page.locator("tr, [id*='cttbl']").filter(has_text="View")
                count = rows.count()
                for i in range(count):
                    r = rows.nth(i)
                    r_text = r.inner_text()
                    if "100%" not in r_text:
                        view_btn = r.locator("button:has-text('View'), input[value='View'], button").first
                        if view_btn.is_visible(timeout=1500):
                            log_info(f"[TRACK] Opening exercise in '{track_keyword}'...")
                            view_btn.click()
                            self.page.wait_for_load_state("domcontentloaded")
                            self.page.wait_for_timeout(2000)
                            return track_id

        log_info("[CHAPTER] All requested chapters and subsequent tracks appear to be 100% completed!")
        return ""

    def handle_captcha_and_wait_for_editor(self):
        """
        Navigates from chapter overview or tutorial page, solves captcha,
        and waits for the VISIBLE code editor widget.
        """
        log_info("[READY] Preparing code editor...")

        # 0. Check if chapter completion screen appeared!
        is_completed_banner = self.page.evaluate("""() => {
            let t = document.body ? document.body.innerText : '';
            return t.includes('successfully completed the programming course') ||
                   t.includes('successfully completed');
        }""")
        if is_completed_banner:
            log_info("[MILESTONE] >>> Chapter completed banner detected. Transitioning to next unfinished chapter... <<<")
            self.open_next_unfinished_chapter()

        # 1. If on chapter overview (codeprogramgroup.xhtml), open next unfinished chapter
        if "codeprogramgroup.xhtml" in self.page.url:
            self.open_next_unfinished_chapter()
        elif "tutorprogram.xhtml" not in self.page.url:
            log_info(f"[NAVIGATION] Scanning for chapter 'View' / 'Resume' button on '{self.page.url}'...")
            try:
                view_btn = self.page.locator("button, a, input").filter(has_text=re.compile(r"^\s*(View|Resume)\s*$", re.I)).first
                if not view_btn.is_visible(timeout=4000):
                    view_btn = self.page.locator("button:has-text('View'), a:has-text('View'), button:has-text('Resume')").first

                if view_btn.is_visible(timeout=10000):
                    btn_text = view_btn.inner_text().strip()
                    log_info(f"[NAVIGATION] Opening chapter via '{btn_text}' button...")
                    view_btn.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    self.page.wait_for_timeout(2000)
            except Exception as nav_e:
                log_warning(f"[NAVIGATION] Chapter open warning: {nav_e}")

        # 2. If 'Proceed to Solve the Program' button is present, handle captcha and click it
        proceed_btn = self.page.locator("#proceedbtn, button:has-text('Proceed to Solve the Program'), input[value*='Proceed to Solve']").first
        if proceed_btn.is_visible(timeout=4000):
            log_info("[NAVIGATION] Tutorial proceed button detected.")
            self.handle_captcha_if_present()
            if proceed_btn.is_visible(timeout=2000):
                log_info("[NAVIGATION] Clicking 'Proceed to Solve the Program' button...")
                proceed_btn.click()
                self.page.wait_for_timeout(2500)

        # 3. Handle captcha if visible above editor
        self.handle_captcha_if_present()

        # 4. Wait for VISIBLE editor widget (Never wait on hidden textarea)
        log_info("[READY] Waiting for visible code editor widget...")
        editor_widget = self.page.locator(".CodeMirror:visible, .ace_editor:visible, #ctutortxtCode:visible").first
        editor_widget.wait_for(state="visible", timeout=120000)
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
