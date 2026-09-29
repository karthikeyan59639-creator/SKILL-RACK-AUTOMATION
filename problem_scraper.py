import re
import json
from logger import log_info, log_warning, log_error

def extract_stub_from_raw_text(raw_text: str) -> str:
    """
    Extracts starter code lines that appear in the raw page text
    (e.g., between the language dropdown and user handle / buttons).
    """
    if not raw_text:
        return ""
    m = re.search(
        r"Python3\s*\([^)]*\)\s*\n(?:Python3\s*\([^)]*\)\s*\n)?(.*?)\n(?:[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+|Save\s*\n\s*Run)",
        raw_text,
        re.DOTALL
    )
    if m:
        lines = []
        for line in m.group(1).splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            if any(kw in line_str for kw in ["Save", "Run", "Ambiance", "ui-button", "Chaos", "Cobalt", "Eclipse", "Chrome", "SQL Server"]):
                continue
            if line_str.isdigit():
                continue
            lines.append(line.rstrip())
        return "\n".join(lines).strip()
    return ""


def parse_problem_text(raw_text: str) -> dict:
    """
    Parses structured problem details from the left panel text of tutorprogram.xhtml.
    Separates reference example boxes from the actual task statement.
    """
    if not raw_text:
        return {
            "program_id": "",
            "topic": "",
            "concept": "",
            "title": "",
            "statement": "",
            "sample_io": [],
            "constraints": "",
            "time_limit": "",
            "example_box": "",
            "raw_text": ""
        }

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    # 1. Program ID extraction
    pid_match = re.search(r"ProgramID-\s*(\d+)", raw_text, re.IGNORECASE)
    program_id = pid_match.group(1) if pid_match else ""

    # Split text into Reference section (before ProgramID) and Task section (after ProgramID)
    before_pid = ""
    after_pid = ""
    if pid_match:
        split_pos = pid_match.start()
        before_pid = raw_text[:split_pos]
        after_pid = raw_text[pid_match.end():]
    else:
        after_pid = raw_text

    # 2. Topic and Concept extraction (from before ProgramID)
    topic = ""
    concept = ""
    example_box = ""

    before_lines = [l.strip() for l in before_pid.splitlines() if l.strip()]
    if before_lines:
        for idx, line in enumerate(before_lines):
            if re.search(r"Python\d*-[A-Z0-9]+", line, re.IGNORECASE):
                topic = line
                if idx + 1 < len(before_lines):
                    concept = before_lines[idx + 1]
                break

    if not topic and lines:
        for line in lines[:3]:
            if re.search(r"Python\d*-[A-Z0-9]+", line, re.IGNORECASE):
                topic = line
                break

    # Look for example code in the reference section
    # Common pattern: code with print, input, assignments
    example_candidates = []
    in_code = False
    for l in before_lines:
        if any(kw in l for kw in ["print(", "input(", "=", "[", "def ", "for ", "while "]) and not l.startswith("The ") and not l.startswith("As an"):
            example_candidates.append(l)
    if example_candidates:
        example_box = "REFERENCE ONLY (DO NOT USE AS TASK ANSWER):\n" + "\n".join(example_candidates)

    # 3. Title extraction (first non-empty heading line after ProgramID)
    title = ""
    after_lines = [l.strip() for l in after_pid.splitlines() if l.strip()]
    
    # Remove branding like "SKILLRACK" right after ProgramID
    cleaned_after_lines = []
    for l in after_lines:
        if l.upper() == "SKILLRACK" or l.startswith("ProgramID"):
            continue
        cleaned_after_lines.append(l)

    if cleaned_after_lines:
        title = cleaned_after_lines[0]

    # 4. Time limit
    time_limit = ""
    time_match = re.search(r"(Max Execution Time Limit:\s*\d+\s*(?:millisecs|ms|seconds|s)?)", raw_text, re.IGNORECASE)
    if time_match:
        time_limit = time_match.group(1).strip()

    # 5. Constraints
    constraints = ""
    constraints_match = re.search(r"(?:Constraints?:?\s*)([^\n]+)", after_pid, re.IGNORECASE)
    if constraints_match:
        constraints = constraints_match.group(1).strip()
    else:
        assume_match = re.search(r"\((Assume [^)]+)\)", after_pid, re.IGNORECASE)
        if assume_match:
            constraints = assume_match.group(1).strip()

    # 6. Sample I/O extraction
    sample_io = []
    # Pattern: Input:\s*(.*?)\s*Expected Output:\s*(.*?)(?=\n\s*(?:Input:|Sample|Max Execution|$)|\Z)
    io_matches = re.finditer(
        r"(?:Sample\s+)?Input:\s*\n?(.*?)\s*(?:Sample\s+)?(?:Expected\s+)?Output:\s*\n?(.*?)(?=(?:Sample\s+)?Input:|Example|\n\s*Max Execution|\n\s*ui-button|\Z)",
        after_pid,
        re.IGNORECASE | re.DOTALL
    )
    for m in io_matches:
        s_in = m.group(1).strip()
        s_out = m.group(2).strip()
        if s_in or s_out:
            if s_in:
                s_in = re.split(r"(?:(?:Sample\s+)?(?:Expected\s+)?Output:|Example)", s_in, flags=re.IGNORECASE)[0].strip().replace("\u00a0", " ")
            if s_out:
                s_out = re.split(r"(?:Example|Explanation:|Note:|Sample\s+Input|Input:|Your\s+Program\s+Output|Actual\s+Output|Max\s+Execution|ui-button|Ambiance)", s_out, flags=re.IGNORECASE)[0].strip().replace("\u00a0", " ")
            sample_io.append({
                "input": s_in,
                "output": s_out
            })

    # 7. Statement extraction:
    # Real task statement usually starts with "Complete the program so that...", "Insert the missing...", "Write a program..."
    statement = ""
    statement_candidates = []
    found_start = False
    for l in cleaned_after_lines[1:]:
        if any(skip_kw in l for skip_kw in ["Max Execution Time Limit", "Ambiance", "Python3 (3.12)", "ui-button", "Save", "Run"]):
            break
        if re.match(r"(?:Sample\s+)?(?:Input|Output):|Example", l, re.IGNORECASE):
            break
        if any(l.startswith(prefix) for prefix in [
            "Complete the program", "Insert the missing", "Write a program",
            "The following program", "Accepts ", "Given ", "Print ", "You need to"
        ]) or found_start:
            found_start = True
            statement_candidates.append(l)

    if statement_candidates:
        statement = " ".join(statement_candidates).strip()
    elif len(cleaned_after_lines) > 1:
        # Fallback to lines between title and time limit
        fallback_lines = []
        for l in cleaned_after_lines[1:]:
            if "Max Execution Time Limit" in l or "Ambiance" in l or "Python3" in l:
                break
            if re.match(r"(?:Sample\s+)?(?:Input|Output):", l, re.IGNORECASE):
                break
            fallback_lines.append(l)
        statement = " ".join(fallback_lines).strip()

    # 8. Synthesize sample_io if empty and statement states target output
    if not sample_io:
        m_below = re.search(r"prints\s+the\s+output\s+given\s+below\.?\s*\n(.*?)(?=\n\s*(?:Max Execution|ui-button|Ambiance|Python3|\Z))", after_pid, re.DOTALL | re.IGNORECASE)
        if m_below:
            target_out = m_below.group(1).strip().replace("\u00a0", " ")
            sample_io.append({"input": "", "output": target_out})
        elif statement:
            m_out = re.search(r"prints\s+([0-9.]+|[^\s,.]+)\s+as\s+the\s+output", statement, re.IGNORECASE)
            if m_out:
                target_val = m_out.group(1).strip()
                sample_io.append({"input": "", "output": target_val})

    return {
        "program_id": program_id,
        "topic": topic,
        "concept": concept,
        "title": title,
        "statement": statement,
        "sample_io": sample_io,
        "constraints": constraints,
        "time_limit": time_limit,
        "example_box": example_box,
        "raw_text": raw_text
    }


