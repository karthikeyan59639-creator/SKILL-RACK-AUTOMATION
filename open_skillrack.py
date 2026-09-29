"""
open_skillrack.py - Opens SkillRack in a visible browser window, logs in, 
navigates to your Python Code Tutor courses, and keeps the browser open 
until you press Enter in the terminal.
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from skill_automation.browser_manager import BrowserManager

def main():
    print("==================================================")
    print("  LAUNCHING SKILLRACK IN VISIBLE BROWSER...")
    print("==================================================")
    
    bm = BrowserManager(headless=False)
    page = bm.start()
    
    # Logs in and navigates to the candidate profile / tutor
    bm.login_and_navigate()
    
    # Navigate directly to Code Tutor Python programming overview
    page.goto("https://skillrack.com/faces/candidate/codeprogramgroup.xhtml?gt=CODETUTOR")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)
    
    # Expand Python Programming section
    py_btn = page.locator("tr").filter(has_text="Python Programming").locator("button:has-text('Show')").first
    if py_btn.is_visible(timeout=4000):
        py_btn.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)
        
    print("\n>>> SkillRack is now OPEN and logged in on your screen! <<<")
    print("You can view your completed tracks, challenges, and certificates.")
    print("Press [Enter] in this terminal when you are done to close the browser...")
    
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        bm.close()
        print("Browser closed.")

if __name__ == "__main__":
    main()
