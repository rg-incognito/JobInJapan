"""
ATS match scorer (Jobscan-style approximation).

Real ATS systems (Greenhouse, Lever, Workday...) don't publish a single "score";
recruiters filter/search by keywords. This scorer measures what matters for that:
  - 75%  hard-skill / keyword coverage of the job description (frequency weighted)
  - 10%  job-title alignment
  - 15%  parseability & structure (contact info, standard sections, dates, length)

Usage:
  python src/ats_score.py <resume.pdf|resume.tex|resume.txt> <jd.txt> [--json]
"""
import json, re, sys
from pathlib import Path

# canonical skill -> regex alternatives (matched case-insensitively on word boundaries)
TAXONOMY = {
    # languages
    "Java": r"java(?!\s*script)", "Python": r"python", "JavaScript": r"javascript|\bjs\b", "TypeScript": r"typescript|\bts\b",
    "Kotlin": r"kotlin", "Go": r"golang|\bgo\b(?=[\s,/)])", "Rust": r"rust", "C++": r"c\+\+|cpp", "C#": r"c#|\.net|dotnet",
    "Scala": r"scala", "Ruby": r"ruby|rails", "PHP": r"php", "SQL": r"\bsql\b", "Bash": r"bash|shell scripting",
    "HTML": r"html5?", "CSS": r"css3?|sass|scss",
    # backend / frameworks
    "Spring Boot": r"spring\s*boot|spring framework|\bspring\b", "Hibernate": r"hibernate|jpa", "Node.js": r"node\.?js|\bnode\b",
    "Express": r"express\.?js|\bexpress\b", "Django": r"django", "FastAPI": r"fastapi", "Flask": r"flask",
    "React": r"react(\.?js)?", "Angular": r"angular(\.?js)?", "Vue": r"vue(\.?js)?", "Next.js": r"next\.?js",
    "JUnit": r"junit", "Maven": r"maven", "Gradle": r"gradle", "GraphQL": r"graphql", "gRPC": r"grpc",
    "REST APIs": r"rest(ful)?\s*api|rest\b|restful", "Microservices": r"micro-?services?",
    "Distributed systems": r"distributed systems?", "Event-driven": r"event[- ](driven|based)|asynchronous",
    "System design": r"system design|scalab(le|ility)", "API design": r"api design",
    # data
    "PostgreSQL": r"postgres(ql)?", "MySQL": r"mysql", "NoSQL": r"nosql", "MongoDB": r"mongo(db)?", "Redis": r"redis",
    "Elasticsearch": r"elastic\s*search", "Kafka": r"kafka", "RabbitMQ": r"rabbitmq", "Spark": r"\bspark\b",
    "DynamoDB": r"dynamo\s*db", "Cassandra": r"cassandra", "Snowflake": r"snowflake", "Data pipelines": r"data pipelines?|etl",
    "RDBMS": r"rdbms|relational databases?",
    # cloud / devops
    "AWS": r"\baws\b|amazon web services", "GCP": r"\bgcp\b|google cloud", "Azure": r"azure", "Docker": r"docker|containeri[sz]",
    "Kubernetes": r"kubernetes|\bk8s\b", "Terraform": r"terraform", "CI/CD": r"ci\s*/\s*cd|continuous (integration|delivery|deployment)",
    "GitHub Actions": r"github actions", "Jenkins": r"jenkins", "Bamboo": r"bamboo", "Amazon Bedrock": r"bedrock", "Consul": r"consul", "Git": r"\bgit\b|github|gitlab|bitbucket", "Linux": r"linux|unix",
    "Observability": r"observability|monitoring|prometheus|opentelemetry", "Serverless": r"serverless|lambda", "AWS services": r"\bec2\b|\becr\b|\bs3\b|cloudwatch|\becs\b|\beks\b",
    "Cloud": r"\bcloud\b",
    # AI / ML
    "LLM": r"\bllms?\b|large language models?", "Generative AI": r"generative ai|gen\s*ai", "AI agents": r"ai agents?|agentic|multi-agent",
    "RAG": r"\brag\b|retrieval[- ]augmented", "LangChain": r"langchain", "CrewAI": r"crew\s*ai", "OpenAI API": r"openai|chatgpt|gpt-?\d",
    "Prompt engineering": r"prompt engineering", "Machine learning": r"machine learning|\bml\b", "Deep learning": r"deep learning",
    "Computer vision": r"computer vision|object detection|yolo", "PyTorch": r"pytorch", "TensorFlow": r"tensorflow",
    "NLP": r"\bnlp\b|natural language processing", "Vector databases": r"vector (db|database|store)s?|pinecone|pgvector|weaviate",
    # practices
    "Unit testing": r"unit test(ing|s)?|tdd|test[- ]driven", "Integration testing": r"integration test(ing|s)?",
    "Agile": r"agile|scrum|kanban", "Code review": r"code reviews?", "Web scraping": r"web scraping|scrap(er|ing)|crawl(er|ing)",
    "Automation": r"automat(ion|ed|e)", "Performance optimization": r"performance (optimi[sz]ation|tuning)|latency",
    "Security": r"security|oauth|authentication", "Payments": r"payments?", "Fintech": r"fintech|banking",
    "Object-oriented programming": r"object[- ]oriented|\boop\b", "Data structures & algorithms": r"data structures|algorithms",
}
# spoken-language requirements are reported separately, never scored (can't be fixed by editing a resume)
LANG_REQ = {
    "Japanese": re.compile(r"(business|fluent|native|conversational)[- ]level (proficiency in )?japanese|proficiency in japanese|japanese[^.\n]{0,40}(required|fluen|proficien|jlpt|n[12]\b)|jlpt\s*n[1-3]", re.I),
    "German": re.compile(r"(fluent|business|native)[^.\n]{0,20}german\b|\bgerman\b(?!y)[^.\n]{0,40}(required|fluen|proficien|c1|b2|mandatory|must)", re.I),
}
SOFT_NOISE = {"Cloud", "Automation", "Security", "Payments", "Fintech"}  # down-weighted
COMPILED = {k: re.compile(r"(?<![\w+#])(?:%s)(?![\w+#])" % v, re.I) for k, v in TAXONOMY.items()}


