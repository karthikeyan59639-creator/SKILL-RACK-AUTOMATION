import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from orchestrator import run_orchestrator
from config import HEADLESS

def main():
    run_orchestrator(headless=HEADLESS)

if __name__ == "__main__":
    main()
