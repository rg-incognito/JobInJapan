"""
Live test (headless, NEVER submits): Rohit corrects an autofilled dropdown on one form and the next form
uses his answer. Changes "Veteran Status" on the Monzo form from the default decline to
"I am not a protected veteran" with real mouse clicks, then opens the form again in a fresh tab and checks its veteran
question. Restores data/learned.json and the job answers.json files afterwards.

  python tests/test_learn_correction.py     (needs src/autofill_server.py running)
"""
import json, shutil, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = str(ROOT / "extension")
OUT = ROOT / "tests" / "out"
LEARNED = ROOT / "data" / "learned.json"
FIRST = "https://job-boards.greenhouse.io/monzo/jobs/6635595"
SECOND = FIRST   # fresh tab = fresh extension instance: the value can only come from the learned override
JOBS = ["gh-monzo-6635595"]

COMBO_VALUE = """(lab) => { const l = [...document.querySelectorAll('label')].find(x => x.innerText.trim().toLowerCase().includes(lab));
  if (!l) return null; const i = document.getElementById(l.htmlFor); if (!i) return null;
  const box = (i.closest('[class*=control]') || i).parentElement;
  const sv = box.querySelector('[class*=single-value]'); i.scrollIntoView({block: 'center'});
  return { id: i.id, value: sv ? sv.textContent : '' }; }"""


def wait_stable(page):
    """Wait until the veteran dropdown has a value and the page stops changing (React hydration can wipe
    the data-jobfill marker, so values are watched instead)."""
    last, deadline = None, time.time() + 70
    while time.time() < deadline:
        time.sleep(4)
        cur = page.evaluate(COMBO_VALUE, "veteran")
        cur = cur and cur["value"]
        if cur and cur == last:
            return cur
        last = cur
    return last


def main():
    backups = {LEARNED: LEARNED.read_text(encoding="utf-8") if LEARNED.exists() else None}
    for j in JOBS:
        f = ROOT / "applications" / j / "answers.json"
        backups[f] = f.read_text(encoding="utf-8") if f.exists() else None
    shutil.rmtree(OUT / "profile", ignore_errors=True)
    ok = False
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(OUT / "profile"), channel="chromium", headless=True,
                args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
                viewport={"width": 1280, "height": 1000})
            page = ctx.new_page()
            page.on("console", lambda m: print("   console:", m.text[:400]) if "JobFill" in m.text else None)
            page.goto(FIRST, wait_until="domcontentloaded", timeout=45000)
            print("first form:", wait_stable(page))
            time.sleep(10)
            print("first form settled:", page.evaluate("document.documentElement.getAttribute('data-jobfill')"))
            before = page.evaluate(COMBO_VALUE, "veteran")
            print("  veteran before:", before)
            # human correction: open the dropdown and click the option
            page.click(f"#{before['id']}")
            page.keyboard.type("not a protected", delay=40)
            time.sleep(1)
            page.keyboard.press("Enter")
            page.keyboard.press("Tab")
            time.sleep(9)
            print("  veteran after human pick:", page.evaluate(COMBO_VALUE, "veteran"))
            learned = json.loads(LEARNED.read_text(encoding="utf-8")) if LEARNED.exists() else {}
            print("  overrides:", json.dumps(learned.get("overrides", {})))
            print("  debug:", json.dumps(page.evaluate("""() => new Promise(r => { addEventListener('message', e => { if (e.data && e.data.jobfillDebug) r(e.data.jobfillDebug); }); postMessage({jobfill:'debug'}, '*'); setTimeout(() => r('no answer'), 3000); })"""))[:1500])
            # refill must not undo the correction
            page.evaluate("window.postMessage({jobfill:'refill'}, '*')")
            time.sleep(8)
            kept = page.evaluate(COMBO_VALUE, "veteran")
            print("  after Refill:", kept)
            page.close()

            page = ctx.new_page()
            page.goto(SECOND, wait_until="domcontentloaded", timeout=45000)
            print("second form:", wait_stable(page))
            got = page.evaluate(COMBO_VALUE, "veteran")
            print("  veteran on second form:", got)
            page.screenshot(path=str(OUT / "learn_correction_second.png"), full_page=True)
            ok = bool(got and "not a protected veteran" in got["value"].lower()
                      and "not a protected veteran" in kept["value"].lower())
            ctx.close()
    finally:
        for f, txt in backups.items():
            if txt is None:
                f.unlink(missing_ok=True)
            else:
                f.write_text(txt, encoding="utf-8")
    print("\nRESULT:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
