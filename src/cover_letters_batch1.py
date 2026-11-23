"""Cover letters for batch 1 (2026-11-01). Each <=200 words, only facts from master resume."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIG = ("\n\nBest regards,\nRohit Gande\n+91 9527513399 | rohitgande.work@gmail.com | "
       "linkedin.com/in/rohit-gande | github.com/rg-incognito\n")
L = {
"ab-openai-fb5862cc-244c-410b-b287-47df89ad1e43": ("OpenAI", "Software Engineer, Privacy (Dublin)",
"""I'm applying for the Software Engineer, Privacy role in Dublin. Your team builds backend systems and data pipelines that turn legal requirements into reliable tooling, and that matches what I do every day.

At Sincro (a DealerOn company) I run real-time inventory and incentive data pipelines for automotive dealer sites. I write parsers that normalise feeds from multiple vehicle-data vendors and keep pricing and conditional offers (for example military or senior discounts) correct. I also built the Bamboo/Bitbucket CI/CD pipeline to UAT and production. At DMG, as an SDE 2, I moved inter-service communication to gRPC and cut latency by 30%.

You mention building tools to speed up colleagues' workflows and using AI agents in privacy engineering. I've built Claude Code skills that take an incident description and investigate the codebase for the root cause, plus a plugin that drives the browser for end-to-end tests.

