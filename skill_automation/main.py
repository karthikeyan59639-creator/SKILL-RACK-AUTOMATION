import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from auth import verify_project_access
from orchestrator import run_orchestrator
from config import HEADLESS

def main():
    verify_project_access()
    run_orchestrator(headless=HEADLESS)

if __name__ == "__main__":
    verify_project_access()
    main()
