import re
from solver import solve_problem as ai_solve_problem, KNOWN_SOLUTIONS
from logger import log_info, log_warning

# Configurable dictionary for user-supplied code solutions per section & problem number
SOLUTIONS = {
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
    "H002": {}
}

def sanitize_solution_for_template(code: str, problem_meta: dict = None) -> str:
    """
    Inspects existing prefix/template code and strips duplicate input statements or aligns variable names.
    Prevents duplicating template lines already present outside the editor.
    """
    if not code:
        return ""
    if not problem_meta:
        return code.strip()

    prefix = (problem_meta.get("prefixCode") or "").strip()
    prefix_lines = set(line.strip() for line in prefix.splitlines() if line.strip())

    # Check ONLY prefixCode (code rendered outside editor) for active input() assignment
    m_prefix_var = re.search(r'^\s*([a-zA-Z_]\w*)\s*=\s*input\(\)', prefix, re.M)

    lines = code.strip().splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # If line is an input assignment and prefix already provided input()
        if m_prefix_var and re.search(r'^\s*\w+\s*=\s*input\(\)', stripped):
            continue
        # If line is already identically present in prefix (e.g. import or header statement)
        if stripped in prefix_lines and len(stripped) > 3 and not stripped.startswith('#'):
            continue
        cleaned.append(line)

    res_code = "\n".join(cleaned)
    if m_prefix_var:
        template_var = m_prefix_var.group(1)
        if template_var != 's':
            res_code = re.sub(r'\bs\b', template_var, res_code)

    return res_code.strip()



def get_solution_code(section: str, problem_num: int, problem_meta: dict) -> str:
    """
    Returns code supplied in SOLUTIONS dictionary or deduced via solver.
    Sanitizes code against template code to avoid duplication.
    """
    pid = problem_meta.get("pid")
    raw_code = None

    if pid and str(pid) in KNOWN_SOLUTIONS:
        log_info(f"[SOLUTIONS] Found verified solution code for ProgramID-{pid}")
        raw_code = KNOWN_SOLUTIONS[str(pid)]
    elif section in SOLUTIONS and problem_num in SOLUTIONS[section]:
        log_info(f"[SOLUTIONS] Found configured solution code for Section {section} Problem {problem_num}")
        raw_code = SOLUTIONS[section][problem_num]
    else:
        log_info(f"[SOLUTIONS] Requesting solution engine for ProgramID-{pid}...")
        raw_code = ai_solve_problem(problem_meta)

    if raw_code:
        sanitized = sanitize_solution_for_template(raw_code, problem_meta)
        log_info(f"[SOLUTIONS SANITIZE] Cleaned solution code:\n{sanitized}")
        return sanitized

    log_warning(f"[SOLUTIONS] No solution code found for Section {section} Problem {problem_num}.")
    return None