I'd welcome the chance to bring that mix of data-pipeline engineering and AI tooling to OpenAI's Privacy team, and I'm ready to relocate to Dublin."""),
"gh-jetbrains-4866608101": ("JetBrains", "Software Developer, Java/Node.js (Web Development Team)",
"""I'm applying for the Software Developer role on your Web Development team. I build and own backend web services in Java/Spring Boot and Node.js on AWS, end to end.

At Sincro (a DealerOn company) I own real-time inventory and incentive services for automotive dealer websites. I built the CI/CD pipeline (Bamboo, Bitbucket) from build through UAT and production, and I added Consul-based configuration injection. I also wrote a version-upgrade tool that upgrades multiple projects in one run while keeping chosen projects on older versions. At DMG I introduced gRPC between microservices, cutting latency by 30%, and defined the proto service contracts.

You mention using AI tools and agents in development workflows. I build Claude Code plugins and skills, including one that lets Claude navigate the UI to run end-to-end tests, and one that triages bugs from incident tickets against the codebase.

I use JetBrains IDEs every day, and building the internal services behind them would be a privilege. I'm ready to relocate."""),
"gh-anthropic-5423029008": ("Anthropic", "Forward Deployed Engineer (London)",
"""I'm applying for the Forward Deployed Engineer role in London. Much of my recent engineering has been building with Claude inside a real company's systems.

At Sincro (a DealerOn company) I built a Claude Code plugin that lets Claude navigate our UI and run end-to-end tests in the browser. I also built agent skills that give Claude context on our incentives build pipeline. At DMG I built a skill that takes a bug report from the incident-management tool and investigates the local repository for the root cause. That's the kind of reusable deployment pattern you describe codifying for customers.

Alongside that I ship production software in Python and Java: real-time inventory and incentive pipelines, vendor data parsers, gRPC microservices (30% lower latency) and CI/CD to production.

I'd love to help enterprises go from first experiments to production agents. I'm open to relocating to London and to the travel the role requires."""),
"ab-airwallex-f4d64c0e-2425-409c-a296-4c4c6b9fe824": ("Airwallex", "Software Engineer Backend, Billing (Singapore)",
"""I'm applying for the Backend Software Engineer role on your Billing team in Singapore. I've spent 3+ years building Java backend systems where pricing correctness matters.

At Sincro (a DealerOn company) I process real-time inventory and incentive updates that drive vehicle pricing on dealer websites: MSRP, internet price, finance options and conditional offers. I write parsers that normalise data from multiple vendors and keep it consistent end to end. I built the Bamboo/Bitbucket CI/CD pipeline to UAT and production. At DMG, as an SDE 2, I introduced gRPC with type-safe proto contracts between microservices, reducing latency by 30%.

Billing systems need the same discipline: accurate rules, reliable pipelines and safe deployments. I'd be glad to bring that to Airwallex, and I'm ready to relocate to Singapore."""),
"gh-stripe-8226261": ("Stripe", "Full Stack Engineer, Money Movement (London)",
"""I'm applying for the Full Stack Engineer role on Money Movement in London. I build full-stack systems in Java/Spring Boot, Node.js, React and Angular, and much of my work is getting financial details exactly right.

At Sincro (a DealerOn company) I keep vehicle pricing correct on dealer websites, including MSRP, internet price, finance options and conditional offers. I do this by processing real-time inventory and incentive data and parsing feeds from multiple vendors. I built the CI/CD pipeline to UAT and production. At DMG I moved services to gRPC with strongly typed proto contracts (30% lower latency) and added unit and integration tests. Earlier I integrated the Bing Automotive Inventory Ads API, cutting ad setup time by 50%.

I'd be excited to bring that care for correctness and end-to-end ownership to Stripe's Money Movement team. I'm ready to relocate to London."""),
"ab-snowflake-d576a5a4-1409-45fa-b710-db8d52041551": ("Snowflake", "Software Engineer (Warsaw)",
"""I'm applying for the Software Engineer role in Warsaw. I build distributed backend systems in Java and Python and care about performance and reliability.

At DMG, as an SDE 2, I introduced gRPC communication between microservices with type-safe Protocol Buffers contracts, cutting latency by 30% compared with REST, and I added unit and integration tests. At Sincro (a DealerOn company) I run real-time data pipelines that process inventory and incentive updates from multiple vendors. I also built the CI/CD pipeline and a multi-project dependency-upgrade tool, and earlier I optimised a computer-vision model from 22 to 60 FPS.

I'd enjoy working on the systems behind the Snowflake platform, and I'm ready to relocate to Warsaw."""),
"ab-n8n-c9fc97fa-a473-4133-b3cb-502785649ecd": ("n8n", "Forward Deployed Engineer - EMEA",
"""I'm applying for the Forward Deployed Engineer role in EMEA. Building integrations and automation that customers actually run in production is my favourite kind of work.

At Sincro (a DealerOn company) I write parsers for multiple vehicle-data vendors and turn messy feeds into real-time inventory and incentive updates. Earlier I integrated the Bing Automotive Inventory Ads API, cutting campaign setup time by 50%. I built CI/CD from build to production and a tool that upgrades many projects in one run. At DMG I designed gRPC/proto service contracts between microservices. On the AI side, I build Claude Code plugins and skills and AI agents that automate browser workflows. My personal agent project handles over half of routine web tasks on its own.

Taking an ambiguous customer problem, shipping a working automation and turning it into a reusable pattern is exactly what I enjoy. I'm happy to travel for on-site engagements."""),
"gh-wolt-8159098": ("Wolt", "Software Engineer (Helsinki)",
"""I'm applying for the Software Engineer role in Helsinki. I've spent 3+ years building backend services and real-time data pipelines in Java, Python and Node.js.

At Sincro (a DealerOn company) I process real-time inventory and incentive updates for automotive dealer websites. I write parsers for multiple data vendors and built the CI/CD pipeline to UAT and production. At DMG, as an SDE 2, I moved inter-service communication to gRPC (30% lower latency) and added test coverage. I also build AI-agent tooling with Claude Code for end-to-end testing and bug triage.

Wolt's scale and its focus on reliable, fast-moving logistics make it a place I'd love to grow as an engineer. I'm ready to relocate to Helsinki."""),
}
for jid, (co, role, body) in L.items():
    (ROOT / "applications" / jid / "cover_letter.md").write_text(
        f"Dear {co} Hiring Team,\n\nRe: {role}\n\n{body}{SIG}", encoding="utf-8")
    print(f"{co:10} {len(body.split())} words")
