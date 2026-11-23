"""
Rohit's one-click submit queue. The autopilot fills and verifies forms (0 open questions) but job sites block
automated submits with a CAPTCHA or an emailed code, so the final click is Rohit's.

  python src/submit_queue.py            list the queue
  python src/submit_queue.py open 10    open the next 10 application forms in Chrome (JobFill fills each in ~20 s;
                                        check the panel, click Submit, solve a CAPTCHA if one appears)
  python src/submit_queue.py auto 8     used by the scheduled run: opens up to 8 queued forms in Rohit's Chrome and
                                        JobFill submits them itself (ctx.autosubmit). Each job is tried at most twice;
                                        a tab with a CAPTCHA / emailed code stays open for Rohit.

When the confirmation page appears, JobFill tells the local server and the job is marked `applied` on its own.
"""
import csv, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from autopilot import apply_url, jload, jsave, STATE_F  # noqa: E402

CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]


def queue():
    state = jload(STATE_F, {})
    rows = {r["job_id"]: r for r in csv.DictReader(open(ROOT / "data" / "jobs.csv", encoding="utf-8"))}
    out = [rows[j] for j, v in state.items() if v.get("to_submit") and j in rows and rows[j]["status"] == "ready"]
    out.sort(key=lambda r: (r["sponsorship"] != "yes", r["company"]))
    return out


def main():
    q = queue()
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
        state = jload(STATE_F, {})
        todo = [r for r in q if state.get(r["job_id"], {}).get("chrome_tries", 0) < 2][:n]
        exe = next((c for c in CHROME if Path(c).exists()), None)
        if not exe or not todo:
            print(f"auto-submit: {len(todo)} to open" + ("" if exe else ", Chrome not found")); return
        for r in todo:
            state = jload(STATE_F, {})   # re-read: the server marks earlier tabs applied meanwhile
            state.setdefault(r["job_id"], {})["chrome_tries"] = state.get(r["job_id"], {}).get("chrome_tries", 0) + 1
            jsave(STATE_F, state)
            print(f"auto-submit: {r['company']} | {r['title'][:60]}")
            subprocess.Popen([exe, apply_url(r)])
            time.sleep(25)          # one form at a time keeps fills and uploads reliable
        return
    if len(sys.argv) > 1 and sys.argv[1] == "open":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        exe = next((c for c in CHROME if Path(c).exists()), None)
        for r in q[:n]:
            url = apply_url(r)
            print(f"opening {r['company']} | {r['title'][:60]}")
            if exe:
                subprocess.Popen([exe, url])
            else:
                import webbrowser; webbrowser.open(url)
            time.sleep(1.5)
        print(f"\n{min(n, len(q))} opened, {max(0, len(q) - n)} left in the queue.")
        return
    print(f"{len(q)} applications ready for your Submit click:\n")
    for i, r in enumerate(q, 1):
        print(f"{i:>3}. {r['company'][:18]:18} {r['title'][:55]:55} {r['country'][:10]:10} visa:{r['sponsorship']}")
    print("\nOpen the next 10:  python src/submit_queue.py open 10")


if __name__ == "__main__":
    main()
