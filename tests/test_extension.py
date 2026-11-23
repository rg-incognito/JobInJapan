"""
Live test of the JobFill extension: loads extension/ into Playwright Chromium, opens real application
forms on several ATS platforms, lets the extension fill them, then dumps what got filled. NEVER submits.

  python tests/test_extension.py [name ...]     (needs src/autofill_server.py running)
Screenshots + per-page results go to tests/out/.
"""
import json, shutil, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = str(ROOT / "extension")
OUT = ROOT / "tests" / "out"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = {
    "greenhouse_adyen": "https://job-boards.greenhouse.io/adyen/jobs/7369512",
    "greenhouse_embed_databricks": "https://job-boards.greenhouse.io/embed/job_app?for=databricks&token=8029666002",
    "greenhouse_stripe": "https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=8175656",
    "lever_spotify": "https://jobs.lever.co/spotify/faffd837-edbc-42f8-b4bf-14e1658c18e6/apply",
    "ashby_openai": "https://jobs.ashbyhq.com/openai/c1316397-25bb-4add-9e9d-0e3ea8ba929a/application",
    "ashby_snowflake": "https://jobs.ashbyhq.com/snowflake/6e31e0cb-7821-4dcf-9d69-0afce918bcc4/application",
    "smartrecruiters_wise": "https://jobs.smartrecruiters.com/oneclick-ui/company/Wise/publication/744000155375829?dcr_ci=Wise",
}

DUMP = """() => {
  const out = []; const stack = [document];
  while (stack.length) { const r = stack.pop();
    for (const e of r.querySelectorAll('*')) { if (e.shadowRoot) stack.push(e.shadowRoot);
      if (!/^(INPUT|SELECT|TEXTAREA)$/.test(e.tagName) || e.type === 'hidden') continue;
      const lab = (e.labels && e.labels[0] && e.labels[0].innerText) || e.getAttribute('aria-label') || e.name || e.id;
      let v = e.type === 'file' ? [...(e.files||[])].map(f => f.name).join(',') : (e.type === 'radio' || e.type === 'checkbox') ? (e.checked ? 'CHECKED' : '') : e.value;
      if (e.tagName === 'SELECT') v = e.selectedIndex >= 0 ? e.options[e.selectedIndex].text : '';
      if (e.getAttribute('role') === 'combobox') { const box = e.closest('[class*=select__container],[class*=-container]');
        const sv = box && box.querySelector('[class*=single-value]'); v = sv ? 'combo:' + sv.textContent : (v ? 'typed:' + v : ''); }
      if (v) out.push([(lab||'').trim().slice(0, 60), String(v).slice(0, 70)]);
    } }
  return { summary: document.documentElement.getAttribute('data-jobfill'), values: out };
}"""


def main(names):
    shutil.rmtree(OUT / "profile", ignore_errors=True)   # fresh browser profile: no saved drafts
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(OUT / "profile"), channel="chromium", headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
            viewport={"width": 1280, "height": 1000},
        )
        results = {}
        for name in names:
            url = PAGES[name]
            page = ctx.new_page()
            print(f"\n=== {name}  {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                # Ashby / Greenhouse sometimes need the Apply tab or button
                time.sleep(4)
                for sel in ["text=Apply for this job", "button:has-text('Apply')", "a:has-text('Apply')"]:
                    pass
                deadline = time.time() + 40
                last = None
                while time.time() < deadline:   # wait until the extension's summary is stable
                    time.sleep(3)
                    frames = [f for f in page.frames]
                    sums = []
                    for fr in frames:
                        try:
                            sums.append(fr.evaluate("document.documentElement.getAttribute('data-jobfill')"))
                        except Exception:
                            pass
                    cur = [s for s in sums if s]
                    if cur and cur == last:
                        break
                    last = cur
                data = []
                for fr in page.frames:
                    try:
                        d = fr.evaluate(DUMP)
                        if d["summary"] or d["values"]:
                            data.append({"frame": fr.url[:90], **d})
                    except Exception:
                        pass
                results[name] = data
                for d in data:
                    print("frame:", d["frame"], "summary:", d["summary"])
                    for lab, v in d["values"]:
                        print(f"   {lab:60} = {v}")
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            except Exception as e:
                print("ERROR", e)
                results[name] = {"error": str(e)}
            finally:
                page.close()
        (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        ctx.close()


if __name__ == "__main__":
    main(sys.argv[1:] or list(PAGES))
