from solver import solve_problem as ai_solve_problem, KNOWN_SOLUTIONS
from skill_automation.logger import log_info, log_warning

# Configurable database for user-supplied code solutions per section & problem number
SOLUTIONS_DB = {
    "H001": {
        1: "x = 10\ny = 10",
        2: 'city = "Chennai"',
        3: 'a = 4\nb = 4\nc = 4',
        4: 'print(x, end="*")',
        5: 'x = int(input())\ny = int(input())\nprint(x * y)',
        6: 'x = float(input())\ny = float(input())\nprint(x - y)',
        7: 'print(round(x + y, 3))',
        8: 'fruitName = "Mango"\nvegetableName = "Brinjal"\nmoviename = "Aviator"',
        9: 'mymessage = "success"'
    },
    "H002": {
        1: "s = input()\nprint(s[1])",
        2: "s = input()\nprint(s[:5])",
        3: "s = input()\nprint(s[1:])"
    }
}

def get_solution(section: str, problem_num: int, problem_meta: dict) -> str:
    """
    Obtains the solution code for the given section and problem number.
    Checks user SOLUTIONS_DB first, then KNOWN_SOLUTIONS cache, then AI solver engine.
    """
    # 1. Check user-supplied SOLUTIONS_DB dictionary
    if section in SOLUTIONS_DB and problem_num in SOLUTIONS_DB[section]:
        log_info(f"[SOLUTIONS] Found user-supplied solution for Section {section} Problem {problem_num}")
        return SOLUTIONS_DB[section][problem_num]

    # 2. Check KNOWN_SOLUTIONS by ProgramID if present
    pid = problem_meta.get("pid")
    if pid and pid in KNOWN_SOLUTIONS:
        log_info(f"[SOLUTIONS] Found verified solution for ProgramID-{pid}")
        return KNOWN_SOLUTIONS[pid]

    # 3. Call analytical AI solver engine
    log_info(f"[SOLUTIONS] Generating solution via AI solver engine for ProgramID-{pid}...")
    ai_solution = ai_solve_problem(problem_meta)
    if ai_solution:
        return ai_solution

    log_warning(f"[SOLUTIONS] No solution found for Section {section} Problem {problem_num} (PID: {pid}).")
    return None
