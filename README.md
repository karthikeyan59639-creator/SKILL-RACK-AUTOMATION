# SkillRack Python Code Tutor Autonomous Solver

An automated, resilient, and adaptive solver for SkillRack's Python Code Tutor (`tutorprogram.xhtml`). It navigates through Python Code Tutor exercises sequentially, extracts task requirements, builds upon pre-filled editor stubs, synthesizes solutions via LLM APIs (Gemini, Claude, GPT) with analytical fallback, validates solutions locally, injects code with multi-engine editor support and read-back assertions, executes the code, and advances with a stale-state guard.

---

## Architecture Overview

```
                      +-----------------------------+
                      |     BrowserManager          |
                      |  (Login, Session, Captcha)  |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |       orchestrator.py       |
                      |  (Main Loop & Stale Guard)  |<----+
                      +--------------+--------------+     |
                                     |                    |
        +----------------------------+-----------------+  |
        |                            |                 |  |
        v                            v                 v  |
+-------------------+      +-------------------+     +----+-------------+
| problem_scraper.py|      |     editor.py     |     |    runner.py     |
| (DOM Inspection,  |      | (Ace, CodeMirror, |     | (Run, Detection, |
| Task vs Example)  |      | Monaco, Textarea) |     | Diagnostics)     |
+---------+---------+      +---------+---------+     +------------------+
          |                          |
          v                          v
+-------------------+      +-------------------+
|     solver.py     |----->|  local_check.py   |
| (LLM / Analytical |      | (Subprocess test, |
| Stub Completer)   |      |   5s timeout)     |
+-------------------+      +-------------------+
```

### Modules

1. **[problem_scraper.py](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/problem_scraper.py)**:
   - `scrape_problem(page) -> dict`: Extracts `program_id`, `topic`, `title`, `statement`, `sample_io`, `constraints`, `time_limit`, and `example_box`.
   - Locates elements using stable structure and text anchors (`ProgramID-` badge, task phrasing).
   - Isolates the reference concept example box (`example_box`) so it is never confused with the actual task statement.

2. **[editor.py](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/editor.py)**:
   - `detect_editor(page) -> str`: Detects CodeMirror 5, CodeMirror 6, Ace, Monaco, or textarea.
   - `get_code(page) -> str`: Reads the starter stub without modifying it.
   - `set_code(page, code, max_retries=3) -> bool`: Fully clears old content, injects code via multi-engine JS evaluators (with keyboard fallback), reads the value back, normalizes line endings and trailing whitespace, and asserts exact match. Retries up to 3 times.

3. **[solver.py](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/solver.py)**:
   - `generate_solution(problem, stub, feedback=None) -> str`: Fulfills the standardized judge prompt template.
   - Integrates with Gemini (`GEMINI_API_KEY`), Anthropic (`ANTHROPIC_API_KEY`), or OpenAI (`OPENAI_API_KEY`).
   - Strips markdown fences (` ```python `) automatically.
   - Appends failure feedback (Input, Expected Output, Actual Output, Traceback) when retrying.
   - Contains an analytical offline fallback to synthesize solutions dynamically from statements and starter stubs (e.g. ProgramID 2775 and 2774).
   - Never overwrites starter stubs blindly; preserves starter lines and supplies missing variable inputs.

4. **[local_check.py](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/local_check.py)**:
   - `run_local_check(code, sample_io) -> tuple[bool, str]`: Runs generated code locally in a subprocess (5-second timeout) against sample inputs before submission.
   - Returns structured feedback if output does not match or code crashes.

5. **[runner.py](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/runner.py)**:
   - `run_code_and_get_result(page, timeout_sec=35) -> dict`: Clicks the Run button, monitors the execution result panel, and returns structured diagnostics (`passed`, `status`, `input`, `expected`, `actual`, `traceback`).

6. **[orchestrator.py](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/orchestrator.py)**:
   - The central loop coordinating problem scraping, reading starter stubs before clearing, solution generation, local checks, editor injection, Run execution, and result inspection.
   - **Stale-State Guard**: After every navigation, waits until the ProgramID badge text changes from the previous exercise (`wait_for_stale_state_change`), asserting `new_pid != prev_pid`.
   - **Resumability**: Checks [progress.json](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/progress.json) and skips exercises already passed.
   - **Retry Limit & Failure Dumps**: Retries up to `MAX_ATTEMPTS` (3) with feedback. If still failing, saves a full-page screenshot, problem definition (`problem.json`), and attempted code (`attempted_code.py`) to `./failures/<program_id>/` and advances to the next exercise.
   - Prints a final summary report of passed, failed, and skipped exercises.

7. **[skill_automation/browser_manager.py](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/skill_automation/browser_manager.py)** & **[skill_automation/code_typer.py](file:///e:/Documents/SKILL%20RACK%20AUTOMATION/skill_automation/code_typer.py)**:
   - Preserves working captcha OCR (`solve_captcha` with math expression template matching).
   - Replaces legacy typing logic with editor-aware `type_code` and `read_code`.

---

## Setup & Installation

### 1. Requirements
- Python 3.10+ (tested on Python 3.14)
- Playwright Chromium browser

### 2. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configuration & API Keys
Create a `.env` file in the project root or set environment variables:

```ini
# SkillRack Credentials
SKILLRACK_USERNAME=your_username@institution
SKILLRACK_PASSWORD=your_password

# LLM Configuration
LLM_PROVIDER=gemini        # 'gemini', 'anthropic', or 'openai'
LLM_MODEL=gemini-2.5-flash # or 'claude-3-5-sonnet-20241022', 'gpt-4o-mini'

# API Keys (Set the one matching your LLM_PROVIDER)
GEMINI_API_KEY=your_gemini_api_key
# ANTHROPIC_API_KEY=your_anthropic_api_key
# OPENAI_API_KEY=your_openai_api_key

# Execution Options
HEADLESS=False             # Set to True for headless execution
MAX_ATTEMPTS=3             # Retry attempts per problem on failure
ACTION_DELAY_MS=500        # Random jitter delay to prevent rate limits
```

---

## Running the Automation

### Run the Autonomous Orchestrator:
```bash
python orchestrator.py
```
*(Or via `python main.py`)*

### Run Acceptance Tests:
```bash
python -m unittest test_acceptance.py test_playwright_pipeline.py
```

All 8 tests cover:
- ProgramID 2775 (stub `print(s[::-1])` + two string concatenation)
- ProgramID 2774 (Convert to lower case)
- Concept example box separation from task instructions
- Editor code normalization (CRLF / whitespace)
- Progress tracking and resumability across restarts
- Stale-state guard asserting ProgramID change across consecutive exercises
- Live Playwright page scraping, editor injection, and runner verification
