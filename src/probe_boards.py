"""Probe public ATS job-board APIs to find which company slugs are live."""
import json, sys, concurrent.futures as cf, urllib.request

CANDIDATES = sys.argv[1].split(",")
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        return None

def probe(slug):
    hits = []
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if d and d.get("jobs"): hits.append(("greenhouse", len(d["jobs"])))
    d = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if isinstance(d, list) and d: hits.append(("lever", len(d)))
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if d and d.get("jobs"): hits.append(("ashby", len(d["jobs"])))
    d = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1")
    if d and d.get("totalFound"): hits.append(("smartrecruiters", d["totalFound"]))
    return slug, hits

with cf.ThreadPoolExecutor(24) as ex:
    for slug, hits in ex.map(probe, CANDIDATES):
        print(slug, hits)
