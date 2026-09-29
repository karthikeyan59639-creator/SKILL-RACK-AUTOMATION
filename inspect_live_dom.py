from playwright.sync_api import sync_playwright
import re
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state='storage_state.json')
    page = context.new_page()
    page.goto('https://skillrack.com/faces/candidate/tutorgroup.xhtml', wait_until='domcontentloaded')
    
    view_btn = page.locator('button, a, input').filter(has_text=re.compile(r'^\s*(View|Resume)\s*$', re.I)).first
    if view_btn.is_visible(timeout=5000):
        print('Clicking:', view_btn.inner_text().strip())
        view_btn.click()
        page.wait_for_timeout(3000)

    print('Current URL:', page.url)
    dom_info = page.evaluate("""() => {
        let pres = Array.from(document.querySelectorAll('pre')).map(p => ({
            tag: 'pre',
            id: p.id,
            className: p.className,
            innerText: p.innerText,
            textContent: p.textContent.trim(),
            display: window.getComputedStyle(p).display
        }));
        let highlighters = Array.from(document.querySelectorAll('.syntaxhighlighter, div[id*="Code"], div[id*="code"]')).map(d => ({
            tag: d.tagName,
            id: d.id,
            className: d.className,
            innerText: d.innerText ? d.innerText.substring(0, 80) : '',
            display: window.getComputedStyle(d).display
        }));
        return { pres, highlighters };
    }""")
    print(json.dumps(dom_info, indent=2))
    browser.close()
