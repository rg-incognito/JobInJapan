"""
Live test of two JobFill behaviours (headless, NEVER submits):
  1. acknowledgement boxes ("Acknowledge/Confirm", "I have read ... privacy notice") get ticked
  2. what a human types into a field is learned (POST /learn -> data/learned.json or the job's answers.json)
The test types a dummy value, checks it was stored, then restores learned.json / answers.json.

  python tests/test_learn_ack.py        (needs src/autofill_server.py running)
"""
import json, shutil, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = str(ROOT / "extension")
OUT = ROOT / "tests" / "out"
LEARNED = ROOT / "data" / "learned.json"
PAGES = {
    "greenhouse_adyen": ("https://job-boards.greenhouse.io/adyen/jobs/7369512", "gh-adyen-7369512"),
    "ashby_snowflake": ("https://jobs.ashbyhq.com/snowflake/23c94498-23c8-4d6e-a1d8-4355bf605663/application",
                        "ab-snowflake-23c94498-23c8-4d6e-a1d8-4355bf605663"),
}
CHECKS = """() => [...document.querySelectorAll('input[type=checkbox]')].filter(c => c.offsetParent || c.closest('label'))
  .map(c => [((c.labels && c.labels[0] && c.labels[0].innerText) || c.closest('div')?.innerText || '').trim().slice(0, 70), c.checked])"""
# first empty, visible, plain text input that is not a combobox: the "human" types into it
FIND_EMPTY = """() => { const e = [...document.querySelectorAll('input[type=text],input:not([type]),textarea')]
  .find(x => !x.value && x.offsetParent && x.getAttribute('role') !== 'combobox' && !x.closest('[class*=select]') && !/recaptcha/.test(x.name||''));
  if (!e) return null; e.setAttribute('data-learn-test', '1');
  return (e.labels && e.labels[0] && e.labels[0].innerText) || e.getAttribute('aria-label') || e.name; }"""


def wait_stable(page):
    last, deadline = None, time.time() + 40
    while time.time() < deadline:
        time.sleep(3)
        cur = page.evaluate("document.documentElement.getAttribute('data-jobfill')")
        if cur and cur == last:
            return cur
        last = cur
    return last


def main():
    backups = {}
    if LEARNED.exists():
        backups[LEARNED] = LEARNED.read_text(encoding="utf-8")
    for _, jid in PAGES.values():
        f = ROOT / "applications" / jid / "answers.json"
        backups[f] = f.read_text(encoding="utf-8") if f.exists() else None
    shutil.rmtree(OUT / "profile", ignore_errors=True)
    ok = True
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(OUT / "profile"), channel="chromium", headless=True,
                args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
                viewport={"width": 1280, "height": 1000})
            for name, (url, jid) in PAGES.items():
                page = ctx.new_page()
                print(f"\n=== {name}")
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                print("summary:", wait_stable(page))
                for lab, checked in page.evaluate(CHECKS):
                    print(f"   [{'x' if checked else ' '}] {lab}")
                lab = page.evaluate(FIND_EMPTY)
                if not lab:
                    print("   (no empty text field to type into)")
                    page.close(); continue
                val = "jobfill learn test"
                page.click("[data-learn-test]")
                page.keyboard.type(val, delay=20)          # trusted key events, like a human
                page.keyboard.press("Tab")
                time.sleep(3)                              # harvest runs 1.5 s after the last touch
                learned = json.loads(LEARNED.read_text(encoding="utf-8")) if LEARNED.exists() else {}
                hit = any(e.get("a") == val for e in learned.get("answers", {}).values())
                fa = ROOT / "applications" / jid / "answers.json"
                hit = hit or (fa.exists() and val in fa.read_text(encoding="utf-8"))
                print(f"   typed into '{(lab or '').strip()[:50]}' -> learned: {hit}")
                ok &= hit
                page.screenshot(path=str(OUT / f"learn_{name}.png"), full_page=True)
                page.close()
            ctx.close()
    finally:
        for f, txt in backups.items():
            if txt is None:
                f.unlink(missing_ok=True)
            else:
                f.write_text(txt, encoding="utf-8")
        if LEARNED not in backups:
            LEARNED.unlink(missing_ok=True)
    print("\nRESULT:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
