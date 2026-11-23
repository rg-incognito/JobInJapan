"""Print the best open jobs to work on next.
python src/report.py [--n 25] [--country Germany] [--all-levels]"""
import csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
arg = lambda k, d=None: next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{k}=")), d)
n, country = int(arg("n", 25)), arg("country")
MAXY = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("max_required_years", 99)
rows = [r for r in csv.DictReader(open(ROOT / "data/jobs.csv", encoding="utf-8"))
        if r["status"] in ("new", "shortlisted") and r["sponsorship"] != "no"
        and ("--all-levels" in sys.argv or r["level"] == "mid")
        and (r.get("req_years") in (None, "") or int(r["req_years"]) <= MAXY) and (not country or r["country"] == country)]
rank = {"yes": 0, "unknown": 1}
PRI = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("country_priority", [])
cprio = lambda c: PRI.index(c) if c in PRI else len(PRI)
rows.sort(key=lambda r: (rank[r["sponsorship"]], cprio(r["country"]), r["tier"], -float(r["base_ats_score"] or 0)))
print(f"{'yrs':>3} {'score':>5}  {'visa':7} {'tier':4} {'country':11} {'company':18} title  [job_id]")
for r in rows[:n]:
    print(f"{r.get('req_years') or '?':>3} {r['base_ats_score']:>5}  {r['sponsorship']:7} {r['tier']:4} {r['country'][:11]:11} {r['company'][:18]:18} {r['title'][:60]}  [{r['job_id']}]")
print(f"\n{len(rows)} open matching jobs")
