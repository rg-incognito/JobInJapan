"""
Autopilot: find -> tailor -> fill -> submit, with no Claude tokens in the normal path.
Runs every 2 hours from Windows Task Scheduler (tools/autopilot.cmd). Rohit gave standing approval (2026-11-02)
to submit forms that are completely and truthfully filled.

  python src/autopilot.py                 full cycle (fetch, pick, tailor, fill, submit)
  python src/autopilot.py --dry-run       fill but never click Submit
  python src/autopilot.py --job <id>      only this job (still respects --dry-run)
  python src/autopilot.py --no-fetch --limit 3

Per job:
  1. Pick eligible jobs: Greenhouse/Ashby/Lever, mid level, <= max_required_years, sponsorship not "no",
     no Japanese/German fluency requirement, salary (when published) >= the 30 LPA floor, and per-company caps
     (default 2 per 30 days, OpenAI 5 per 180 days), 1 per company per run.
  2. app.py prepare + src/auto_tailor.py (truthful rule-based tailoring + template cover letter).
     ATS < min_score -> skipped.
  3. Open the form in a dedicated Chromium profile with the JobFill extension, wait for it to finish.
  4. needs > 0  -> questions go to data/needs_queue.json (answered by one short `claude -p` run in the .cmd),
                   job stays `ready` and is retried next cycle (max 3 attempts).
     CAPTCHA    -> left `ready` with a note for Rohit; never bypassed, never retried.
     otherwise  -> clicks Submit, waits for the confirmation page, marks `applied`, logs data/applied_log.csv.
Screenshots of every outcome: data/logs/shots/.
"""
import csv, json, re, subprocess, sys, time, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ats_score import LANG_REQ  # noqa: E402

PY = sys.executable
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
AP = {"per_run": 5, "per_day": 50, "per_company_days": 30, "per_company_max": 2, "min_score": 80, "submit": False, "max_attempts": 3,
      "company_caps": {"OpenAI": [180, 5]}, "headless": False, **CONFIG.get("autopilot", {})}
MAXY = CONFIG.get("max_required_years", 4)
FLOOR_LPA = CONFIG.get("candidate", {}).get("hard_floor_inr_lpa", 30)
EXT = str(ROOT / "extension")
PROFILE_DIR = ROOT / "data" / "autopilot_profile"
STATE_F = ROOT / "data" / "autopilot_state.json"
QUEUE_F = ROOT / "data" / "needs_queue.json"
LEDGER_F = ROOT / "data" / "applied_log.csv"
LOG_DIR = ROOT / "data" / "logs"
SHOTS = LOG_DIR / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
LOG_F = LOG_DIR / f"autopilot-{date.today():%Y%m%d}.log"

# rough INR per unit, only used to drop postings whose *published* maximum is below the floor
INR = {"EUR": 100, "€": 100, "GBP": 115, "£": 115, "USD": 88, "$": 88, "PLN": 23, "ZŁ": 23, "SGD": 68, "S$": 68,
       "JPY": 0.58, "¥": 0.58, "AED": 24, "CHF": 105, "SEK": 9, "DKK": 13.4, "NOK": 8.5, "CZK": 4}

SUCCESS_RX = re.compile(r"thank(s| you)[^.\n]{0,40}(appl|interest|submitting)|application (has been |was )?(successfully )?(submitted|received|sent)"
                        r"|we('ve| have) received your application|successfully submitted|your application is (complete|on its way)", re.I)
# Greenhouse sometimes emails a code "to confirm you're a human": a human check, left for Rohit like a CAPTCHA
VERIFY_RX = re.compile(r"verification code (was|has been) sent|enter the \d+.character code|confirm you.re a human|security code", re.I)
NET_RX = re.compile(r"ERR_INTERNET_DISCONNECTED|ERR_NETWORK_ACCESS_DENIED|ERR_NAME_NOT_RESOLVED|ERR_NETWORK_CHANGED|ERR_CONNECTION_(RESET|REFUSED|TIMED_OUT)|ERR_TIMED_OUT")


class NetworkDown(Exception):
    pass


CLOSED_RX = re.compile(r"no longer (accepting|available|open)|job (is )?not found|position has been filled|page (you.re looking for )?(was )?not found|this job (has )?(closed|expired)", re.I)


