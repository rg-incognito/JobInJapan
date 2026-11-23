"""Cover letters for batch 2 (2026-11-01). No colons inside paragraphs, no placeholders, facts from master resume only."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIG = ("\n\nBest regards,\nRohit Gande\n+91 9527513399 | rohitgande.work@gmail.com | "
       "linkedin.com/in/rohit-gande | github.com/rg-incognito\n")
L = {
"sr-scalablegmbh-744000157800719": ("Scalable Capital", "AI Software Engineer, Python (Berlin)",
"""I'm applying for the AI Software Engineer role in your Data Science team. Bringing LLM capabilities into production systems, rather than training models from scratch, is exactly the work I enjoy most.

At Sincro (a DealerOn company) I build Claude Code plugins and agent skills that run inside our engineering workflow, including one that drives the browser to run end-to-end tests. At DMG I built a skill that takes an incident report and investigates the codebase for the root cause. Alongside the AI work I run real-time inventory and incentive pipelines, built our CI/CD pipeline from build to production, and work with AWS, Docker and Terraform. On my own time I built ClipForge, a full-stack AI video product with Python workers that call LLMs with automatic model fallback.

Your focus on agentic workflows, AWS, Terraform and monitoring for AI systems matches where I want to grow. I'd be glad to help build this new work stream, and I'm ready to relocate to Berlin."""),
"gh-adyen-7369512": ("Adyen", "Java Software Engineer, Payments (Amsterdam)",
"""I'm applying for the Java Software Engineer role in your payments solution. I build Java and Spring Boot services that need to be correct every time, and I want to bring that to payments at Adyen's scale.

At Sincro (a DealerOn company) I keep vehicle pricing accurate across automotive dealer websites, including MSRP, finance options and conditional offers, by processing real-time inventory and incentive updates from multiple vendors. I built the CI/CD pipeline to UAT and production and a Maven tool that upgrades many projects in one run. At DMG I introduced gRPC with type-safe Protocol Buffers contracts between microservices and cut latency by 30%. Earlier I integrated the Bing Automotive Inventory Ads REST API, which cut campaign setup time by 50%.

I like owning features end to end, from design through testing to production, which is how your teams work. I'm ready to relocate to Amsterdam and work office-first."""),
"ab-snowflake-6e31e0cb-7821-4dcf-9d69-0afce918bcc4": ("Snowflake", "Forward Deployed Engineer, Applied AI (Warsaw)",
"""I'm applying for the Forward Deployed Engineer, Applied AI role in Warsaw. Turning ambiguous business problems into AI agents and pipelines that run in production is the work I've been doing and want to do more of.

At Sincro (a DealerOn company) I built a Claude Code plugin that lets an agent navigate our UI and run end-to-end tests, and agent skills that give it context on our incentives pipeline. At DMG I built a skill that goes from an incident report to the likely root cause in the codebase. My core engineering is data heavy, with parsers that normalise feeds from multiple vehicle-data vendors, real-time inventory and incentive pipelines, and an LLM-assisted website migration tool that moved dealer sites into new templates without data loss.

I enjoy working directly with the people who use what I build, and I'd love to help Snowflake's customers ship AI on their data. I'm ready to relocate to Warsaw."""),
"gh-stripe-8175656": ("Stripe", "Software Engineer, Security Business Enablement (Dublin)",
"""I'm applying for the Software Engineer role on Security Business Enablement in Dublin. The mix of LLM integrations, retrieval-augmented systems and workflow automation in this role is very close to what I build today.

At Sincro (a DealerOn company) I build AI tooling with Claude Code, including agent skills that pull the right context about our build pipeline and a plugin that drives the browser for end-to-end tests. At DMG I built a skill that turns an incident description into a root-cause investigation across the codebase. I also build workflow automation for non-engineers. During our platform migration I shipped a feature that copies a dealer site's data and components into the new template, replacing manual re-entry for our operations team.

I like starting projects from scratch and measuring whether they actually work. I'd be excited to help Stripe's security and sales teams move faster, and I'm ready to relocate to Dublin."""),
"gh-databricks-8029666002": ("Databricks", "Software Engineer, Backend (Amsterdam)",
"""I'm applying for the backend Software Engineer role in Amsterdam. I build distributed Java services and data pipelines, and Databricks is where I'd like to do that at much larger scale.

At DMG, as an SDE 2, I introduced gRPC communication with type-safe Protocol Buffers contracts between microservices and reduced latency by 30% compared with REST. At Sincro (a DealerOn company) I run real-time inventory and incentive pipelines, write parsers that normalise data from multiple vendors, and built the CI/CD pipeline from build to production along with Consul-based configuration. My toolkit includes AWS, Docker, Kubernetes, PostgreSQL and SQL.

I enjoy problems that span product and infrastructure, like reliable services, monitoring and developer experience. I'd be glad to bring that to your backend teams, and I'm ready to relocate to Amsterdam."""),
}
for jid, (co, role, body) in L.items():
    assert ":" not in body, jid
    d = ROOT / "applications" / jid
    txt = f"Dear {co} Hiring Team,\n\nRe {role}\n\n{body}{SIG}"
    (d / "cover_letter.md").write_text(txt, encoding="utf-8")
    (d / "Rohit_Gande_Cover_Letter.txt").write_text(txt, encoding="utf-8")
    print(f"{co:17} {len(body.split())} words")
