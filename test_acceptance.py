import os
import sys
import json
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from solver import generate_solution
from local_check import run_local_check
from editor import normalize_code
from problem_scraper import parse_problem_text
from progress import ProgressManager


class TestSkillRackAutomationAcceptance(unittest.TestCase):

    def test_acceptance_program_2775(self):
        """
        Acceptance test 1:
        ProgramID 2775, stub `print(s[::-1])`, task 'accepts two string values, concatenates them and then prints the reverse of the concatenated value'
        must produce:
            s1 = input()
            s2 = input()
            s = s1 + s2
            print(s[::-1])
        """
        problem = {
            "program_id": "2775",
            "topic": "Python3-H002 Strings",
            "title": "Concatenate two strings and reverse",
            "statement": "Complete the program so that it accepts two string values, concatenates them and then prints the reverse of the concatenated value.",
            "sample_io": [
                {"input": "hello\nworld", "output": "dlrowolleh"}
            ],
            "constraints": "",
            "time_limit": "Max Execution Time Limit: 5000 millisecs"
        }
        stub = "print(s[::-1])"

        solution = generate_solution(problem, stub)
        valid_options = [
            "s1 = input()\ns2 = input()\ns = s1 + s2\nprint(s[::-1])",
            "s1 = input().strip()\ns2 = input().strip()\ns = s1 + s2\nprint(s[::-1])",
            "s1 = input()\ns2 = input()\ns = s1+s2\nprint(s[::-1])",
            "s = input() + input()\nprint(s[::-1])"
        ]
        norm_options = [normalize_code(opt) for opt in valid_options]
        self.assertIn(
            normalize_code(solution),
            norm_options,
            f"ProgramID 2775 did not produce the expected code.\nGot:\n{solution}\nExpected one of:\n{valid_options}"
        )

        # Test local check against sample input
        passed, msg = run_local_check(solution, problem["sample_io"])
        self.assertTrue(passed, f"Local check failed for ProgramID 2775: {msg}")

    def test_acceptance_program_2774(self):
        """
        Acceptance test 2:
        ProgramID 2774 ('Convert to lower case') must produce:
            inputstring = input()
            print(inputstring.lower())
        """
        problem = {
            "program_id": "2774",
            "topic": "Python3-H002 Strings",
            "title": "Convert to lower case",
            "statement": "Complete the program so that it prints the input string value in lower case.",
            "sample_io": [
                {"input": "HeLLo WoRLd", "output": "hello world"}
            ],
            "constraints": "",
            "time_limit": "Max Execution Time Limit: 5000 millisecs"
        }
        stub = "print(inputstring.lower())"

        solution = generate_solution(problem, stub)
        expected_code = "inputstring = input()\nprint(inputstring.lower())"

        self.assertEqual(
            normalize_code(solution),
            normalize_code(expected_code),
            f"ProgramID 2774 did not produce the expected code.\nGot:\n{solution}\nExpected:\n{expected_code}"
        )

        # Test local check against sample input
        passed, msg = run_local_check(solution, problem["sample_io"])
        self.assertTrue(passed, f"Local check failed for ProgramID 2774: {msg}")

    def test_scraper_separates_example_from_task(self):
        """
        Verifies that problem_scraper.py cleanly isolates the concept example box
        and labels it reference-only, extracting the real task statement separately.
        """
        raw_text = """Python3-H002 Strings
String - Length

The len() function can be used to find the length of the string as shown below.

name = input()
print(len(name))

ProgramID- 2772  SKILLRACK

Print String Length

Complete the program so that it prints the length of the input string value.

Max Execution Time Limit: 5000 millisecs
"""
        parsed = parse_problem_text(raw_text)
        self.assertEqual(parsed["program_id"], "2772")
        self.assertEqual(parsed["title"], "Print String Length")
        self.assertIn("Complete the program so that it prints the length", parsed["statement"])
        self.assertIn("REFERENCE ONLY", parsed["example_box"])
        self.assertIn("print(len(name))", parsed["example_box"])
        # Ensure the example code is NOT in the statement
        self.assertNotIn("name = input()", parsed["statement"])

    def test_editor_normalization(self):
        """Verifies code normalization handles CRLF, trailing spaces, and blank lines."""
        c1 = "s1 = input()  \r\ns2 = input()\r\ns = s1 + s2 \r\nprint(s[::-1]) \r\n"
        c2 = "s1 = input()\ns2 = input()\ns = s1 + s2\nprint(s[::-1])"
        self.assertEqual(normalize_code(c1), normalize_code(c2))

    def test_resumability_and_progress_manager(self):
        """
        Acceptance test 3:
        Verifies progress recording and resumability (skipping exercises already passed).
        """
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            mgr = ProgressManager(filepath=temp_path)
            self.assertFalse(mgr.is_passed("2775"))

            # Record 2775 passed
            mgr.record_passed("2775", "s = input()\nprint(s[::-1])", attempts=1)
            self.assertTrue(mgr.is_passed("2775"))
            self.assertFalse(mgr.is_passed("2774"))

            # Simulate restart
            mgr2 = ProgressManager(filepath=temp_path)
            self.assertTrue(mgr2.is_passed("2775"))
            self.assertFalse(mgr2.is_passed("2774"))

            summary = mgr2.get_summary()
            self.assertEqual(summary["passed"], 1)
            self.assertEqual(summary["failed"], 0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_consecutive_exercises_stale_state_simulation(self):
        """
        Acceptance test 4:
        Simulates processing 3 consecutive exercises (2773, 2774, 2775)
        and verifies that stale-state guard prevents typing previous problem's code into the next.
        """
        exercises = [
            {
                "pid": "2773",
                "title": "String - Strip and Concat",
                "statement": "Complete the program so that it concatenates three input strings without extra whitespace.",
                "stub": "print(s1.strip() + s2.strip() + s3.strip())",
                "sample_io": [{"input": "a \nb \nc ", "output": "abc"}]
            },
            {
                "pid": "2774",
                "title": "Convert to lower case",
                "statement": "Complete the program so that it prints the input string value in lower case.",
                "stub": "print(inputstring.lower())",
                "sample_io": [{"input": "ABC", "output": "abc"}]
            },
            {
                "pid": "2775",
                "title": "Concatenate two strings and reverse",
                "statement": "Complete the program so that it accepts two string values, concatenates them and then prints the reverse of the concatenated value.",
                "stub": "print(s[::-1])",
                "sample_io": [{"input": "hi\nthere", "output": "erehtih"}]
            }
        ]

        solutions_generated = []
        prev_pid = None

        for ex in exercises:
            current_pid = ex["pid"]

            # Stale-state guard check
            if prev_pid is not None:
                self.assertNotEqual(current_pid, prev_pid, f"Stale-state guard failed: {current_pid} == {prev_pid}")

            problem = {
                "program_id": current_pid,
                "title": ex["title"],
                "statement": ex["statement"],
                "sample_io": ex["sample_io"],
                "constraints": ""
            }

            code = generate_solution(problem, ex["stub"])
            solutions_generated.append((current_pid, code))

            # Verify that solution is specific to this exercise and does not contain previous code
            code_str = code[0] if isinstance(code, (tuple, list)) else code
            if prev_pid == "2774" and current_pid == "2775":
                self.assertNotIn("inputstring.lower()", code_str)
                self.assertIn("s[::-1]", code_str)

            prev_pid = current_pid

        self.assertEqual(len(solutions_generated), 3)
        self.assertEqual(solutions_generated[0][0], "2773")
        self.assertEqual(solutions_generated[1][0], "2774")
        self.assertEqual(solutions_generated[2][0], "2775")


if __name__ == "__main__":
    unittest.main()
