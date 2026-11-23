"""
JobFill local server - feeds the Chrome extension (extension/) with Rohit's profile, the answer bank,
and the tailored resume / cover letter for whichever job the open application page belongs to.

  python src/autofill_server.py            # serves on http://127.0.0.1:8765 (localhost only)

Endpoints (only reachable from the extension: requests carrying a web-page Origin are refused):
  GET  /health                 -> {"ok": true}
  POST /context {"urls": [...]} -> profile, rules, matched job, resume + cover letter (base64)
  POST /report  {"job_id", "url", "report"} -> writes applications/<id>/form_report.json
                                  (or data/form_reports/<host>.json when no job matched)
  POST /applied {"job_id"} -> confirmation seen after Rohit's Submit: status applied + data/applied_log.csv
  POST /learn   {"job_id", "url", "items": [{label, kind, value}]} -> answers Rohit typed/picked himself.
                Short / choice answers -> data/learned.json (reused on every form, exact question match).
                Long free text or questions naming the company -> applications/<id>/answers.json only.
"""
import base64, csv, json, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
PORT = 8765
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

COUNTRY_SALARY_KEY = {"United Kingdom": "UK/London", "UK": "UK/London"}
CITY_COUNTRY = [
    (r"berlin|munich|münchen|hamburg|frankfurt|cologne|köln|stuttgart|germany|deutschland", "Germany"),
    (r"amsterdam|rotterdam|utrecht|eindhoven|the hague|netherlands", "Netherlands"),
    (r"dublin|cork|ireland", "Ireland"),
    (r"london|manchester|edinburgh|cambridge|united kingdom|\buk\b", "UK"),
    (r"warsaw|warszawa|krakow|kraków|wroclaw|wrocław|gdansk|poland", "Poland"),
    (r"tokyo|osaka|fukuoka|japan", "Japan"),
    (r"helsinki|espoo|finland", "Finland"),
    (r"singapore", "Singapore"),
    (r"pune|mumbai|bangalore|bengaluru|hyderabad|chennai|delhi|noida|gurgaon|gurugram|kolkata|ahmedabad|india|naukri", "India"),
]


def load_jobs():
    p = ROOT / "data" / "jobs.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def match_job(urls):
    """Find the job whose ATS id appears in one of the page URLs (top tab URL or iframe URL)."""
    urls = [u for u in urls if u]
    best = None
    for job in load_jobs():
        parts = job["job_id"].split("-", 2)
        if len(parts) < 3:
            continue
        tail = parts[2]
        if len(tail) < 6:
            continue
        rx = re.compile(r"(?<![\w-])" + re.escape(tail) + r"(?![\w])", re.I)
        if any(rx.search(u) for u in urls):
            has_app = (ROOT / "applications" / job["job_id"]).exists()
            if best is None or (has_app and not best[1]):
                best = (job, has_app)
    if best:
        return best[0]
    # fall back to application folders (jobs.csv may have been refreshed without the job)
    for jf in (ROOT / "applications").glob("*/job.json"):
        job = json.loads(jf.read_text(encoding="utf-8"))
        if any(job.get("url") and job["url"].split("?")[0].rstrip("/") in u for u in urls):
            return job
    return None


def b64(path: Path):
    return base64.b64encode(path.read_bytes()).decode()


