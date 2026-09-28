import os

# Project Root Directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Browser Settings
HEADLESS = False
DEFAULT_TIMEOUT = 60000  # 60 seconds
NAV_WAIT_UNTIL = "domcontentloaded"

# Website & Credentials
SKILLRACK_URL = "https://skillrack.com/faces/ui/profile.xhtml"
USERNAME = "2117250080034@rgit"
PASSWORD = "jai0011k@"
STORAGE_STATE_FILE = os.path.join(PROJECT_ROOT, "storage_state.json")

# Automation Behavior
TOTAL_PROBLEMS_PER_SECTION = 10
STOP_ON_FAILURE = True
TAKE_SUCCESS_SCREENSHOTS = True
TAKE_FAILURE_SCREENSHOTS = True
DRY_RUN = False  # Set to True for dry-run verification without submitting

# Configurable Sections Loop
SECTIONS = [
    "H001",
    "H002",
    "H003",
    "H004",
    "H005",
    "H006"
]

# Output Directories & Files
PROGRESS_FILE = os.path.join(PROJECT_ROOT, "progress.json")
SCREENSHOTS_DIR = os.path.join(PROJECT_ROOT, "screenshots")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "automation.log")

# Success & Failure Indicator Strings
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