def log(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG_F, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def jload(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def jsave(p, obj):
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def jobs():
    return list(csv.DictReader(open(ROOT / "data" / "jobs.csv", encoding="utf-8")))


def set_status(job_id, st, note):
    subprocess.run([PY, str(ROOT / "src" / "app.py"), "status", job_id, st, note], cwd=ROOT, check=True)


# ---------------- ledger of submitted applications ----------------
def ledger():
    if not LEDGER_F.exists():
        rows = []
        for r in jobs():
            if r["status"] in ("applied", "interview", "offer", "rejected"):
                m = re.search(r"(\d{4}-\d{2}-\d{2})", r.get("notes", ""))
                rows.append({"date": m.group(1) if m else str(date.today()), "job_id": r["job_id"], "company": r["company"], "how": "before autopilot"})
        with open(LEDGER_F, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date", "job_id", "company", "how"]); w.writeheader(); w.writerows(rows)
    return list(csv.DictReader(open(LEDGER_F, encoding="utf-8")))


def ledger_add(job, how):
    with open(LEDGER_F, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([str(date.today()), job["job_id"], job["company"], how])


# ---------------- selection ----------------
def salary_ok(s):
    if not s or not s.strip():
        return True
    up = s.upper().replace(",", "")
    cur = next((c for c in sorted(INR, key=len, reverse=True) if c in up), None)
    nums = [float(n) * (1000 if k else 1) for n, k in re.findall(r"(\d+(?:\.\d+)?)\s*(K)?\b", up)]
    nums = [n for n in nums if n >= 1000]
    if not cur or not nums:
        return True
    return max(nums) * INR[cur] / 1e5 >= FLOOR_LPA


def company_capped(company, led, today):
    days, mx = AP["company_caps"].get(company, [AP["per_company_days"], AP["per_company_max"]])
    since = today - timedelta(days=days)
    n = sum(1 for r in led if r["company"].lower() == company.lower() and date.fromisoformat(r["date"]) >= since)
    return n >= mx


def eligible(only=None):
    led, state, today = ledger(), jload(STATE_F, {}), date.today()
    out, seen_company = [], set()
    rows_by_id = {r["job_id"]: r for r in jobs()}
    # jobs waiting in the submit queue count against the company caps like submitted ones
    led = led + [{"company": rows_by_id[j]["company"], "date": v.get("last", str(today))[:10]}
                 for j, v in state.items() if v.get("to_submit") and j in rows_by_id]
    rank = {"yes": 0, "unknown": 1}
    pri = CONFIG.get("country_priority", [])
    rows = jobs()
    if only:
        return [r for r in rows if r["job_id"] == only]
    rows.sort(key=lambda r: (rank.get(r["sponsorship"], 2), r["status"] != "ready",
                             pri.index(r["country"]) if r["country"] in pri else len(pri), r["tier"], -float(r["base_ats_score"] or 0)))
    for r in rows:
        st = state.get(r["job_id"], {})
        if r["status"] not in ("new", "ready") or r["sponsorship"] == "no" or r["level"] != "mid":
            continue
        if r["job_id"][:3] not in ("gh-", "ab-", "lv-"):
            continue
        if r.get("req_years") and int(r["req_years"]) > MAXY:
            continue
        if st.get("blocked") or st.get("attempts", 0) >= AP["max_attempts"]:
            continue
        if st.get("waiting_answers") and QUEUE_F.exists() and r["job_id"] in jload(QUEUE_F, {}):
            continue   # questions not answered yet
        if not salary_ok(r.get("salary", "")):
            continue
        jd_p = ROOT / "data" / "jd" / f"{r['job_id']}.txt"
        jd = jd_p.read_text(encoding="utf-8") if jd_p.exists() else ""
        if any(rx.search(jd) for rx in LANG_REQ.values()):
            continue
        if r["company"].lower() in seen_company or company_capped(r["company"], led, today):
            continue
        seen_company.add(r["company"].lower())
        out.append(r)
    return out


def apply_url(r):
    jid = r["job_id"]
    if jid.startswith("gh-"):
        slug, num = jid[3:].rsplit("-", 1)
        # the embed form works even when the board redirects to the company's own careers site (Helsing, Dropbox...)
        return f"https://job-boards.greenhouse.io/embed/job_app?for={slug}&token={num}"
    if jid.startswith("ab-"):
        return r["url"].rstrip("/") + "/application"
    if jid.startswith("lv-"):
        return r["url"].rstrip("/") + "/apply"
    return r["url"]


# ---------------- prepare ----------------
def prepare(r):
    d = ROOT / "applications" / r["job_id"]
    has_pdf = d.exists() and any(d.glob("Rohit_Gande_*.pdf"))
    if r["status"] == "ready" and has_pdf:
        sc = jload(d / "score.json", {}).get("score", 0)
        if not (d / "Rohit_Gande_Cover_Letter.txt").exists() and (d / "cover_letter.md").exists():
            (d / "Rohit_Gande_Cover_Letter.txt").write_text((d / "cover_letter.md").read_text(encoding="utf-8"), encoding="utf-8")
        return sc
    subprocess.run([PY, str(ROOT / "src" / "app.py"), "prepare", r["job_id"]], cwd=ROOT, check=True, capture_output=True)
    res = subprocess.run([PY, str(ROOT / "src" / "auto_tailor.py"), r["job_id"]], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise RuntimeError("tailor failed: " + (res.stderr or res.stdout)[-300:])
    info = json.loads(res.stdout.strip().splitlines()[-1])
    log(f"   tailored ({info['family']}, {info['stage']}): ATS {info['score']}, missing {', '.join(info['missing'][:6]) or '-'}")
    return info["score"]


# ---------------- browser ----------------
def server_up():
    try:
        req = urllib.request.Request("http://127.0.0.1:8765/health", headers={"Origin": "chrome-extension://autopilot"})
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def ensure_server():
    if server_up():
        return
    pyw = Path(PY).with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else PY), str(ROOT / "src" / "autofill_server.py")], cwd=ROOT,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(20):
        time.sleep(0.5)
        if server_up():
            return
    raise RuntimeError("autofill server did not start")


def summary(page):
    tot = {"filled": 0, "needs": 0, "consent": 0, "acked": 0}
    seen = False
    for fr in page.frames:
        try:
            s = fr.evaluate("document.documentElement.getAttribute('data-jobfill')")
        except Exception:
            continue
        if s:
            seen = True
            for k, v in json.loads(s).items():
                tot[k] = tot.get(k, 0) + v
    return tot if seen else None


def wait_filled(page, timeout=150):
    last, stable, t0 = None, 0, time.time()
    while time.time() - t0 < timeout:
        time.sleep(4)
        cur = summary(page)
        if cur and cur == last and cur["filled"] > 0:
            stable += 1
            if stable >= 2:
                return cur
        else:
            stable = 0
        last = cur
    return last


def page_text(page):
    out = []
    for fr in page.frames:
        try:
            out.append(fr.evaluate("document.body ? document.body.innerText : ''"))
        except Exception:
            pass
    return "\n".join(out)


def captcha_visible(page):
    for fr in page.frames:
        u = fr.url or ""
        if ("recaptcha" in u and "bframe" in u) or ("hcaptcha" in u and "challenge" in u) or "challenges.cloudflare" in u:
            try:
                el = fr.frame_element()
                box = el.bounding_box()
                if box and box["width"] > 50 and box["height"] > 50 and el.is_visible():
                    return True
            except Exception:
                pass
    return False


def submit_button(page):
    for fr in [page.main_frame] + [f for f in page.frames if f != page.main_frame]:
        for sel in ["#btn-submit", "button[type=submit]:has-text('Submit')", "button:has-text('Submit application')",
                    "button:has-text('Submit Application')", "input[type=submit][value*='Submit' i]", "button:has-text('Submit')"]:
            try:
                loc = fr.locator(sel)
                for i in range(loc.count()):
                    b = loc.nth(i)
                    if b.is_visible() and b.is_enabled():
                        return b
            except Exception:
                continue
    return None


def validation_errors(page):
    js = """() => [...document.querySelectorAll('[aria-invalid=true], .error, .field-error, [class*=error-message], [class*=_error_], .helper-text--error')]
      .filter(e => e.offsetParent && (e.innerText || '').trim()).map(e => e.innerText.trim().slice(0, 100)).slice(0, 5)"""
    out = []
    for fr in page.frames:
        try:
            out += fr.evaluate(js)
        except Exception:
            pass
    return out


def checked(page):
    js = """() => [...document.querySelectorAll('input[type=radio]:checked, input[type=checkbox]:checked')].map(e =>
      ((e.labels && e.labels[0] && e.labels[0].innerText) || e.value || '').trim().slice(0, 40))"""
    out = []
    for fr in page.frames:
        try:
            out += fr.evaluate(js)
        except Exception:
            pass
    return out


def shot(page, job_id, tag):
    try:
        page.screenshot(path=str(SHOTS / f"{date.today():%Y%m%d}-{job_id[:40]}-{tag}.png"), full_page=True)
    except Exception:
        pass


def queue_needs(r):
    rep = jload(ROOT / "applications" / r["job_id"] / "form_report.json", {})
    needs = [n for fr in rep.get("frames", {}).values() for n in fr.get("needs", [])]
    q = jload(QUEUE_F, {})
    q[r["job_id"]] = {"company": r["company"], "title": r["title"], "url": apply_url(r),
                      "questions": [{k: n.get(k) for k in ("label", "kind", "options", "required") if n.get(k) is not None} for n in needs]}
    jsave(QUEUE_F, q)
    return [n.get("label", "")[:70] for n in needs]


def live_search_fix(page, r):
    """Location dropdowns that search a places API ignore script-set text. Type the city with real keystrokes
    and take the first suggestion that names Pune, then let the extension re-report."""
    rep = jload(ROOT / "applications" / r["job_id"] / "form_report.json", {})
    todo = [n["label"] for fr in rep.get("frames", {}).values() for n in fr.get("needs", [])
            if n.get("kind") == "combo" and n.get("key") in ("location", "city")]
    fixed = 0
    for label in todo:
        for fr in page.frames:
            try:
                inp = fr.get_by_label(label, exact=True)
                if inp.count() != 1:
                    continue
                inp.click()
                inp.press_sequentially("Pune", delay=90)
                opt = fr.locator("[role=option]", has_text=re.compile("Pune", re.I)).first
                opt.wait_for(state="visible", timeout=6000)
                opt.click()
                fixed += 1
                break
            except Exception:
                continue
    if fixed:
        page.evaluate("window.postMessage({jobfill: 'refill'}, '*')")
        time.sleep(6)
    return fixed


def run_job(ctx, r, dry):
    url = apply_url(r)
    page = ctx.new_page()
    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            if NET_RX.search(str(e)):
                raise NetworkDown(str(e)[:120])
            raise
        time.sleep(3)
        txt = page_text(page)
        if CLOSED_RX.search(txt[:3000]) or "/jobs/" not in page.url and r["job_id"].startswith("gh-") and "error" in page.url:
            return "closed", ""
        s = wait_filled(page)
        if not s:
            shot(page, r["job_id"], "nofill")
            return "error", "extension did not fill (no form found?)"
        time.sleep(4)   # let the last report reach the server
        if s["needs"] > 0 and live_search_fix(page, r):
            s = wait_filled(page, 60) or s
            time.sleep(3)
        if s["needs"] > 0:
            qs = queue_needs(r)
            shot(page, r["job_id"], "needs")
            return "needs", "; ".join(qs)
        rep = jload(ROOT / "applications" / r["job_id"] / "form_report.json", {})
        req_consent = [c.get("label", "")[:80] for fr in rep.get("frames", {}).values() for c in fr.get("consent", []) if c.get("required")]
        if req_consent:
            shot(page, r["job_id"], "consent")
            return "consent", "; ".join(req_consent)
        if captcha_visible(page):
            shot(page, r["job_id"], "captcha")
            return "captcha", ""
        if dry:
            shot(page, r["job_id"], "dry")
            return "dry", json.dumps(s) + " | checked: " + "; ".join(checked(page))
        btn = submit_button(page)
        if not btn:
            shot(page, r["job_id"], "nobutton")
            return "error", "submit button not found"
        start_url = page.url
        for fr in page.frames:   # the JobFill panel is fixed bottom-right and can sit on top of Submit
            try:
                fr.evaluate("() => { const h = document.getElementById('__jobfill_panel'); if (h) h.style.display = 'none'; }")
            except Exception:
                pass
        btn.scroll_into_view_if_needed()
        try:
            btn.click(timeout=10000)
        except Exception:
            btn.dispatch_event("click")
        t0 = time.time()
        while time.time() - t0 < 45:
            time.sleep(3)
            if captcha_visible(page):
                shot(page, r["job_id"], "captcha")
                return "captcha", "after submit click"
            txt = page_text(page)
            if VERIFY_RX.search(txt) and not SUCCESS_RX.search(txt):
                shot(page, r["job_id"], "verify")
                return "captcha", "emailed security code required"
            if SUCCESS_RX.search(txt) or (page.url != start_url and re.search(r"confirm|thank|success", page.url, re.I)):
                shot(page, r["job_id"], "applied")
                return "applied", ""
        errs = validation_errors(page)
        shot(page, r["job_id"], "failed")
        return "failed", "; ".join(errs) or "no confirmation seen"
    finally:
        page.close()


def main():
    args = sys.argv[1:]
    # Ashby shows a CAPTCHA and Greenhouse emails a security code to automated submits (seen on every try,
    # 2026-11-02), so by default the autopilot fills + verifies and queues the job for Rohit's one-click submit
    # (python src/submit_queue.py). "--submit" or config autopilot.submit=true still tries to submit.
    dry = "--dry-run" in args or ("--submit" not in args and not AP["submit"])
    only = args[args.index("--job") + 1] if "--job" in args else None
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else AP["per_run"]
    log(f"=== autopilot start (fill-only={dry}, limit={limit})")

    if "--no-fetch" not in args and not only:
        r = subprocess.run([PY, str(ROOT / "src" / "fetch_jobs.py")], cwd=ROOT, capture_output=True, text=True, timeout=900)
        log("   fetch: " + (r.stdout.strip().splitlines() or ["?"])[-1])

    led = ledger()
    today_n = sum(1 for x in led if x["date"] == str(date.today()) and x["how"].startswith("autopilot")) + sum(
        1 for v in jload(STATE_F, {}).values() if v.get("to_submit") and v.get("last", "").startswith(str(date.today())))
    if today_n >= AP["per_day"] and not only:
        log(f"   daily cap reached ({today_n})"); return
    limit = min(limit, AP["per_day"] - today_n)
    cands = eligible(only)
    log(f"   {len(cands)} eligible jobs")
    if not cands:
        return
    ensure_server()

    from playwright.sync_api import sync_playwright
    state = jload(STATE_F, {})
    done = {"applied": [], "needs": [], "captcha": [], "consent": [], "skipped": [], "failed": [], "closed": [], "dry": []}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), channel="chromium", headless=AP["headless"],
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"], viewport={"width": 1280, "height": 900})
        tried = 0
        for r in cands:
            if len(done["applied"]) + len(done["dry"]) >= limit or tried >= limit * 3:
                break
            tried += 1
            jid = r["job_id"]
            log(f"-> {r['company']} | {r['title'][:60]} | {r['country']} [{jid}]")
            st = state.setdefault(jid, {"attempts": 0})
            try:
                sc = prepare(r)
                if sc < AP["min_score"]:
                    set_status(jid, "skipped", f"autopilot: ATS {sc} < {AP['min_score']} after auto-tailoring")
                    done["skipped"].append(jid); log(f"   skipped (ATS {sc})"); continue
                if r["status"] == "new":
                    set_status(jid, "ready", f"autopilot tailored ATS {sc}")
                st["attempts"] += 1
                res, info = run_job(ctx, r, dry)
            except NetworkDown as e:
                st["attempts"] -= 1
                log(f"   network down ({e}), stopping this run")
                jsave(STATE_F, state)
                break
            except Exception as e:
                res, info = "failed", str(e)[:300]
            st["last"], st["result"] = datetime.now().isoformat(timespec="minutes"), res
            log(f"   {res}{': ' + info if info else ''}")
            if res == "applied":
                set_status(jid, "applied", f"autopilot submitted {date.today()}")
                ledger_add(r, "autopilot"); st.pop("waiting_answers", None)
                q = jload(QUEUE_F, {}); q.pop(jid, None); jsave(QUEUE_F, q)
            elif res == "needs":
                st["waiting_answers"] = True
                set_status(jid, "ready", f"autopilot: needs answers ({info[:120]})")
            elif res == "consent":
                st["blocked"] = True
                set_status(jid, "ready", f"autopilot: required consent not auto-accepted ({info[:100]}), please review")
            elif res == "captcha":
                st["blocked"] = True; st["to_submit"] = True
                set_status(jid, "ready", "autopilot: filled; human check on submit -> in submit queue")
            elif res == "dry":
                st["blocked"] = True; st["to_submit"] = True
                set_status(jid, "ready", "autopilot: filled and verified (0 open questions) -> in submit queue")
            elif res == "closed":
                st["blocked"] = True
                set_status(jid, "closed", "autopilot: posting closed")
            elif res == "failed" or res == "error":
                set_status(jid, "ready", f"autopilot: {res} ({info[:150]})")
            done.setdefault(res if res in done else "failed", []).append(jid)
            jsave(STATE_F, state)
        ctx.close()

    line = (f"- {datetime.now():%Y-%m-%d %H:%M} autopilot{' (fill-only)' if dry else ''}: applied {len(done['applied'])}, "
            f"needs answers {len(done['needs'])}, captcha {len(done['captcha'])}, failed {len(done['failed'])}, "
            f"skipped {len(done['skipped'])}, closed {len(done['closed'])}"
            + (f" | applied: {', '.join(done['applied'])}" if done["applied"] else "")
            + (f" | queued for Rohit's submit: {len(done['dry'])}" if done["dry"] else ""))
    with open(ROOT / "data" / "run_log.md", "a", encoding="utf-8") as f:
        f.write(line + "\n")
    log(line)


if __name__ == "__main__":
    main()
