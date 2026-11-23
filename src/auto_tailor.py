"""
Token-free tailoring for the autopilot: truthful, rule-based edits to applications/<id>/resume.tex plus a template
cover letter. Never adds anything that is not already in resume/master.tex or resume/skills_bank.json -> confirmed.

  python src/auto_tailor.py <job_id>      -> resume.tex tailored, PDF built + scored, cover letter written

What it changes:
  * Summary: one of three truthful variants (backend / full-stack / FDE-AI) picked from the job title + JD.
  * Technical Skills: items the JD mentions move to the front of each line, lines with more JD hits move up
    (Languages stays first), and confirmed skills the JD asks for but the resume omits are appended (Gradle, Git...).
  * If the PDF grows past 1 page the additions are dropped and it is rebuilt.
"""
import json, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ats_score import score, load_text  # noqa: E402

PY = sys.executable

SUMMARY_RX = re.compile(r"(\\section\{Summary\}\s*\n\\small\{)(.*?)(\}\s*\n)", re.S)
SKILLS_RX = re.compile(r"(\\section\{Technical Skills\}.*?\\item\[\] \\small\{\n)(.*?)(\n\s*\}\s*\n\\listend)", re.S)

SUMMARIES = {   # keep each <= the master summary's length (236 chars) so the page count does not change
    "backend": "Backend Software Engineer with 3+ years of experience building real-time data pipelines, gRPC/REST microservices "
               "and CI/CD in Java, Spring Boot and Python on AWS, plus AI-agent developer tooling with Claude Code and LLMs.",
    "fullstack": "Full-Stack Software Engineer with 3+ years of experience building Java, Spring Boot and Python microservices, "
                 "REST/gRPC APIs, React and Angular UIs and CI/CD, plus AI-agent developer tooling with Claude Code and LLMs.",
    "fde": "Software Engineer with 3+ years of experience shipping AI agents and LLM tooling (Claude Code plugins and skills, RAG) "
           "alongside production Java, Spring Boot and Python microservices, data pipelines and CI/CD.",
}

# confirmed skills (skills_bank.json) that master.tex leaves out -> (JD regex, skills line, text to append)
EXTRA = [
    (r"\bgradle\b", "Backend", "Gradle"),
    (r"\bgit\b|github|gitlab", "Cloud \\& DevOps", "Git"),
    (r"machine learning|\bml\b", "AI / ML", "Machine Learning"),
    (r"\bagile\b|\bscrum\b", "Testing", "Agile/Scrum"),
    (r"code reviews?", "Testing", "Code Review"),
]

HOOK = {
    "backend": "Building reliable backend services and APIs that other teams and customers depend on is the work I have done "
               "for the last three years, and I would like to keep doing it on {company}'s products.",
    "fullstack": "Owning features end to end, from the API and data model to the screen a user sees, is the work I enjoy most, "
                 "and that is what this role at {company} offers.",
    "fde": "Turning ambiguous problems into AI agents and services that run in production is the work I have been doing and "
           "want to do more of, closer to the customers who use them.",
}


def family(title, jd):
    t = title.lower()
    if re.search(r"forward.?deployed|\bfde\b|applied ai|\bai\b|agent|llm", t):
        return "fde"
    if re.search(r"full.?stack|product engineer", t) or (re.search(r"\breact\b", jd.lower()) and not re.search(r"backend|back-end", t)):
        return "fullstack"
    return "backend"


def split_items(s):
    """Split 'A, B (x, y), C' on top-level commas only."""
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def item_rx(item):
    """Regex for an item's main term, e.g. 'AWS (EC2, S3)' -> aws|ec2|s3, 'Hibernate/JPA' -> hibernate|jpa."""
    words = [w.strip() for w in re.split(r"[(),/]|\\&", item) if w.strip()]
    alts = [re.escape(w.lower()).replace(r"\ ", r"[\s-]?") for w in words if len(w) > 1 and w.lower() not in ("unit", "integration")]
    return re.compile(r"(?<![a-z])(%s)(?![a-z])" % "|".join(alts)) if alts else None


