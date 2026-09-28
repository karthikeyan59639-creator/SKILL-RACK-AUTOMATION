import json
import os
from datetime import datetime
from config import PROGRESS_FILE, TOTAL_PROBLEMS_PER_SECTION
from logger import log_info, log_error

class ProgressManager:
    def __init__(self, filepath: str = PROGRESS_FILE):
        self.filepath = filepath
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log_error(f"Failed to read progress file '{self.filepath}': {e}. Initializing fresh progress.")
        return {}

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            log_error(f"Failed to save progress to '{self.filepath}': {e}")

    def get_section_info(self, section: str) -> dict:
        if section not in self.data:
            self.data[section] = {
                "status": "pending",
                "completed_problems": 0,
                "total_problems": TOTAL_PROBLEMS_PER_SECTION,
                "problems": {}
            }
        return self.data[section]

    def is_problem_completed(self, section: str, problem_num: int) -> bool:
        sec_info = self.get_section_info(section)
        prob_key = f"problem_{problem_num:02d}"
        if sec_info.get(prob_key) == "completed":
            return True
        prob_str = str(problem_num)
        prob_data = sec_info.get("problems", {}).get(prob_str, {})
        return prob_data.get("status") == "completed"

    def mark_problem_status(self, section: str, problem_num: int, status: str, screenshot_path: str = None, error_msg: str = None):
        sec_info = self.get_section_info(section)
        sec_info["status"] = "in_progress"
        prob_key = f"problem_{problem_num:02d}"
        sec_info[prob_key] = status

        if problem_num + 1 <= TOTAL_PROBLEMS_PER_SECTION:
            next_key = f"problem_{problem_num+1:02d}"
            if next_key not in sec_info:
                sec_info[next_key] = "pending"

        prob_str = str(problem_num)
        now_iso = datetime.now().isoformat()
        prob_record = {
            "section": section,
            "problem": problem_num,
            "status": status,
            "timestamp": now_iso,
            "screenshot": screenshot_path
        }
        if error_msg:
            prob_record["error"] = error_msg

        if "problems" not in sec_info:
            sec_info["problems"] = {}
        sec_info["problems"][prob_str] = prob_record

        completed_count = sum(
            1 for p_num in range(1, TOTAL_PROBLEMS_PER_SECTION + 1)
            if sec_info.get(f"problem_{p_num:02d}") == "completed" or sec_info.get("problems", {}).get(str(p_num), {}).get("status") == "completed"
        )
        sec_info["completed_problems"] = completed_count

        if completed_count >= TOTAL_PROBLEMS_PER_SECTION:
            sec_info["status"] = "completed"
            log_info(f"[PROGRESS] Section {section} is 100% COMPLETED ({completed_count}/{TOTAL_PROBLEMS_PER_SECTION})!")

        self.save()

    def get_resume_target(self, sections: list) -> tuple:
        """Returns (first_incomplete_section, first_incomplete_problem_number)."""
        for sec in sections:
            sec_info = self.get_section_info(sec)
            if sec_info.get("status") == "completed":
                continue
            for prob in range(1, TOTAL_PROBLEMS_PER_SECTION + 1):
                if not self.is_problem_completed(sec, prob):
                    return (sec, prob)
        return (None, None)
