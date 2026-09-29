from skill_automation.browser_manager import BrowserManager
import json

bm = BrowserManager(headless=True)
try:
    page = bm.start()
    bm.login_and_navigate()
    bm.handle_captcha_and_wait_for_editor()
    
    info = page.evaluate("""() => {
        let panel = document.querySelector('#codediv, #codeeditorpanel') || document.body;
        let children = Array.from(panel.querySelectorAll('*')).map(el => {
            let text = (el.innerText || '').trim();
            let tc = (el.textContent || '').trim();
            if (!tc || tc.length > 500) return null;
            return {
                tag: el.tagName,
                id: el.id,
                className: el.className,
                visible: el.offsetParent !== null,
                innerText: text.substring(0, 150),
                textContent: tc.substring(0, 150)
            };
        }).filter(Boolean);
        return {
            url: window.location.href,
            panelId: panel.id,
            children: children
        };
    }""")
    with open("panel_dump.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print("SAVED panel_dump.json successfully!")
finally:
    bm.close()
