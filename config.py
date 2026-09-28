import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# Browser & Timeout Settings
HEADLESS = False
DEFAULT_TIMEOUT = 60000
NAV_WAIT_UNTIL = "domcontentloaded"

# Website & Credentials
SKILLRACK_URL = "https://skillrack.com/faces/ui/profile.xhtml"
USERNAME = "2117250080034@rgit"
PASSWORD = "jai0011k@"
STORAGE_STATE_FILE = os.path.join(PROJECT_ROOT, "storage_state.json")

# Workflow Flags
FIRST_TEST_ONLY = True  # Set to True for initial verification milestone (stops before submitting)
TOTAL_PROBLEMS_PER_SECTION = 10
STOP_ON_FAILURE = True
TAKE_SUCCESS_SCREENSHOTS = True
TAKE_FAILURE_SCREENSHOTS = True

# Configurable Sections Loop
SECTIONS = [
    "H002",
    "H003",
    "H004",
    "H005"
]

# Output Files & Directories
PROGRESS_FILE = os.path.join(PROJECT_ROOT, "progress.json")
SCREENSHOTS_DIR = os.path.join(PROJECT_ROOT, "screenshots")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "automation.log")
