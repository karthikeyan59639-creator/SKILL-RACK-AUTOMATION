import sys
import ast
import subprocess
from solver import (
    generate_solution,
    assemble_final_code,
    verify_stub_preserved,
    extract_missing_lines_with_matcher,
    parse_solver_json
)
from local_check import run_local_check


def test_program_2775():
    print("\n--- TEST 1: ProgramID 2775 (Concatenate and reverse) ---")
    problem = {
        "program_id": "2775",
        "title": "Concatenate two strings and reverse",
        "statement": "accepts two string values, concatenates them and then prints the reverse of the concatenated value",
        "sample_io": [
            {"input": "hello\nworld\n", "output": "dlrowolleh"}
        ]
    }
    stub = "print(s[::-1])"

    final_code, before, after, *rest = generate_solution(problem, stub)
    print(f"Before lines: {before}")
    print(f"After lines:  {after}")
    print(f"Final code:\n{final_code}")

    # 1. Assert stub appears exactly once
    ok, msg = verify_stub_preserved(final_code, stub)
    assert ok, f"Stub preservation check failed: {msg}"
    assert "print(s[::-1])" in final_code
    assert final_code.count("print(s[::-1])") == 1

    # 2. Assert compilation
    ast.parse(final_code)
    compile(final_code, "<test>", "exec")

    # 3. Assert local execution against sample input
    passed, err = run_local_check(final_code, problem["sample_io"])
    assert passed, f"Local check failed: {err}"
    print("[PASS] Test 1: ProgramID 2775 passed all checks!")


def test_stub_both_sides():
    print("\n--- TEST 2: Stub needing lines on BOTH sides ---")
    problem = {
        "program_id": "9999",
        "title": "Square numbers",
        "statement": "Read space-separated integers, and print each squared value on a separate line.",
        "sample_io": [
            {"input": "2 3 4\n", "output": "4\n9\n16"}
        ]
    }
    stub = "for x in nums:"

    before = ["nums = list(map(int, input().split()))"]
    after = ["    print(x * x)"]
    final_code = assemble_final_code(before, stub, after)

    print(f"Stub: {stub}")
    print(f"Before lines: {before}")
    print(f"After lines:  {after}")
    print(f"Final code:\n{final_code}")

    # 1. Assert stub appears exactly once
    ok, msg = verify_stub_preserved(final_code, stub)
    assert ok, f"Stub preservation check failed: {msg}"
    assert final_code.count("for x in nums:") == 1

    # 2. Assert compilation
    ast.parse(final_code)
    compile(final_code, "<test>", "exec")

    # 3. Assert local execution against sample input
    passed, err = run_local_check(final_code, problem["sample_io"])
    assert passed, f"Local check failed: {err}"
    print("[PASS] Test 2: Stub with lines on both sides passed all checks!")


def test_sequencematcher_full_program_extraction():
    print("\n--- TEST 3: difflib.SequenceMatcher fallback on full program ---")
    stub = "result = a + b"
    full_program = (
        "a = int(input())\n"
        "b = int(input())\n"
        "result = a + b\n"
        "print(result)"
    )

    before, middle, after = extract_missing_lines_with_matcher(full_program, stub)
    print(f"Extracted Before: {before}")
    print(f"Extracted Middle: {middle}")
    print(f"Extracted After:  {after}")

    assembled = assemble_final_code(before, stub, after, middle=middle)
    print(f"Assembled:\n{assembled}")

    assert before == ["a = int(input())", "b = int(input())"]
    assert after == ["print(result)"]
    assert assembled == full_program
    ok, msg = verify_stub_preserved(assembled, stub)
    assert ok, f"Stub preservation check failed: {msg}"
    print("[PASS] Test 3: SequenceMatcher extracted before and after correctly!")


