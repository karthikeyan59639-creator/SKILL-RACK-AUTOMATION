import os
from dotenv import load_dotenv

# Call load_dotenv() before any environment variables are read
load_dotenv()

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# Read Credentials & LLM Configuration from Environment
USERNAME = os.getenv("SKILLRACK_USERNAME")
PASSWORD = os.getenv("SKILLRACK_PASSWORD")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_env_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_MODEL = _env_model

# Parse HEADLESS from string into boolean
HEADLESS_STR = os.getenv("HEADLESS", "False")
HEADLESS = str(HEADLESS_STR).strip().lower() in ("true", "1", "yes")

# Validate required variables without printing or exposing their values
if not USERNAME:
    raise ValueError("Missing required environment variable: SKILLRACK_USERNAME")
if not PASSWORD:
    raise ValueError("Missing required environment variable: SKILLRACK_PASSWORD")
if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise ValueError("Missing required environment variable: GEMINI_API_KEY")

# Browser & Timeout Settings
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "180000"))
NAV_WAIT_UNTIL = os.getenv("NAV_WAIT_UNTIL", "domcontentloaded")
SKILLRACK_URL = os.getenv("SKILLRACK_URL", "https://skillrack.com/faces/ui/profile.xhtml")
STORAGE_STATE_FILE = os.path.join(PROJECT_ROOT, "storage_state.json")

# LLM & Solver Execution Settings
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "4"))
ACTION_DELAY_MS = int(os.getenv("ACTION_DELAY_MS", "800"))

# Automation Control
FIRST_TEST_ONLY = os.getenv("FIRST_TEST_ONLY", "False").lower() in ("true", "1", "yes")
STOP_ON_FAILURE = os.getenv("STOP_ON_FAILURE", "False").lower() in ("true", "1", "yes")
CLOSE_BROWSER_ON_FINISH = os.getenv("CLOSE_BROWSER_ON_FINISH", "False").lower() in ("true", "1", "yes")
TAKE_SUCCESS_SCREENSHOTS = True
TAKE_FAILURE_SCREENSHOTS = True
TOTAL_PROBLEMS_PER_SECTION = 10

# Sections
SECTIONS = [
    "H001", "H002", "H003", "H004", "H005", "H006",
    "H007", "H008", "H009", "H010", "H011", "H012",
    "H013", "H014", "H015"
]

# Output Files & Directories
PROGRESS_FILE = os.path.join(PROJECT_ROOT, "progress.json")
SCREENSHOTS_DIR = os.path.join(PROJECT_ROOT, "screenshots")
FAILURES_DIR = os.path.join(PROJECT_ROOT, "failures")
DEBUG_DIR = os.path.join(PROJECT_ROOT, "debug")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "automation.log")

# Indicator Strings
SUCCESS_INDICATORS = [
    "Congratulations! Your Code has passed",
    "Great! Your code has passed",
    "Proceed Next"
]

FAILURE_INDICATORS = [
    "Code did not pass the execution",
    "Wrong Answer",
    "Traceback (most recent call last)"
]

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(FAILURES_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
