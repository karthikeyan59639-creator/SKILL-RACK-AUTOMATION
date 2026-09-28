from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto('https://skillrack.com/faces/ui/profile.xhtml')
    time.sleep(3)
    inputs = page.evaluate('''() => {
        return Array.from(document.querySelectorAll('input, button')).map(i => ({
            tag: i.tagName, name: i.name, id: i.id, type: i.type, text: i.innerText || i.value
        }));
    }''')
    print('Inputs found:', inputs, flush=True)
    browser.close()
