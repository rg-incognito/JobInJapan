# JobInJapan — Project Overview

> An automated system that finds software-engineering jobs abroad paying **≥ 40 LPA** (hard floor 30 LPA) with **visa sponsorship**. For each job it tailors Rohit Gande's LaTeX resume to the job description, writes a cover letter and fills in the application form. A human (Rohit) only ticks the consent boxes and clicks Submit.

*Status as of 1 Nov 2026.*

---

## 1. Goal and rules

| Item | Decision |
|---|---|
| Target roles | Software Engineer, SDE 2 / Software Engineer II, Backend or Full-stack Engineer, Forward Deployed Engineer (FDE) |
| Never apply to | QA, test, SDET, automation engineer, DevOps/SRE, data engineer, frontend-only, junior/new-grad, Staff+ |
| Experience level | About 3 years full-time (Sincro ×2, DMG SDE 2), so mid-level. Skip roles requiring 5+ years (filter: ≤ 4) |
| Pay | Target ≥ 40 LPA, minimum 30 LPA |
| Visa | Must sponsor. Skip roles marked no sponsorship, local candidates only, EU citizens only, security clearance, B2B/freelance contracts, or Japanese/German fluency required |
| Country priority | Germany → Netherlands → Japan → Poland → Ireland (UK, Singapore, Finland and others are also accepted) |
| Resume | One page, LaTeX, ATS score ≥ 95 ideal. **Tailor whenever the score is below 80.** Never fabricate skills, metrics, titles or dates |
| Writing style | No colons inside paragraphs, no placeholders, truthful, final text ready to submit |
| Consents / legal declarations | Never ticked automatically. Rohit ticks them himself |
| Submitting | Claude submits only when every field is filled and no consent box or CAPTCHA blocks it. Otherwise Rohit clicks Submit |

---

## 2. Architecture

```
            ┌──────────────────────── every 6 h (Windows Task "JobInJapan") ────────────────────────┐
            │                                                                                        │
 companies.csv ──► fetch_jobs.py ──► jobs.csv + jd/*.txt ──► report.py (rank) ──► app.py prepare/build │
 (126 cos,         (Greenhouse, Lever,   (filters: title,        (sponsorship >      (tailored resume.tex │
  4 ATS APIs)       Ashby, SmartRecr.)    country, years,          country > tier >     → PDF, score.json, │
                                          sponsorship, language)    ATS score)           cover letter)     │
            └────────────────────────────────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼  applications/<job_id>/
 Chrome ── JobFill extension ◄──► autofill_server.py (127.0.0.1:8765) ◄── profile.json + answers.json
             │  fills known fields, uploads tailored PDF + cover letter
             └► form_report.json (only the unanswered questions) ──► Claude writes answers.json ──► Refill
                                                                                       │
                                                         Rohit ticks consents + clicks Submit ◄┘
```

---

