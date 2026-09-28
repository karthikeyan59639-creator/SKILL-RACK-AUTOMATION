from skill_automation.config import TOTAL_PROBLEMS_PER_SECTION
from skill_automation.logger import log_info, log_error, log_warning
from skill_automation.problem_runner import ProblemRunner

class SectionRunner:
    @staticmethod
    def run_section(page, browser_mgr, progress_mgr, section: str) -> bool:
        """
        Executes all 10 problems for the given section sequentially.
        Only marks section COMPLETED after ALL 10 problems succeed.
        """
        log_info(f"\n============================================================")
        log_info(f"[SECTION RUNNER] Commencing processing for Section '{section}'")
        log_info(f"============================================================\n")

        sec_info = progress_mgr.get_section_info(section)
        if sec_info.get("status") == "completed":
            log_info(f"[SECTION] Section {section} is already marked COMPLETED in progress.json. Skipping.")
            return True

        for prob_num in range(1, TOTAL_PROBLEMS_PER_SECTION + 1):
            if progress_mgr.is_problem_completed(section, prob_num):
                log_info(f"[RESUME] Section {section} Problem {prob_num:02d} is already COMPLETED. Skipping.")
                continue

            log_info(f"[SECTION LOGIC] Processing Section {section} -> Problem {prob_num}/{TOTAL_PROBLEMS_PER_SECTION}")
            success = ProblemRunner.run_problem(page, browser_mgr, progress_mgr, section, prob_num)

            if not success:
                log_error(f"[SECTION FAIL] Section {section} stopped at Problem {prob_num:02d} due to failure.")
                return False

        # Mark section completed after all 10 problems succeed
        sec_info["status"] = "completed"
        progress_mgr.save()
        log_info(f"\n============================================================")
        log_info(f"[SECTION COMPLETE] >>> Section '{section}' COMPLETED SUCCESSFULLY! <<<")
        log_info(f"============================================================\n")
        return True
