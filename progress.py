import json
import os
from datetime import datetime
from config import PROGRESS_FILE
from logger import log_info, log_error

class ProgressManager:
    def __init__(self, filepath: str = PROGRESS_FILE):
        self.filepath = filepath
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                if os.path.getsize(self.filepath) == 0:
                    return {"exercises": {}, "summary": {"passed": 0, "failed": 0, "skipped": 0}}
                with open(self.filepath, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, dict):
                        return content
            except Exception as e:
                log_error(f"[PROGRESS] Failed to read '{self.filepath}': {e}. Initializing fresh progress.")
        return {"exercises": {}, "summary": {"passed": 0, "failed": 0, "skipped": 0}}

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            log_error(f"[PROGRESS] Failed to save progress to '{self.filepath}': {e}")

    def _ensure_exercises(self):
        if "exercises" not in self.data:
            self.data["exercises"] = {}

    def is_passed(self, program_id: str) -> bool:
        """Returns True if the given program_id has already been successfully solved."""
        if not program_id:
            return False
        pid_str = str(program_id).strip()
        self._ensure_exercises()

        # Check exercises dict
        if pid_str in self.data["exercises"]:
            return self.data["exercises"][pid_str].get("status") == "passed"

        # Check legacy section-based structure
        for k, v in self.data.items():
            if isinstance(v, dict) and "problems" in v:
                for prob_k, prob_v in v["problems"].items():
                    if str(prob_v.get("program_id")) == pid_str and prob_v.get("status") == "passed":
                        return True

        return False

    def record_passed(self, program_id: str, code: str, attempts: int):
        """Records a successfully passed exercise."""
        pid_str = str(program_id).strip()
        self._ensure_exercises()
        self.data["exercises"][pid_str] = {
            "program_id": pid_str,
            "status": "passed",
            "code": code,
            "attempts": attempts,
            "timestamp": datetime.now().isoformat()
        }
        self._update_summary()
        self.save()
        log_info(f"[PROGRESS] Recorded PASSED status for ProgramID-{pid_str} (Attempts: {attempts}).")

    def record_failed(self, program_id: str, code: str, attempts: int, error: str = ""):
        """Records a failed exercise."""
        pid_str = str(program_id).strip()
        self._ensure_exercises()
        self.data["exercises"][pid_str] = {
            "program_id": pid_str,
            "status": "failed",
            "code": code,
            "attempts": attempts,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        self._update_summary()
        self.save()
        log_info(f"[PROGRESS] Recorded FAILED status for ProgramID-{pid_str}.")

    def record_skipped(self, program_id: str, reason: str = ""):
        """Records a skipped exercise."""
        pid_str = str(program_id).strip()
        self._ensure_exercises()
        self.data["exercises"][pid_str] = {
            "program_id": pid_str,
            "status": "skipped",
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        self._update_summary()
        self.save()
        log_info(f"[PROGRESS] Recorded SKIPPED status for ProgramID-{pid_str}.")

    def _update_summary(self):
        self._ensure_exercises()
        passed = sum(1 for v in self.data["exercises"].values() if v.get("status") == "passed")
        failed = sum(1 for v in self.data["exercises"].values() if v.get("status") == "failed")
        skipped = sum(1 for v in self.data["exercises"].values() if v.get("status") == "skipped")
        self.data["summary"] = {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "total_processed": len(self.data["exercises"])
        }

    def get_summary(self) -> dict:
        self._update_summary()
        return self.data.get("summary", {"passed": 0, "failed": 0, "skipped": 0})
