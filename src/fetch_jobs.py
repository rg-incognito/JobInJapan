"""
Pull live openings from public ATS job-board APIs (Greenhouse, Lever, Ashby,
SmartRecruiters) for every company in data/companies.csv, keep only roles that
match the target titles + countries, detect visa-sponsorship language, score
each against the master resume, and write data/jobs.csv. New jobs get status=new.

Usage: python src/fetch_jobs.py [--company Adyen] [--limit-per-company 50]
"""
import csv, html, json, re, sys, urllib.request, concurrent.futures as cf
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ats_score import score, load_text  # noqa: E402

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
JD_DIR = ROOT / "data" / "jd"; JD_DIR.mkdir(parents=True, exist_ok=True)
JOBS_CSV = ROOT / "data" / "jobs.csv"
FIELDS = ["job_id", "company", "title", "country", "location", "level", "req_years", "sponsorship", "base_ats_score",
          "salary", "url", "first_seen", "status", "tier", "notes"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (job-search personal tool)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def strip_html(s):
    s = html.unescape(s or "")
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", s))


def fetch_company(c):
    ats, slug = c["ats"], c["slug"]
    out = []
    try:
        if ats == "greenhouse":
            for j in get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")["jobs"]:
                out.append(dict(id=f"gh-{slug}-{j['id']}", title=j["title"], location=(j.get("location") or {}).get("name", ""),
                                url=j["absolute_url"], desc=strip_html(j.get("content")), salary=""))
        elif ats == "lever":
            for j in get(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
                cats = j.get("categories", {})
                locs = cats.get("allLocations") or [cats.get("location", "")]
                desc = (j.get("descriptionPlain") or "") + "\n" + "\n".join(
                    l.get("text", "") + "\n" + strip_html(l.get("content")) for l in j.get("lists", [])) + strip_html(j.get("additional"))
                sal = j.get("salaryRange") or {}
                out.append(dict(id=f"lv-{slug}-{j['id']}", title=j["text"], location="; ".join(filter(None, locs)),
                                url=j["hostedUrl"], desc=desc,
                                salary=f"{sal.get('currency','')} {sal.get('min','')}-{sal.get('max','')}" if sal else ""))
        elif ats == "ashby":
            for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")["jobs"]:
                locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations", []) or []]
                comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
                out.append(dict(id=f"ab-{slug}-{j['id']}", title=j["title"], location="; ".join(filter(None, locs)),
                                url=j["jobUrl"], desc=j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")), salary=comp))
        elif ats == "smartrecruiters":
            offset = 0
            while offset < 1000:
                d = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}")
                for j in d["content"]:
                    loc = j.get("location", {})
                    out.append(dict(id=f"sr-{slug}-{j['id']}", title=j["name"],
                                    location=", ".join(filter(None, [loc.get("city"), loc.get("country")])),
                                    url=f"https://jobs.smartrecruiters.com/{slug}/{j['id']}", desc=None, salary="",
                                    detail=f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{j['id']}"))
                offset += 100
                if offset >= d.get("totalFound", 0):
                    break
    except Exception as e:
        print(f"  ! {c['company']}: {e}", file=sys.stderr)
    return c, out


def country_of(location):
    low = location.lower()
    for country, keys in CFG["target_countries"].items():
        for k in keys:
            if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(k), low):
                return country
    return None


def title_ok(title):
    t = f" {title.lower()} "
    return any(k in t for k in CFG["title_include"]) and not any(k in t for k in CFG["title_exclude"])


NO_SPONSOR_RX = re.compile(
    r"\b(unable|not able|cannot|can.?t|can not|do(es)? not|don.?t|won.?t|will not|not in a position)\s+(to\s+)?(\w+\s+){0,3}?"
    r"(offer|provide|support|sponsor|assist)\w*\s+(\w+\s+){0,3}?(visa|sponsorship|relocation|work permit)"
    r"|\bmust (already )?(hold|have|possess) (the |a )?(legal |valid |full )?(right to work|work (permit|authori[sz]ation))"
    r"|\b(already )?(hold|have) the (legal )?right to work in"
    r"|\bno (visa )?sponsorship\b|\bsponsorship is not (available|offered|possible)", re.I)


def sponsorship(desc):
    low = (desc or "").lower()
    if any(p in low for p in CFG["no_sponsor_phrases"]) or NO_SPONSOR_RX.search(low):
        return "no"
    if any(p in low for p in CFG["sponsor_phrases"]):
        return "yes"
    return "unknown"


YEARS_RX = re.compile(r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|to\s*\d{1,2})?\s*\+?\s*years?(?:'|’)?\s*(?:of\s+)?(?:[\w/,+-]+\s+){0,6}?(?:experience|exp)", re.I)


def required_years(desc):
    """Largest "N+ years ... experience" requirement stated; '' if none."""
    nums = [int(m.group(1)) for m in YEARS_RX.finditer(desc or "") if 0 < int(m.group(1)) <= 15]
    return max(nums) if nums else ""


def main():
    only = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--company=")), None)
    companies = [c for c in csv.DictReader(open(ROOT / "data/companies.csv", encoding="utf-8"))
                 if c["ats"] != "manual" and (not only or c["company"].lower() == only.lower())]
    master = load_text(str(ROOT / "resume/master.pdf")) if (ROOT / "resume/master.pdf").exists() else load_text(str(ROOT / "resume/master.tex"))

    existing = {}
    if JOBS_CSV.exists():
        existing = {r["job_id"]: r for r in csv.DictReader(open(JOBS_CSV, encoding="utf-8"))}

    candidates = []
    with cf.ThreadPoolExecutor(16) as ex:
        for c, jobs in ex.map(fetch_company, companies):
            for j in jobs:
                country = country_of(j["location"])
                if country and title_ok(j["title"]):
                    candidates.append((c, j, country))
    print(f"{len(candidates)} matching openings across {len(companies)} companies")

    # SmartRecruiters needs a detail call for the description (only for filtered jobs)
    def hydrate(item):
        c, j, country = item
        if j.get("desc") is None and j.get("detail"):
            try:
                secs = get(j["detail"]).get("jobAd", {}).get("sections", {})
                j["desc"] = "\n".join(strip_html(s.get("text")) for s in secs.values() if isinstance(s, dict))
            except Exception:
                j["desc"] = ""
        return item
    with cf.ThreadPoolExecutor(16) as ex:
        candidates = list(ex.map(hydrate, candidates))

    today, rows, new = date.today().isoformat(), {}, 0
    for c, j, country in candidates:
        desc = j["desc"] or ""
        (JD_DIR / f"{j['id']}.txt").write_text(f"{j['title']}\n{c['company']} | {j['location']}\n{j['url']}\n\n{desc}", encoding="utf-8")
        old = existing.get(j["id"])
        level = "senior" if any(k in f" {j['title'].lower()} " for k in CFG["senior_keywords"]) else "mid"
        rows[j["id"]] = {
            "job_id": j["id"], "company": c["company"], "title": j["title"], "country": country, "location": j["location"],
            "level": level, "req_years": required_years(desc), "sponsorship": sponsorship(desc), "base_ats_score": score(master, desc, j["title"])["score"],
            "salary": j.get("salary", ""), "url": j["url"], "first_seen": old["first_seen"] if old else today,
            "status": old["status"] if old else "new", "tier": c["tier"], "notes": old["notes"] if old else "",
        }
        new += old is None
    # keep history of jobs that disappeared (mark closed) unless already acted on
    for jid, r in existing.items():
        if jid not in rows and (not only or r["company"].lower() == only.lower()):
            if r["status"] in ("new", "shortlisted"):
                r["status"] = "closed"
            rows[jid] = r
        elif jid not in rows:
            rows[jid] = r

    ordered = sorted(rows.values(), key=lambda r: (r["status"] != "new", r["sponsorship"] == "no", r["tier"], -float(r["base_ats_score"] or 0)))
    with open(JOBS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(ordered)
    print(f"{new} new jobs. Wrote {JOBS_CSV}")


if __name__ == "__main__":
    main()