def build_context(urls, page_text=""):
    profile = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
    rules = overridden_rules(json.loads((ROOT / "data" / "answers.json").read_text(encoding="utf-8"))["rules"])
    job = match_job(urls)
    ctx = {"profile": profile, "rules": rules, "job": job, "app_rules": [], "resume": None, "cover": None,
           "learned_rules": learned_rules()}

    country = (job or {}).get("country") or ""
    if not country:
        hay = " ".join(urls) + " " + page_text[:4000]
        for rx, c in CITY_COUNTRY:
            if re.search(rx, hay, re.I):
                country = c
                break
    ctx["country"] = country
    sal = profile.get("salary_expectations_by_location", {})
    ask = sal.get(COUNTRY_SALARY_KEY.get(country, country), "")
    ctx["salary_ask"] = ask
    ctx["why_country"] = profile.get("why_country_scripts", {}).get(country, "")

    # Rohit (2026-11-02): "i really dont want to submit them on own". Jobs the autopilot verified (to_submit) are
    # submitted by JobFill itself in his Chrome. If a CAPTCHA / emailed code appears, the tab stays open for him.
    ctx["autosubmit"] = False
    if job:
        try:
            st = json.loads((ROOT / "data" / "autopilot_state.json").read_text(encoding="utf-8")).get(job["job_id"], {})
            cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("autopilot", {})
            ctx["autosubmit"] = bool(st.get("to_submit")) and cfg.get("chrome_submit", True) and job.get("status") == "ready"
        except Exception:
            pass

    app_dir = ROOT / "applications" / job["job_id"] if job else None
    if app_dir and app_dir.exists():
        pdfs = [p for p in app_dir.glob("Rohit_Gande_*.pdf") if "cover" not in p.name.lower()]
        if pdfs:
            ctx["resume"] = {"name": pdfs[0].name, "type": "application/pdf", "b64": b64(pdfs[0])}
        cl = app_dir / "Rohit_Gande_Cover_Letter.txt"
        if cl.exists():
            ctx["cover"] = {"name": cl.name, "type": "text/plain", "b64": b64(cl),
                            "text": cl.read_text(encoding="utf-8")}
        ans = app_dir / "answers.json"
        if ans.exists():
            data = json.loads(ans.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "rules" not in data:   # simple {"question text": "answer"} map
                data = [{"q": re.escape(k.lower().strip()[:80]), "a": v} for k, v in data.items()]
            elif isinstance(data, dict):
                data = data["rules"]
            ctx["app_rules"] = data
    if ctx["resume"] is None:
        m = ROOT / "resume" / "master.pdf"
        if m.exists():
            ctx["resume"] = {"name": "Rohit_Gande_Resume.pdf", "type": "application/pdf", "b64": b64(m)}
    return ctx


def save_report(body):
    job_id = body.get("job_id")
    report = body.get("report") or {}
    report["url"] = body.get("url")
    report["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if job_id and (ROOT / "applications" / job_id).exists():
        out = ROOT / "applications" / job_id / "form_report.json"
    else:
        host = re.sub(r"[^\w.-]", "_", urlparse(body.get("url") or "").netloc or "unknown")
        out = ROOT / "data" / "form_reports" / f"{host}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
    # merge per frame: Greenhouse embeds etc. report from several frames
    old = {}
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    frames = old.get("frames", {}) if old.get("url_top") == body.get("url_top") else {}
    frames[body.get("frame_url") or "top"] = report
    merged = {"job_id": job_id, "url_top": body.get("url_top"), "saved_at": report["saved_at"], "frames": frames}
    needs = [f for fr in frames.values() for f in fr.get("needs", [])]
    consent = [f for fr in frames.values() for f in fr.get("consent", [])]
    merged["summary"] = {"filled": sum(len(fr.get("filled", [])) for fr in frames.values()),
                         "needs_input": len(needs), "consent_for_rohit": len(consent)}
    out.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out.relative_to(ROOT))


LEARNED = ROOT / "data" / "learned.json"
JOB_ID_RX = re.compile(r"^[\w.-]{3,120}$")
LONG_ANSWER = 150          # longer free text is usually specific to one company / role


def norm_q(s):
    return re.sub(r"\s+", " ", str(s or "").replace("*", "")).strip().lower()


def load_learned():
    try:
        return json.loads(LEARNED.read_text(encoding="utf-8"))
    except Exception:
        return {"_note": "Answers Rohit typed or picked himself on application forms (learned by JobFill). "
                         "Edit or delete entries freely.", "answers": {}}


def synonyms(v):
    """Extra option patterns so an answer picked on one form matches the wording on other forms."""
    l = v.lower()
    out = []
    if re.fullmatch(r"(cis ?(gender)? ?)?(male|man)", l):
        out.append(r"^(cis ?(gender)? ?)?(male|man)\b")
    elif re.fullmatch(r"(cis ?(gender)? ?)?(female|woman)", l):
        out.append(r"^(cis ?(gender)? ?)?(female|woman)\b")
    if re.search(r"(?<!american )\bindian\b", l):
        out += [r"^(?!.*american indian).*\bindian\b", r"south asian", r"^asian\b(?!.*(chinese|pakistani|bangladeshi|any other|other asian))"]
    elif re.search(r"south asian", l):
        out += [r"south asian", r"^asian\b"]
    if re.search(r"heterosexual|straight", l):
        out.append(r"heterosexual|straight")
    if re.fullmatch(r"(yes|no)\b.*", l):
        out.append("^" + l.split()[0] + r"\b")
    if re.search(r"not a (protected )?veteran|i am not a", l):
        out.append(r"not a (protected )?veteran|^i am not\b")
    return out


def overridden_rules(rules):
    """Rohit's corrections to a generic rule (e.g. eeo_gender) replace that rule's answer on every form."""
    ov = load_learned().get("overrides", {})
    out = []
    for r in rules:
        o = ov.get(r.get("id"))
        if o and o.get("values"):
            r = dict(r)
            vals = o["values"]
            r["a"] = vals[0]
            exact = "|".join("^" + re.escape(x.strip().lower()) + "$" for x in vals)
            r["pick"] = "||".join([exact] + [p for x in vals for p in synonyms(x)])
            r.pop("choice_only", None)
            r.pop("avoid", None)
            r["_learned"] = True
        out.append(r)
    return out


def learned_rules():
    out = []
    for k, e in load_learned().get("answers", {}).items():
        if not e.get("a"):
            continue
        r = {"id": "learned", "q": "^" + re.escape(k[:120]), "a": e["a"]}
        if " | " in e["a"]:                     # multi-select: accept any of the picked options
            r["pick"] = "|".join("^" + re.escape(x.strip().lower()) + "$" for x in e["a"].split(" | "))
        out.append(r)
    return out


def save_learned(body):
    job_id = body.get("job_id") or ""
    app_dir = ROOT / "applications" / job_id if JOB_ID_RX.match(job_id) else None
    if app_dir and not app_dir.is_dir():
        app_dir = None
    company = ""
    if app_dir and (app_dir / "job.json").exists():
        try:
            company = json.loads((app_dir / "job.json").read_text(encoding="utf-8")).get("company", "")
        except Exception:
            pass
    company_l = company.lower().strip()
    host = urlparse(body.get("url") or "").netloc
    data = load_learned()
    ans = data.setdefault("answers", {})
    ovs = data.setdefault("overrides", {})
    base_rules = {r.get("id"): r for r in json.loads((ROOT / "data" / "answers.json").read_text(encoding="utf-8"))["rules"]}
    job_answers, saved = {}, {"global": 0, "job": 0, "rule": 0}
    for it in (body.get("items") or [])[:60]:
        label = re.sub(r"\s+", " ", str(it.get("label", ""))).strip()[:300]
        value = str(it.get("value", "")).strip()[:4000]
        if len(label) < 3 or not value:
            continue
        rule = base_rules.get(it.get("rule"))
        templated = bool(rule and "{" in (str(rule.get("a", "")) + str(rule.get("pick", ""))))  # job_city, salary...
        # a correction of a generic rule's answer (gender, ethnicity, relocation...) becomes the new answer everywhere
        if rule and not templated and not rule.get("never") and not rule.get("ack") and len(value) <= LONG_ANSWER:
            o = ovs.setdefault(rule["id"], {"values": []})
            o["values"] = [value] + [x for x in o["values"] if x.lower() != value.lower()][:9]
            o["last"] = time.strftime("%Y-%m-%d")
            o.setdefault("replaced", it.get("old"))
            saved["rule"] += 1
        job_specific = templated or (it.get("kind") == "text" and len(value) > LONG_ANSWER) or (
            len(company_l) > 2 and company_l in label.lower())
        if job_specific:
            if app_dir:
                job_answers[label] = value
                saved["job"] += 1
            continue
        k = norm_q(label)
        old = ans.get(k, {})
        ans[k] = {"q": label, "a": value, "kind": it.get("kind"), "seen": old.get("seen", 0) + 1,
                  "first": old.get("first") or time.strftime("%Y-%m-%d"), "last": time.strftime("%Y-%m-%d"),
                  "from": host, "job_id": job_id or None}
        saved["global"] += 1
    if saved["global"] or saved["rule"]:
        LEARNED.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    if job_answers:
        f = app_dir / "answers.json"
        cur = {}
        if f.exists():
            try:
                cur = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                cur = {}
        if isinstance(cur, dict) and "rules" not in cur:
            cur.update(job_answers)
            f.write_text(json.dumps(cur, indent=2, ensure_ascii=False), encoding="utf-8")
    return saved


def mark_applied(body):
    """The extension saw an ATS confirmation after Rohit clicked Submit: mark the job applied + log it."""
    import csv, subprocess, sys
    from datetime import date
    job_id = str(body.get("job_id") or "")
    if not JOB_ID_RX.match(job_id):
        return False
    rows = list(csv.DictReader(open(ROOT / "data" / "jobs.csv", encoding="utf-8")))
    row = next((r for r in rows if r["job_id"] == job_id), None)
    if not row or row["status"] in ("applied", "interview", "offer", "rejected"):
        return False
    how = "jobfill-auto" if body.get("how") == "jobfill-auto" else "submit-queue"
    who = "submitted by JobFill (auto)" if how == "jobfill-auto" else "submitted by Rohit"
    subprocess.run([sys.executable, str(ROOT / "src" / "app.py"), "status", job_id, "applied",
                    f"{who} {date.today()} (confirmation seen by JobFill)"], cwd=ROOT, check=True)
    led = ROOT / "data" / "applied_log.csv"
    new = not led.exists()
    with open(led, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "job_id", "company", "how"])
        w.writerow([str(date.today()), job_id, row["company"], how])
    st = ROOT / "data" / "autopilot_state.json"
    if st.exists():
        s = json.loads(st.read_text(encoding="utf-8"))
        if job_id in s:
            s[job_id]["to_submit"] = False; s[job_id]["result"] = "applied"
            st.write_text(json.dumps(s, indent=1), encoding="utf-8")
    return True


class H(BaseHTTPRequestHandler):
    def _guard(self):
        origin = self.headers.get("Origin", "")
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:          # DNS-rebinding guard
            return False
        if origin and not origin.startswith("chrome-extension://"):  # web pages may not read profile
            return False
        return True

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._guard():
            return self._send(403, {"error": "forbidden"})
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._guard():
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        try:
            if self.path.startswith("/context"):
                return self._send(200, build_context(body.get("urls", []), body.get("page_text", "")))
            if self.path.startswith("/report"):
                return self._send(200, {"saved": save_report(body)})
            if self.path.startswith("/learn"):
                return self._send(200, {"learned": save_learned(body)})
            if self.path.startswith("/applied"):
                return self._send(200, {"applied": mark_applied(body)})
        except Exception as e:  # keep the server alive, report the error to the extension
            return self._send(500, {"error": repr(e)})
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        sys.stderr.write("[jobfill] " + (fmt % args) + "\n")


if __name__ == "__main__":
    print(f"JobFill server on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
