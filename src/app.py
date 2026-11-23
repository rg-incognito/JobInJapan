"""
Per-job application workspace.

  python src/app.py prepare <job_id>   -> applications/<job_id>/{resume.tex, jd.txt}
  python src/app.py build   <job_id>   -> compiles resume.tex -> Rohit_Gande_<Company>.pdf, scores it, writes score.json
  python src/app.py status  <job_id> <new|shortlisted|tailored|ready|applied|interview|rejected|skipped|offer> [note]
"""
import csv, json, re, shutil, subprocess, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ats_score import score, load_text  # noqa: E402

TECTONIC = ROOT / "tools" / "tectonic.exe"
JOBS = ROOT / "data" / "jobs.csv"


def jobs():
    return list(csv.DictReader(open(JOBS, encoding="utf-8")))


def save(rows):
    with open(JOBS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


def job(job_id):
    for r in jobs():
        if r["job_id"] == job_id:
            return r
    sys.exit(f"unknown job_id {job_id}")


def prepare(job_id):
    j = job(job_id)
    d = ROOT / "applications" / job_id
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "resume.tex").exists():
        shutil.copy(ROOT / "resume" / "master.tex", d / "resume.tex")
    shutil.copy(ROOT / "data" / "jd" / f"{job_id}.txt", d / "jd.txt")
    (d / "job.json").write_text(json.dumps(j, indent=2), encoding="utf-8")
    print(d)


def build(job_id):
    j, d = job(job_id), ROOT / "applications" / job_id
    r = subprocess.run([str(TECTONIC), "-X", "compile", "resume.tex"], cwd=d, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(r.stderr[-2000:])
    safe = re.sub(r"[^A-Za-z0-9]+", "_", j["company"]).strip("_")
    pdf = d / f"Rohit_Gande_{safe}.pdf"
    shutil.move(d / "resume.pdf", pdf)
    from pypdf import PdfReader
    pages = len(PdfReader(str(pdf)).pages)
    res = score(load_text(str(pdf)), load_text(str(d / "jd.txt")), j["title"])
    res["pages"] = pages
    (d / "score.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"{pdf.name}: ATS {res['score']} | pages {pages} | missing: {', '.join(res['missing']) or '-'}"
          + (f" | fix: {res['failed_checks']}" if res["failed_checks"] else ""))


def status(job_id, st, note=""):
    rows = jobs()
    for r in rows:
        if r["job_id"] == job_id:
            r["status"] = st
            if note:
                r["notes"] = f"{date.today()}: {note}" + (f" | {r['notes']}" if r["notes"] else "")
    save(rows)


if __name__ == "__main__":
    cmd, *a = sys.argv[1:]
    {"prepare": prepare, "build": build, "status": status}[cmd](*a)