def scrape_problem(page) -> dict:
    """
    Scrapes the active problem from the SkillRack tutorprogram page using DOM inspection
    and structural selectors. Never relies on fixed pixel coordinates.
    """
    log_info("[SCRAPER] Inspecting DOM to scrape problem details...")

    try:
        # Wait for left panel or programgrid to be present
        page.locator("#programgrid, .ui-g-12.ui-md-6, #codeeditorpanel").first.wait_for(state="attached", timeout=15000)
    except Exception as e:
        log_warning(f"[SCRAPER] Waiting for problem container attached warning: {e}")

    # Extract structured content directly from DOM
    dom_data = page.evaluate("""() => {
        let leftEl = document.querySelector('#programgrid') ||
                     document.querySelector('.ui-g-12.ui-md-6') ||
                     document.querySelector('.ui-md-6') ||
                     document.body;

        let leftText = leftEl ? leftEl.innerText : '';

        // Dedicated search for ProgramID element
        let pid = '';
        let allEls = Array.from(leftEl.querySelectorAll('*'));
        let pidEl = allEls.find(el => el.innerText && el.innerText.match(/ProgramID-\\s*\\d+/i));
        if (pidEl) {
            let m = pidEl.innerText.match(/ProgramID-\\s*(\\d+)/i);
            if (m) pid = m[1];
        }

        // Dedicated search for reference example box (<pre>, <code>, or black container before pid)
        let exampleBoxText = '';
        let preEls = Array.from(leftEl.querySelectorAll('pre, code'));
        if (preEls.length > 0) {
            exampleBoxText = preEls.map(p => p.innerText.trim()).filter(Boolean).join('\\n');
        }

        return {
            leftText: leftText,
            domPid: pid,
            domExample: exampleBoxText
        };
    }""")

    raw_text = dom_data.get("leftText", "")
    parsed = parse_problem_text(raw_text)

    # If DOM directly found a PID, ensure it is used
    if dom_data.get("domPid") and not parsed.get("program_id"):
        parsed["program_id"] = dom_data["domPid"]

    if dom_data.get("domExample") and not parsed.get("example_box"):
        parsed["example_box"] = "REFERENCE ONLY (DO NOT USE AS TASK ANSWER):\n" + dom_data["domExample"]

    log_info(f"[SCRAPER] ProgramID: {parsed.get('program_id')} | Title: '{parsed.get('title')}'")
    log_info(f"[SCRAPER] Statement: {parsed.get('statement')}")
    if parsed.get("sample_io"):
        log_info(f"[SCRAPER] Sample I/O pairs found: {len(parsed['sample_io'])}")
    if parsed.get("constraints"):
        log_info(f"[SCRAPER] Constraints: {parsed['constraints']}")
    if parsed.get("time_limit"):
        log_info(f"[SCRAPER] Time Limit: {parsed['time_limit']}")

    return parsed
