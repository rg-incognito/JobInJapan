"""Probe how the Greenhouse 'School' search dropdown responds to typing (no extension, no submit)."""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto("https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=8175656", wait_until="domcontentloaded")
    time.sleep(5)
    sch = pg.locator("input#school--0")
    print("school inputs:", sch.count(), pg.evaluate("[...document.querySelectorAll('input[role=combobox]')].map(e=>e.id).join(',')"))
    for q in ["Raisoni", "G H Raisoni", "Other"]:
        sch.click(); sch.fill(""); sch.type(q, delay=60); time.sleep(2.5)
        opts = pg.evaluate("(() => { const i=document.getElementById('school--0'); const lb=i.getAttribute('aria-controls'); const vis=[...document.querySelectorAll('[role=option],[id*=-option-]')].filter(o=>o.getBoundingClientRect().height>0).map(o=>o.textContent).slice(0,8); return {ctrl: lb, owns: i.getAttribute('aria-owns'), vis}; })()")
        print(q, "->", opts)
        pg.keyboard.press("Escape")
    b.close()
