import os
import sys
import unittest
from playwright.sync_api import sync_playwright

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from editor import detect_editor, get_code, set_code, normalize_code
from problem_scraper import scrape_problem
from runner import run_code_and_get_result
from orchestrator import wait_for_stale_state_change, advance_to_next


MOCK_HTML_PAGE_1 = """<!DOCTYPE html>
<html>
<head>
    <title>SkillRack Code Tutor - Program 2774</title>
</head>
<body>
    <div id="programgrid" class="ui-g-12 ui-md-6">
        <div>Python3-H002 Strings</div>
        <div>String - Lower</div>
        <div>
            Strings can be converted to lower case using lower() function.
            <pre>s = input()
print(s.lower())</pre>
        </div>
        <span class="ui-badge">ProgramID- 2774</span> SKILLRACK
        <h3>Convert to lower case</h3>
        <p>Complete the program so that it prints the input string value in lower case.</p>
        <p>Sample Input:
HELLO WORLD
Expected Output:
hello world</p>
        <div>Max Execution Time Limit: 5000 millisecs</div>
    </div>

    <div id="codeeditorpanel" class="ui-g-12 ui-md-6">
        <textarea id="txtCode" class="code_editor">print(inputstring.lower())</textarea>
        <button id="btnSave" class="ui-button">Save</button>
        <button id="btnRun" class="ui-button" onclick="document.getElementById('result').innerText = 'Congratulations! Your Code has passed'; document.getElementById('proceedNextBtn').style.display='inline';">Run</button>
        <button id="proceedNextBtn" style="display:none;" onclick="document.open(); document.write(window.PAGE_2_CONTENT); document.close();">Proceed Next</button>
        <div id="result"></div>
    </div>
</body>
</html>"""


MOCK_HTML_PAGE_2 = """<!DOCTYPE html>
<html>
<head>
    <title>SkillRack Code Tutor - Program 2775</title>
</head>
<body>
    <div id="programgrid" class="ui-g-12 ui-md-6">
        <div>Python3-H002 Strings</div>
        <div>String - Reverse</div>
        <div>
            Strings can be reversed using slicing.
            <pre>s = input()
print(s[::-1])</pre>
        </div>
        <span class="ui-badge">ProgramID- 2775</span> SKILLRACK
        <h3>Concatenate two strings and reverse</h3>
        <p>Complete the program so that it accepts two string values, concatenates them and then prints the reverse of the concatenated value.</p>
        <p>Sample Input:
hello
world
Expected Output:
dlrowolleh</p>
        <div>Max Execution Time Limit: 5000 millisecs</div>
    </div>

    <div id="codeeditorpanel" class="ui-g-12 ui-md-6">
        <textarea id="txtCode" class="code_editor">print(s[::-1])</textarea>
        <button id="btnSave" class="ui-button">Save</button>
        <button id="btnRun" class="ui-button">Run</button>
        <div id="result"></div>
    </div>
</body>
</html>"""


class TestPlaywrightPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def test_editor_and_scraper_flow(self):
        """Tests scraper, editor get/set, and runner on mock live page."""
        self.page.set_content(MOCK_HTML_PAGE_1)

        # 1. Scrape problem
        prob = scrape_problem(self.page)
        self.assertEqual(prob["program_id"], "2774")
        self.assertEqual(prob["title"], "Convert to lower case")
        self.assertIn("Complete the program so that it prints the input string value in lower case.", prob["statement"])
        self.assertIn("REFERENCE ONLY", prob["example_box"])

        # 2. Detect editor
        ed_type = detect_editor(self.page)
        self.assertEqual(ed_type, "textarea")

        # 3. Read initial stub BEFORE clearing
        initial_stub = get_code(self.page)
        self.assertEqual(initial_stub.strip(), "print(inputstring.lower())")

        # 4. Set new code
        new_code = "inputstring = input()\nprint(inputstring.lower())"
        success = set_code(self.page, new_code)
        self.assertTrue(success)

        # 5. Read back
        readback = get_code(self.page)
        self.assertEqual(normalize_code(readback), normalize_code(new_code))

        # 6. Run code and check result
        result = run_code_and_get_result(self.page, timeout_sec=5)
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "PASSED")

    def test_stale_state_guard_and_navigation(self):
        """Tests stale-state guard and page transition."""
        self.page.set_content(MOCK_HTML_PAGE_1)
        self.page.evaluate(f"window.PAGE_2_CONTENT = {repr(MOCK_HTML_PAGE_2)};")

        prob1 = scrape_problem(self.page)
        self.assertEqual(prob1["program_id"], "2774")

        # Click Run to reveal Proceed Next
        self.page.locator("#btnRun").click()
        self.page.wait_for_timeout(300)

        # Click Proceed Next to transition to Page 2
        proceed_btn = self.page.locator("#proceedNextBtn")
        self.assertTrue(proceed_btn.is_visible())
        proceed_btn.click()

        # Wait for ProgramID to change from 2774 to 2775
        new_pid = wait_for_stale_state_change(self.page, "2774", timeout_sec=5)
        self.assertEqual(new_pid, "2775")
        self.assertNotEqual(new_pid, "2774")

        # Scrape page 2
        prob2 = scrape_problem(self.page)
        self.assertEqual(prob2["program_id"], "2775")
        self.assertEqual(prob2["title"], "Concatenate two strings and reverse")
        stub2 = get_code(self.page)
        self.assertEqual(stub2.strip(), "print(s[::-1])")


if __name__ == "__main__":
    unittest.main()
