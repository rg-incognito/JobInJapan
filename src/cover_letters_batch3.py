"""Cover letters for batch 3 (2026-11-01). No colons inside paragraphs, no placeholders, facts from master resume only."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIG = ("\n\nBest regards,\nRohit Gande\n+91 9527513399 | rohitgande.work@gmail.com | "
       "linkedin.com/in/rohit-gande | github.com/rg-incognito\n")
L = {
"ab-openai-c1316397-25bb-4add-9e9d-0e3ea8ba929a": ("OpenAI", "Software Engineer, Agent Infrastructure (London)",
"""I'm applying for the Software Engineer role on Agent Infrastructure in London. Most of my best recent work has been building the environment that lets an AI agent do real engineering, and your team does that at a scale I'd love to learn from.

At Sincro (a DealerOn company) I built a Claude Code plugin that lets an agent navigate our product UI and run end-to-end tests, plus skills that give it context on our incentives pipeline. At DMG I built a skill that takes an incident description and investigates a locally cloned codebase for the root cause. Underneath that I'm a backend engineer. I build real-time data pipelines and Java and Spring Boot microservices, I introduced gRPC with Protocol Buffers and cut latency by 30%, and I built our CI/CD pipeline from build to production on AWS and Docker.

Agents that execute code, debug and ship software need reliable infrastructure, and that is the problem I want to work on full time. I'm ready to relocate to London and work from the office three days a week."""),
"gh-monzo-6635595": ("Monzo", "Backend Engineer III (London)",
"""I'm applying for the Backend Engineer III role. I build backend services that have to stay correct while data changes constantly, and I'd like to do that for a bank whose customers actually love using it.

At Sincro (a DealerOn company) I run real-time, event-driven pipelines that keep vehicle pricing accurate across dealer websites, including MSRP, finance options and conditional offers, and I write the parsers that normalise feeds from multiple vendors. At DMG, as an SDE 2, I introduced gRPC with type-safe Protocol Buffers contracts between microservices and reduced latency by 30%. I also built our CI/CD pipeline to UAT and production and a Maven tool that upgrades many projects in one run. My main languages are Java and Python, and I have also worked in Go.

Monzo's in-house platform and the way your engineers own problems from end to end is the environment I want to grow in. I'm ready to relocate to London and value working together in the office."""),
"ab-snowflake-23c94498-23c8-4d6e-a1d8-4355bf605663": ("Snowflake", "Software Engineer, Java Platform (Berlin)",
"""I'm applying for the Software Engineer role on the Java Platform team in Berlin. I've spent my career writing Java and Spring Boot services, and the chance to work on the core libraries and JVM infrastructure that other Snowflake engineers depend on is what drew me to this role.

Much of my work already sits at the platform level. At Sincro (a DealerOn company) I built a Maven tool that upgrades dependency versions across many projects in one run, and I built the CI/CD pipeline from build to UAT and production with Consul-based configuration. At DMG I introduced gRPC with Protocol Buffers contracts between Java microservices and cut latency by 30%. I also use AI as a daily collaborator, building Claude Code plugins and agent skills for our engineering workflow.

I enjoy making shared code faster and safer for everyone who builds on it. I'm ready to relocate to Berlin and work from your Potsdamer Platz office."""),
"gh-adyen-6761873": ("Adyen", "Java Software Engineer, Customer Experience (Amsterdam)",
"""I'm applying for the Java Software Engineer role in your Customer Experience teams. I build Java services that run in production every day, and I want to take ownership of features at Adyen's scale.

At Sincro (a DealerOn company) I keep vehicle pricing accurate across automotive dealer websites by processing real-time inventory and incentive updates, backed by PostgreSQL and REST APIs. I built the CI/CD pipeline to UAT and production and a Maven tool that upgrades many projects in one run. At DMG I introduced gRPC with type-safe Protocol Buffers contracts between microservices and cut latency by 30%, and earlier I integrated the Bing Automotive Inventory Ads REST API, which cut campaign setup time by 50%.

I like owning the full cycle from design and testing to watching a change behave well in production, which is how your teams work. I'm ready to relocate to Amsterdam and work office-first."""),
"ab-cohere-2d256112-b336-4539-8133-a0bf7f6698f0": ("Cohere", "Forward Deployed Engineer, Agentic Platform (Europe)",
"""I'm applying for the Forward Deployed Engineer role on the Agentic Platform team. Connecting AI agents to the real tools and workflows that people use every day is the work I enjoy most, and North is built for exactly that.

At Sincro (a DealerOn company) I built a Claude Code plugin that lets an agent operate our product UI for end-to-end tests, and agent skills that give it context on our incentives pipeline. At DMG I built a skill that goes from an incident description to a root-cause investigation in the codebase. I also build integrations for non-engineers. During our platform migration I shipped a feature that copies a dealer site's data and components into the new template, replacing manual re-entry for our operations team. I write production Python and Java, and I have hands-on experience with RAG and LangChain.

I like working directly with the people who use what I build. I'm ready to relocate to any of your European offices."""),
}
for jid, (co, role, body) in L.items():
    assert ":" not in body, jid
    d = ROOT / "applications" / jid
    txt = f"Dear {co} Hiring Team,\n\nRe {role}\n\n{body}{SIG}"
    (d / "cover_letter.md").write_text(txt, encoding="utf-8")
    (d / "Rohit_Gande_Cover_Letter.txt").write_text(txt, encoding="utf-8")
    print(f"{co:10} {len(body.split())} words")