def test_program_2792_middle_insertion():
    print("\n--- TEST 4: ProgramID 2792 (Combine lists - middle line insertion) ---")
    problem = {
        "program_id": "2792",
        "title": "Concatenate Lists",
        "statement": "Complete the program to combine the items in list1 and list2 into list3.",
        "sample_io": [
            {"input": "ABC DEF\nXYZ MNO\n", "output": "ABC DEF XYZ MNO "}
        ]
    }
    stub = (
        "list1 = list(input().split())\n"
        "list2 = list(input().split())\n"
        "for item in list3:\n"
        "    print (item, end=\" \")"
    )

    final_code, before, after, middle = generate_solution(problem, stub)
    print(f"Before lines: {before}")
    print(f"Middle lines: {middle}")
    print(f"After lines:  {after}")
    print(f"Final code:\n{final_code}")

    ok, msg = verify_stub_preserved(final_code, stub)
    assert ok, f"Stub preservation check failed: {msg}"
    assert "list3 = list1 + list2" in final_code
    assert final_code.count("list1 = list(input().split())") == 1
    assert final_code.count("list2 = list(input().split())") == 1
    assert final_code.count("for item in list3:") == 1

    ast.parse(final_code)
    compile(final_code, "<test>", "exec")
    passed, err = run_local_check(final_code, problem["sample_io"])
    assert passed, f"Local check failed: {err}"
    print("[PASS] Test 4: ProgramID 2792 middle insertion passed all checks!")


def test_live_gemini_fill_mode():
    print("\n--- TEST 5: Live Gemini API call with fill-in-missing-lines JSON mode ---")
    problem = {
        "program_id": "test_live_2775",
        "title": "Concatenate two strings and reverse",
        "statement": "accepts two string values, concatenates them and then prints the reverse of the concatenated value",
        "sample_io": [
            {"input": "hello\nworld\n", "output": "dlrowolleh"}
        ]
    }
    stub = "print(s[::-1])"

    final_code, before, after, *rest = generate_solution(problem, stub)
    print(f"Live Gemini Before lines: {before}")
    print(f"Live Gemini After lines:  {after}")
    print(f"Live Gemini Final code:\n{final_code}")

    ok, msg = verify_stub_preserved(final_code, stub)
    assert ok, f"Stub preservation check failed: {msg}"
    assert "print(s[::-1])" in final_code
    assert final_code.count("print(s[::-1])") == 1

    ast.parse(final_code)
    passed, err = run_local_check(final_code, problem["sample_io"])
    assert passed, f"Local check failed: {err}"
    print("[PASS] Test 5: Live Gemini API call passed all checks!")


def test_split_prefix_suffix_2794():
    print("\n--- TEST 6: ProgramID 2794 (Split prefix above editor and suffix below editor) ---")
    problem = {
        "program_id": "2794",
        "title": "Add 400 and 500 to List",
        "statement": "A list of integers values is given as input. Complete the program so that it adds 400 and 500 to the list values and prints all elements separated by space.",
        "sample_io": [
            {"input": "", "output": "100 200 300 400 500 "}
        ]
    }
    prefix = "values = [100,200,300]"
    suffix = 'for v in values:\n    print (v, end=" ")'
    stub = f"{prefix}\n{suffix}"

    final_code, before, after, middle = generate_solution(problem, stub, prefix=prefix, suffix=suffix)
    print(f"Prefix: {prefix}")
    print(f"Suffix: {suffix}")
    print(f"Middle lines: {middle}")
    print(f"Final code:\n{final_code}")

    from editor import extract_editor_code_from_full
    code_for_editor = extract_editor_code_from_full(final_code, prefix, suffix)
    print(f"Extracted code for editor:\n{code_for_editor}")

    assert "values = [100,200,300]" not in code_for_editor
    assert "for v in values" not in code_for_editor
    assert "400" in code_for_editor and "500" in code_for_editor

    ast.parse(final_code)
    passed, err = run_local_check(final_code, problem["sample_io"])
    assert passed, f"Local check failed: {err}"
    print("[PASS] Test 6: Split prefix/suffix 2794 passed all checks!")


if __name__ == "__main__":
    test_program_2775()
    test_stub_both_sides()
    test_sequencematcher_full_program_extraction()
    test_program_2792_middle_insertion()
    test_live_gemini_fill_mode()
    test_split_prefix_suffix_2794()
    print("\n>>> ALL MOCK SOLVER TESTS (INCLUDING LIVE GEMINI & SPLIT PRE/SUF) PASSED! <<<\n")