def tailor_skills(block, jd_low, add_extra=True):
    lines = [l for l in block.split("\n") if l.strip()]
    parsed = []
    for l in lines:
        m = re.match(r"(\s*\\textbf\{(.+?)\}: )(.*?)(\s*\\\\)?\s*$", l)
        if not m:
            return block
        head, name, body = m.group(1), m.group(2), m.group(3)
        items = [i.replace("@@", ",") for i in split_items(body.replace("Unit, Integration", "Unit@@ Integration"))]
        hits = [bool((rx := item_rx(i)) and rx.search(jd_low)) for i in items]
        if add_extra:
            for pat, line_name, text in EXTRA:
                if line_name == name and re.search(pat, jd_low) and text.lower() not in body.lower():
                    items.append(text); hits.append(True)
        order = sorted(range(len(items)), key=lambda k: (not hits[k], k))
        parsed.append((name, head, [items[k] for k in order], sum(hits)))
    first, rest = parsed[0], parsed[1:]
    rest = sorted(rest, key=lambda p: -p[3])   # stable: ties keep master order
    out = [first] + rest
    return "\n".join(h + ", ".join(items) + (" \\\\" if i < len(out) - 1 else "") for i, (n, h, items, _) in enumerate(out))


def build(job_id):
    r = subprocess.run([PY, str(ROOT / "src" / "app.py"), "build", job_id], capture_output=True, text=True, cwd=ROOT)
    if r.returncode:
        raise RuntimeError(r.stderr[-800:] or r.stdout[-800:])
    return json.loads((ROOT / "applications" / job_id / "score.json").read_text(encoding="utf-8"))


def cover_letter(job, fam):
    company = job["company"]
    title = re.sub(r"\s*\((?:[mfwdxa]/?|all genders?|m/w/d|f/m/d|w/m/d|x/f/m|f/m/x|m/f/x|m/f/d|d/f/m)+\)", "", job["title"], flags=re.I).strip()
    city = (job["location"].split(";")[0].split(",")[0].strip() or job["country"])
    place = job["country"] if re.search(r"remote|anywhere", city, re.I) else city
    stack = "Java, Spring Boot and Python"
    para2 = ("At Sincro (a DealerOn company) I run real-time pipelines that keep vehicle prices, finance options and offers "
             "accurate across dealer websites, I built our CI/CD pipeline on Bamboo and Bitbucket from UAT to production, and "
             "I build AI-agent tooling with Claude Code plugins and skills. At Divisions Maintenance Group, as an SDE 2, I "
             "introduced gRPC with Protocol Buffers contracts between microservices, cut latency by 30%, and added unit and "
             f"integration tests. My production work is mainly in {stack}.")
    body = (f"Dear {company} Hiring Team,\n\nRe {title} ({place})\n\n"
            f"I'm applying for the {title} role at {company}. " + HOOK[fam].format(company=company, title=title) + "\n\n"
            + para2 + "\n\n"
            f"I'm ready to relocate to {place} with visa sponsorship, and I would welcome the chance to talk.\n\n"
            "Best regards,\nRohit Gande\n+91 9527513399 | rohitgande.work@gmail.com | linkedin.com/in/rohit-gande | github.com/rg-incognito\n")
    return body


def run(job_id):
    d = ROOT / "applications" / job_id
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    jd = (d / "jd.txt").read_text(encoding="utf-8")
    fam = family(job["title"], jd)
    master = (ROOT / "resume" / "master.tex").read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10))

    def write(add_extra):
        tex = SUMMARY_RX.sub(lambda m: m.group(1) + SUMMARIES[fam] + m.group(3), master, count=1)
        tex = SKILLS_RX.sub(lambda m: m.group(1) + tailor_skills(m.group(2), jd.lower(), add_extra) + m.group(3), tex, count=1)
        (d / "resume.tex").write_text(tex, encoding="utf-8")

    for p in d.glob("Rohit_Gande_*.pdf"):
        p.unlink()
    write(True)
    res, stage = build(job_id), "tailored"
    if res.get("pages", 1) > 1:
        stage = "tailored-no-extras"
        for p in d.glob("Rohit_Gande_*.pdf"):
            p.unlink()
        write(False)
        res = build(job_id)
    if res.get("pages", 1) > 1:   # fall back to the untouched master
        stage = "master"
        shutil.copy(ROOT / "resume" / "master.tex", d / "resume.tex")
        for p in d.glob("Rohit_Gande_*.pdf"):
            p.unlink()
        res = build(job_id)
    if not (d / "cover_letter.md").exists():
        cl = cover_letter(job, fam)
        (d / "cover_letter.md").write_text(cl, encoding="utf-8")
    if not (d / "Rohit_Gande_Cover_Letter.txt").exists():
        (d / "Rohit_Gande_Cover_Letter.txt").write_text((d / "cover_letter.md").read_text(encoding="utf-8"), encoding="utf-8")
    return {"family": fam, "stage": stage, "score": res["score"], "pages": res.get("pages"), "missing": res.get("missing", [])}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1])))