## 3. Folder map (`C:\Users\rohit\Desktop\JobInJapan`)

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Runbook Claude follows every cycle (rules, steps, statuses, extension workflow) |
| `PROJECT_OVERVIEW.md` | This document |
| `config.json` | Filters: target countries, title include/exclude, senior keywords, no-sponsorship phrases (including B2B/freelance), sponsorship phrases, `max_required_years: 4`, country priority |
| `run_cycle.ps1` | Headless `claude -p` cycle (prepares at most 5 applications; no browser, never submits). Logs go to `data/logs/` |
| `tools/tectonic.exe` | LaTeX compiler (Tectonic 0.17, XeTeX) |
| **data/** | |
| `data/companies.csv` | 126 companies: ATS, slug, careers URL, offices, sponsorship signal, tier, notes. Breakdown: Greenhouse 62, Ashby 29, Lever 7, SmartRecruiters 7, manual 21 (SAP, Zalando, Booking, Mercari, Rakuten, LY Corp, and others) |
| `data/countries.csv` | 17 countries: visa route, salary floor, typical pay, INR LPA estimate, difficulty |
| `data/jobs.csv` | Every job seen, with status history |
| `data/jd/<id>.txt` | Saved job descriptions |
| `data/profile.json` | Rohit's answers to common application questions (see §6) |
| `data/answers.json` | Regex answer bank used by the extension (see §7) |
| `data/run_log.md` | Summary of each cycle |
| `data/form_reports/` | Extension reports for pages that don't match a tracked job |
| **resume/** | |
| `resume/master.tex` / `master.pdf` | Master one-page resume (A4, 10pt, Latin Modern, ligatures and kerning off so text extracts cleanly) |
| `resume/skills_bank.json` | `confirmed` skills (allowed in tailoring) and `to_confirm` (not allowed until Rohit says yes) |
| **src/** | |
| `src/probe_boards.py` | Finds each company's board slug across the 4 ATS APIs |
| `src/fetch_jobs.py` | Pulls all boards in parallel, filters, saves JDs, computes `req_years`, sponsorship and base ATS score, writes `jobs.csv` |
| `src/ats_score.py` | Jobscan-style scorer: 75% keywords, 10% title, 15% structure. Also reports a language requirement (Japanese/German) |
| `src/report.py` | Ranks candidate jobs (`--n=`, `--country=`, `--all-levels`) |
| `src/app.py` | `prepare <id>`, `build <id>` (compile → `Rohit_Gande_<Company>.pdf` + score.json), `status <id> <status> [note]` |
| `src/tailor.py` | Applies [old, new] text replacements to an application's resume.tex |
| `src/update_projects.py` | Replaces the Projects section in the master resume and in every application resume |
| `src/cover_letters_batch1.py`, `batch2.py` | Cover letters for rounds 1 and 2 |
| `src/autofill_server.py` | Local server for the extension |
| **extension/** | JobFill Chrome extension (see §8) |
| **applications/<job_id>/** | `jd.txt`, `job.json`, `resume.tex`, `Rohit_Gande_<Company>.pdf`, `score.json`, `cover_letter.md`, `Rohit_Gande_Cover_Letter.txt`, optionally `answers.json` and `form_report.json` |
| **tests/** | `test_extension.py` (live forms, never submits), `show_report.py`, `probe_school.py`, `out/` (screenshots) |

---

## 4. Job pipeline

1. **Fetch** — `python src/fetch_jobs.py`. Sources:
   - Greenhouse: `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`
   - Lever
   - Ashby: `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true`
   - SmartRecruiters (descriptions fetched separately)

   New jobs get status `new`; jobs that disappear become `closed`.
2. **Filter** — target country; title include/exclude; required years at most 4 (the largest "N years" in the JD); sponsorship yes/unknown/no from phrase lists; B2B/freelance excluded; language requirement detected.
3. **Rank** — `python src/report.py --n=15`. Order: sponsorship, then country priority, then tier, then ATS score.
4. **Prepare** — `python src/app.py prepare <id>` copies master.tex, the JD and job.json into `applications/<id>/`.
5. **Build and score** — `python src/app.py build <id>`. If the score is below 80, tailor the resume truthfully (summary aimed at the role, the JD's skills first, the JD's wording in true bullets) and rebuild. Must stay one page.
6. **Cover letter** — at most 200 words, specific to the company and role, no colons in paragraphs.
7. **Status** — `python src/app.py status <id> ready "ATS 87.2"`.
8. **Fill and submit** — the JobFill extension, plus Claude for open questions, plus Rohit for consents and Submit.
9. **Log** — append to `data/run_log.md`.

**Statuses:** `new → shortlisted → tailored → ready → applied → interview → offer | rejected | skipped | closed`

**Automation:**
- **Scheduled task `JobInJapan`** runs `run_cycle.ps1` every 6 hours (next run: 1 Nov 2026, 11:34 PM).
- **The JobFill server** starts at logon from the Startup folder (`JobFillServer.cmd`).

---

## 5. Resume (current master)

- **Header:**
  - Pune; open to relocation (visa sponsorship required)
  - +91 9527513399 · rohitgande.work@gmail.com
  - linkedin.com/in/rohit-gande · github.com/rg-incognito · leetcode rg-incognito
- **Summary:** Software Engineer with 3+ years of experience building real-time data pipelines, gRPC/REST microservices and CI/CD for automotive platforms in Java, Spring Boot and Python, plus AI-agent developer tooling with Claude Code (plugins and skills) and LLMs.
- **Experience**
  - **Sincro, a DealerOn company** — Software Engineer, Inventory Team (Automotive), Jan 2026 – Present
    - Real-time inventory and incentive updates for the pricing box (MSRP, internet price, finance options, conditional military/senior offers)
    - Parsers for vendor data feeds
    - CI/CD on Bamboo + Bitbucket to UAT and production, with Consul property injection
    - Maven version-upgrade tool
    - Claude Code plugin that navigates the UI for end-to-end tests, plus skills for the incentives pipeline
  - **Divisions Maintenance Group** — SDE 2, Bengaluru, Jul 2025 – Dec 2025
    - gRPC + Protocol Buffers, 30% lower latency
    - Claude Code skill that investigates bugs from incident-management descriptions
    - Unit and integration tests
  - **Sincro (now a DealerOn company)** — Software Engineer, Sep 2023 – Apr 2025
    - Ad framework: 30% more engagement, 40% less manual update time
    - Bing Automotive Inventory Ads REST API integration: 50% faster setup
    - Real-time monitoring dashboards
  - **IITM** — Machine Learning Project Intern, Jun – Dec 2022: YOLOv4 sped up from 22 to 60 FPS
- **Projects**
  - **ClipForge – AI Video Editor SaaS** (May – Jun 2026): Spring Boot, Python, Next.js, PostgreSQL, Redis, Docker, Gemini LLM with multi-model fallback
  - **Website Migration Automation, Sincro to DealerOn** (Jan – Apr 2025): 10+ sites, 75%+ less effort, a copy-data-and-components feature
- **Education:** G. H. Raisoni College of Engineering and Management, Pune — B.Tech Computer Engineering, Aug 2019 – Jun 2023
- **Skills:**
  - Java, Python, JavaScript, TypeScript, SQL, Kotlin, Go
  - Spring Boot, Hibernate/JPA, Maven, Kafka, FastAPI, Flask, gRPC
  - AWS (EC2, ECR, S3, CloudWatch, Bedrock), GCP, Azure, Docker, Kubernetes, Terraform, Bamboo, Bitbucket, Consul
  - LLMs, AI agents, Claude Code, LangChain, CrewAI, RAG, prompt engineering, and more
- **Still to confirm** (`skills_bank.json → to_confirm`): HTML/CSS, Japanese/German level.

---

## 6. Profile (`data/profile.json`)

| Field | Value |
|---|---|
| Legal name / DOB | Rohit Gande / 16 Jun 2001 (eligible for the UK new-entrant salary rate until 15 Jun 2027) |
| Nationality / passport | Indian / valid until about 2033; no previous visas, no refusals |
| Location | Pune, Maharashtra, India |
| Current CTC | 12 LPA fixed |
| Minimum / target | 30 LPA / 40 LPA |
| Notice | 60 days |
| Work mode | Hybrid or onsite; family not relocating |
| Salary asks | Germany EUR 65k · Netherlands EUR 65k · Ireland EUR 70k · UK GBP 60k · Singapore SGD 90k · Poland PLN 240k · Finland EUR 60k · Japan JPY 8M |
| Scripts | Why leaving DMG (short health matter, resolved; then rehired by Sincro) · why looking now (go deeper into AI at an AI-core company, international team) · why-country text for the top 5 countries |
| Still unanswered | Team size / reports to, mentoring, CGPA, 10th/12th %, English or language test, domains to avoid, interview-time availability, reference |

---

## 7. Answer bank (`data/answers.json`)

Ordered regex rules; the first match wins. Fields:

- **`q`** — regex on the question text
- **`a`** — the text answer
- **`pick`** — regex choosing an option in dropdowns, radios or yes/no buttons
- **`avoid`** — options that must never be picked
- **`not`** — regex that disqualifies the rule
- **`type`** — what to type into search dropdowns
- **`never`** — leave the question for Rohit
- **`choice_only`** — answer only the dropdown/radio version of the question

| Rule | Answer |
|---|---|
| consent, legal | **Never answered** — privacy, terms, acknowledgements, WhatsApp/SMS, interview recording, talent pool, criminal record, clearance |
| us_person | "Citizen of a different country / None of the above" |
| sponsorship | Yes, will require sponsorship |
| work_authorization | No / "do not have work authorization" (never picks "currently hold a visa") |
| relocate, office, travel, passport | Yes |
| remote | No, will work from an office |
| current_salary | INR 12,00,000 fixed (12 LPA) |
| salary_expectation / currency | Ask for the job's country |
| office_location / job_country | The job's city / country |
| recent_employer | Sincro, a DealerOn company |
| notice | 60 days (about 2 months) |
| years_experience | 3 |
| previous_employee, referral | No |
| how_heard | Company careers page |
| eeo_gender, eeo_ethnicity, eeo_hispanic, eeo_transgender, eeo_orientation, eeo_veteran, eeo_disability, eeo_neuro, eeo_pronouns, eeo_religion | Default "decline / prefer not to say". When Rohit picks a different answer himself, it is learned per topic (`data/learned.json` → `overrides`) and used on every form, with wording variants (Male/Man, Indian/South Asian/Asian) |
| nationality / residence / located / timezone | Indian / India / Pune, Maharashtra, India / IST (UTC+5:30) |
| english | Professional working proficiency (fluent) |
| education_level, cs_degree, grad_year | Bachelor's / Yes / 2023 |
| reason_leaving, gap, why_country, cover_letter_text, dob | From the profile scripts and the job's cover letter |

**Per-job overrides:** `applications/<id>/answers.json` as `{"exact question text": "answer"}`. Claude writes these for essay questions.

---

## 8. JobFill Chrome extension

**Files**
- `manifest.json` — MV3
- `background.js` — talks to the local server; caches the profile for offline use
- `content.js` — the filler
- `popup.html` / `popup.js` — server status, auto-fill toggle, Fill now, Clear highlights

**Runs automatically on** Greenhouse (including embedded forms), Lever, Ashby, SmartRecruiters, Workday, Workable, Recruitee, Personio, Teamtailor, BambooHR, JOIN, Breezy, Jobvite and iCIMS. On any other site, use **Fill this page now** in the popup.

**How it works**
1. It detects an application form (an email or file input and at least 3 fields), including forms inside iframes and shadow DOM.
2. It asks the local server for context: profile, answer rules, the job matched by URL id, the tailored resume PDF and the cover letter.
3. It works out each field's question from its label, aria attributes, nearby text, or name/id/autocomplete, so differently named fields map to the same answer.
4. Matching order:
   - **Choice fields:** consent check → per-job answers → profile keys → answer bank.
   - **Text fields:** per-job answers → profile keys → consent check → answer bank.
   - **Long questions** (over 40 characters) go to the answer bank before profile keys.
5. Widgets it handles:
   - text and textarea (React-safe value setting)
   - native `<select>`
   - react-select and other comboboxes (opens or types, then picks an option)
   - radio groups and checkbox groups
   - Ashby yes/no buttons
   - location fields with suggestion lists
   - file uploads (tailored PDF and cover letter via DataTransfer)
   - date and number fields
6. Phone handling: if a +91 country picker exists it fills `9527513399`, otherwise `+91 9527513399`. It re-sets the number if the site reformats it.
7. Colour outlines: 🟢 filled · 🟠 needs an answer · 🟣 consent (Rohit ticks). A floating panel lists the open items; click one to jump to it.
8. It writes `applications/<id>/form_report.json`. `needs` means required and unanswered; each entry includes the dropdown options.
9. It re-runs when new fields appear (follow-up questions, SPA tab switches). It never overwrites what the user typed, **never ticks consents, never clicks Submit**, and never uploads to "autofill from resume" fields.

**Local server** (`src/autofill_server.py`, `127.0.0.1:8765`)
- Endpoints: `GET /health`, `POST /context`, `POST /report`.
- Rejects requests from web-page origins and wrong Host headers, so websites can't read the profile.

**Token-saving workflow**
1. Open the application page; the extension fills it.
2. Claude reads only `form_report.json`.
3. Claude writes `answers.json` for the `needs` items.
4. Refill: `window.postMessage({jobfill:"refill"},"*")` or the panel's Refill button.
5. Rohit ticks consents and clicks Submit.

**Install (one time)**
1. Open `chrome://extensions` and turn on Developer mode.
2. Click **Load unpacked** and choose `C:\Users\rohit\Desktop\JobInJapan\extension`.

**Tests** (`python tests/test_extension.py`, headless Chromium, live forms, never submits)

| Form | Filled | Left for Rohit |
|---|---|---|
| Stripe (Greenhouse embed) | 18 | WhatsApp opt-in, BrightHire consent |
| Adyen (Greenhouse) | 15 (incl. essay via answers.json) | Acknowledge/Confirm |
| Databricks (Greenhouse embed) | 14 | Legal declaration and its follow-up |
| Spotify (Lever) | 14 | Future-contact consent |
| Snowflake Applied AI (Ashby) | 13 | Privacy notice |
| OpenAI (Ashby) | 13 | Arbitration / privacy acknowledgements |
| Wise (SmartRecruiters) | — | Not testable headless (bot protection); use real Chrome |

**Bugs found by the tests and fixed:**
- A false work-authorization pick.
- Sponsorship questions routed to the work-authorization rule.
- "Acknowledge" not treated as consent.
- Ashby yes/no buttons skipped.
- Lever labels including every option text.
- The school dropdown reading the phone-country list ("Other" is now the fallback, because Raisoni isn't in Greenhouse's list).
- The report losing entries after React re-renders.

---

## 9. Where we are (1 Nov 2026)

**Jobs tracked:** 674
- By status: 443 new · 207 closed · 11 skipped · 3 ready · 10 applied
- Top countries: UK 170, Germany 127, Singapore 86, Spain 44, Ireland 43, Poland 37, France 35, Netherlands 31, Japan 27

### Applied (10)
| # | Company | Role | Location | ATS |
|---|---|---|---|---|
| 1 | Anthropic | Forward Deployed Engineer | London | 95.7 |
| 2 | JetBrains | Software Developer Java/Node.js | Berlin | 89.9 |
| 3 | OpenAI | Software Engineer, Privacy | Dublin | 87.1 |
| 4 | Wolt | Software Engineer | Helsinki | 85.9 |
| 5 | Stripe | Full Stack Engineer, Money Movement | London | 85.7 |
| 6 | Airwallex | Software Engineer Backend, Billing | Singapore | 83.5 |
| 7 | n8n | Forward Deployed Engineer EMEA | Berlin | 82.5 |
| 8 | Snowflake | Software Engineer | Warsaw | 80.6 |
| 9 | Scalable Capital | AI Software Engineer, Python | Berlin | 96.2 |
| 10 | Databricks | Software Engineer, Backend | Amsterdam | 81.8 |

### Ready: Rohit ticks the consent and submits
| Company | Role | Pending |
|---|---|---|
| Adyen | Java SWE, Payments (Amsterdam), ATS 87.2 | Acknowledge/Confirm, then Submit |
| Stripe | SWE Security Business Enablement (Dublin), ATS 82.2 | WhatsApp opt-in + BrightHire consent, then Submit |
| Snowflake | SWE Applied AI (Warsaw), ATS 84.2 | Privacy notice, then Submit |

Once submitted, mark each one: `python src/app.py status <id> applied`.

### Skipped (with reasons)
- Trade Republic: 5 years + Kotlin
- Mollie: 5 years, no relocation
- Wise Tallinn: local candidates only
- OpenAI FDE Munich: 5+ years
- IMC: financial-data experience required, 4+ years
- Flix ×2: B2B freelance contracts
- Woven by Toyota: business Japanese
- MongoDB SE2: Dublin-based candidates only
- Helsing: defence, Rohit's choice
- Scalable Capital: duplicate postings

### Limits to remember
- OpenAI: at most 5 applications per 180 days.
- n8n: at most 1 role per 15 days.

### Recurring skill gaps (what to learn next)
Kubernetes (hands-on), Kotlin, Go, observability, event-driven systems/Kafka in production, the payments domain.

---

## 10. Open items / next steps

1. Submit Adyen, Stripe Dublin and Snowflake Applied AI (consents), then mark them applied.
2. Load the JobFill extension in Chrome (§8).
3. Answer the remaining profile questions (§6) so more forms fill completely.
4. Review two answer-bank defaults: English = "professional working proficiency (fluent)", and office-attendance questions = "Yes" even when they mention a US office.
5. Put the degree certificate and experience letters in a `documents/` folder; some forms ask for them.
6. Japan: most target companies (Mercari, Rakuten, LY Corp, and others) use manual career pages. Check them by hand each week.
7. Test the extension on SmartRecruiters and Workday in real Chrome during the next live round.
8. Track replies and interviews (status `interview`, `offer` or `rejected` in jobs.csv).

---

## 11. Command cheat sheet

```powershell
python src/fetch_jobs.py                     # refresh jobs
python src/report.py --n=15                  # top candidates
python src/app.py prepare <job_id>           # create application folder
python src/app.py build <job_id>             # compile + score resume
python src/ats_score.py resume.pdf jd.txt --title="..."   # score manually
python src/app.py status <job_id> applied "note"
python src/autofill_server.py                # start JobFill server (auto-starts at logon)
python tests/test_extension.py [name]        # live extension tests (never submits)
python tests/show_report.py <job_id>         # what the extension filled / still needs
schtasks /Query /TN JobInJapan               # check the 6-hourly cycle
```
