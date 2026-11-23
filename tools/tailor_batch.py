"""One-off batch tailoring for cycle 2026-11-01 (round 3). Applies exact-string replacements to
applications/<id>/resume.tex. Fails loudly if any target string is missing."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD_SUMMARY = """\\small{Software Engineer with 3+ years of experience building real-time data pipelines, gRPC/REST microservices and CI/CD for
automotive platforms in Java, Spring Boot and Python, plus AI-agent developer tooling with Claude Code (plugins and skills) and LLMs.}"""
OLD_TEST = r"\textbf{Testing}: JUnit, Playwright, Selenium, Unit, Integration \& End-to-End (E2E) Testing \\"
NEW_TEST = r"\textbf{Testing \& Practices}: JUnit, Playwright, Selenium, Unit, Integration \& End-to-End (E2E) Testing, Code Review, Agile/Scrum \\"
OLD_DSA = "1,000+ DSA problems"
NEW_DSA = "1,000+ data structures and algorithms problems"
OLD_LANG = r"\textbf{Languages}: Java, Python, JavaScript, TypeScript, Kotlin, Go, SQL \\"
OLD_BACK = r"\textbf{Backend}: Spring Boot, Node.js, RESTful APIs, gRPC, Protocol Buffers, Microservices, Distributed Systems, Hibernate/JPA, Maven, Kafka, FastAPI, Flask \\"
OLD_FRONT = r"\textbf{Frontend}: React, Angular \\"
OLD_AI = r"\textbf{AI / ML}: LLMs, AI Agents,"
OLD_DB = r"\textbf{Databases}: PostgreSQL, MySQL, MongoDB, Redis, RDBMS, NoSQL \\"
OLD_CLOUD = r"\textbf{Cloud \& DevOps}: AWS (EC2, ECR, S3, CloudWatch, Bedrock), Docker, Kubernetes, GCP, Azure, Linux, CI/CD (Bamboo, Bitbucket), Terraform, Consul \\"
OLD_HEADER = r"\small Software Engineer \;|\; Pune, India \;|\; Open to relocation (visa sponsorship required) \\"
OLD_CLIP = "Built a full-stack SaaS that turns long videos into vertical shorts: Spring Boot REST API,"


def summary(text):
    return "\\small{" + text + "}"


JOBS = {
    "gh-helsing-4125061101": [
        (OLD_HEADER, r"\small Backend Software Engineer \;|\; Pune, India \;|\; Open to relocation (visa sponsorship required) \\"),
        (OLD_SUMMARY, summary("Backend Software Engineer with 3+ years of experience building distributed systems, gRPC/Protocol Buffers and RESTful "
                              "microservices and data pipelines in Java, Spring Boot and Python, plus Generative AI and LLM agent tooling.")),
        (OLD_LANG, r"\textbf{Languages}: Java, Go, Python, SQL, Kotlin, TypeScript, JavaScript \\"),
        (OLD_BACK, r"\textbf{Backend}: gRPC, Protocol Buffers, RESTful APIs, Distributed Systems, Microservices, Spring Boot, Kafka, Node.js, Hibernate/JPA, Maven, FastAPI, Flask \\"),
        (OLD_AI, r"\textbf{AI / ML}: LLMs, Generative AI, AI Agents,"),
    ],
    "ab-openai-a0ccedf1-2bb7-4f10-8be8-db50f9ae02c3": [
        (OLD_SUMMARY, summary("Full-stack Software Engineer with 3+ years of experience building backend services, data pipelines and internal tooling "
                              "in Java, Spring Boot, Python and React, owning production systems through testing, monitoring and CI/CD.")),
        (OLD_LANG, r"\textbf{Languages}: Python, Java, SQL, TypeScript, JavaScript, Go, Kotlin \\"),
    ],
    "gh-doctolib-7809464003": [
        (OLD_HEADER, r"\small Fullstack Software Engineer \;|\; Pune, India \;|\; Open to relocation (visa sponsorship required) \\"),
        (OLD_SUMMARY, summary("Fullstack Software Engineer with 3+ years on the JVM ecosystem (Java, Spring Boot, Kotlin) and React/TypeScript, building "
                              "RESTful microservices and well-tested code with unit, integration and E2E tests, code review and CI/CD.")),
        (OLD_LANG, r"\textbf{Languages}: Java, Kotlin, TypeScript, JavaScript, Python, SQL, Go \\"),
        (OLD_FRONT, r"\textbf{Frontend}: React, TypeScript, Next.js, Angular \\"),
    ],
    "gh-staffbase-8819543002": [
        (OLD_HEADER, r"\small Fullstack Engineer \;|\; Pune, India \;|\; Open to relocation (visa sponsorship required) \\"),
        (OLD_SUMMARY, summary("Fullstack Engineer with 3+ years of experience integrating third-party APIs and vendor feeds, building RESTful microservices "
                              "and React/TypeScript UIs, and shipping AI agents and Claude Code plugins that take actions in a browser.")),
        (OLD_LANG, r"\textbf{Languages}: TypeScript, JavaScript, Kotlin, Go, Java, Python, SQL \\"),
        (OLD_FRONT, r"\textbf{Frontend}: React, TypeScript, Next.js, Angular \\"),
        (OLD_CLIP, "Built a fullstack SaaS that turns long videos into vertical shorts: Spring Boot REST API,"),
    ],
    "gh-sumup-8789067002": [
        (OLD_HEADER, r"\small Backend Engineer \;|\; Pune, India \;|\; Open to relocation to Europe (visa sponsorship required) \\"),
        (OLD_SUMMARY, summary("Backend Engineer with 3+ years of experience building and supporting production backend services, data pipelines and "
                              "RESTful/gRPC microservices in Java, Spring Boot and Python, with API design, code review and CI/CD on AWS.")),
        (OLD_LANG, r"\textbf{Languages}: Go (Golang), Java, Python, SQL, Kotlin, TypeScript, JavaScript \\"),
        (OLD_BACK, r"\textbf{Backend}: Microservices, RESTful APIs, gRPC, Kafka, Distributed Systems, Spring Boot, Protocol Buffers, Node.js, Hibernate/JPA, Maven, FastAPI, Flask \\"),
        (OLD_DB, r"\textbf{Databases}: PostgreSQL, Redis, MySQL, MongoDB, RDBMS, NoSQL \\"),
        (OLD_CLOUD, r"\textbf{Cloud \& DevOps}: AWS (EC2, ECR, S3, CloudWatch, Bedrock), Kubernetes, Docker, CI/CD (Bamboo, Bitbucket), Linux, GCP, Azure, Terraform, Consul \\"),
    ],
}

for job_id in (sys.argv[1:] or JOBS):
    p = ROOT / "applications" / job_id / "resume.tex"
    t = (ROOT / "resume" / "master.tex").read_text(encoding="utf-8")  # always start from master
    for old, new in [(OLD_TEST, NEW_TEST), (OLD_DSA, NEW_DSA)] + JOBS[job_id]:
        if old not in t:
            sys.exit(f"{job_id}: target not found: {old[:60]}")
        t = t.replace(old, new, 1)
    p.write_text(t, encoding="utf-8")
    print("tailored", job_id)
