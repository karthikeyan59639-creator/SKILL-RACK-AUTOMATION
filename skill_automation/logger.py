import logging
import os
import sys
from skill_automation.config import LOGS_DIR, LOG_FILE

os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger("skill_automation")
logger.setLevel(logging.INFO)

# Formatter with detailed ISO timestamps
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

# File Handler
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

def log_info(msg: str):
    logger.info(msg)

def log_error(msg: str):
    logger.error(msg)

def log_warning(msg: str):
    logger.warning(msg)