def load_text(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        raw = "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
        if re.search("[ﬀ-ﬆ]", raw):
            raw += "\n�"  # ligature glyphs present -> fail the 'no unparsed glyphs' check
        return raw
    t = p.read_text(encoding="utf-8", errors="ignore")
    if p.suffix.lower() == ".tex":
        t = re.sub(r"%.*", "", t)
        t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", t)
        t = re.sub(r"[{}$\\]", " ", t)
    return t


def find_skills(text: str) -> dict:
    out = {}
    for k, rx in COMPILED.items():
        n = len(rx.findall(text))
        if n:
            out[k] = n
    return out


def title_words(title: str) -> set:
    stop = {"senior", "sr", "junior", "jr", "mid", "level", "i", "ii", "iii", "m/f/d", "f/m/d", "m", "f", "d", "w", "x", "-", "&", "and", "the", "of", "for", "(", ")"}
    return {w for w in re.findall(r"[a-z+#.]+", title.lower()) if w not in stop and len(w) > 1}


def structure_checks(resume: str) -> list:
    low = resume.lower()
    checks = [
        ("email", bool(re.search(r"[\w.+-]+@[\w-]+\.\w+", resume))),
        ("phone", bool(re.search(r"\+?\d[\d\s-]{8,}", resume))),
        ("linkedin url", "linkedin.com/" in low),
        ("experience section", bool(re.search(r"\bexperience\b", low))),
        ("education section", "education" in low),
        ("skills section", "skills" in low),
        ("dates parseable", len(re.findall(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}", low)) >= 4),
        ("length 350-950 words", 350 <= len(resume.split()) <= 950),
        ("no unparsed glyphs", resume.count("\ufffd") == 0 and not re.search(r"[\uf000-\uf8ff]", resume)),
        ("github/portfolio url", "github.com/" in low),
    ]
    return checks


def score(resume: str, jd: str, job_title: str = "") -> dict:
    jd_sk, cv_sk = find_skills(jd), find_skills(resume)
    weights = {k: (0.4 if k in SOFT_NOISE else 1.0) * (1 + 0.5 * min(n - 1, 2)) for k, n in jd_sk.items()}
    total = sum(weights.values()) or 1
    matched = {k for k in jd_sk if k in cv_sk}
    kw = sum(weights[k] for k in matched) / total

    if job_title:
        tw = title_words(job_title)
        tmatch = len([w for w in tw if w in resume.lower()]) / (len(tw) or 1)
    else:
        tmatch = 1.0
    checks = structure_checks(resume)
    st = sum(ok for _, ok in checks) / len(checks)
    final = round(100 * (0.75 * kw + 0.10 * tmatch + 0.15 * st), 1)
    missing = sorted((k for k in jd_sk if k not in matched), key=lambda k: -weights[k])
    return {
        "score": final, "keyword_coverage": round(100 * kw, 1), "title_match": round(100 * tmatch, 1),
        "structure": round(100 * st, 1), "matched": sorted(matched), "missing": missing,
        "failed_checks": [n for n, ok in checks if not ok],
        "language_requirements": [k for k, rx in LANG_REQ.items() if rx.search(jd)],
    }


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    title = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--title=")), "")
    r = score(load_text(args[0]), load_text(args[1]), title)
    if "--json" in sys.argv:
        print(json.dumps(r, indent=2))
    else:
        print(f"ATS score: {r['score']}  (keywords {r['keyword_coverage']}%, title {r['title_match']}%, structure {r['structure']}%)")
        print("Matched :", ", ".join(r["matched"]))
        print("Missing :", ", ".join(r["missing"]) or "-")
        if r["language_requirements"]:
            print("Language:", ", ".join(r["language_requirements"]), "(required by JD)")
        if r["failed_checks"]:
            print("Fix     :", ", ".join(r["failed_checks"]))
