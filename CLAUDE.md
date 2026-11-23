# JobInJapan - autonomous job-search runbook

You (Claude) operate this pipeline for Rohit Gande: find software-engineering jobs abroad that
pay >= 40 LPA and sponsor visas, tailor his LaTeX resume per job to an ATS score >= 95, and
prepare applications. Rohit has ~2 years experience (Java/Spring Boot, Python, JS, LLM agents).

## Target roles (Rohit's choice, 2026-11-01)
Only Software Engineer / SDE 2 / Software Engineer II / Backend or Full-stack Engineer / Forward Deployed Engineer (FDE).
Never QA, test, SDET, automation-engineer, DevOps/SRE, data-engineer, frontend-only, junior/new-grad, or Staff+ roles.
Experience: ~3 years full-time (Sincro x2, DMG SDE 2) -> mid-level.

## Hard rules (never break)
1. **Never fabricate.** Tailoring may reword, reorder, emphasise and surface skills listed in
   `resume/skills_bank.json -> confirmed`. Never add employers, titles, dates, metrics, or skills
   that are not there. Items in `to_confirm` need Rohit's OK first - ask him, don't assume.
2. If the honest maximum score for a job is < 95, do NOT pad the resume. Record the gap in the
   job's notes (`python src/app.py status <id> skipped "gap: Kotlin, Kubernetes"`) and move on.
   Jobs at 90-94 with only 1 small gap may be marked `shortlisted` for Rohit to decide.
3. **Submitting:** since 2026-11-02 Rohit gives standing approval to submit application forms for jobs that pass
   these rules once every required field is filled truthfully (`needs_input: 0`). Stop and leave the job `ready`
   for him if a CAPTCHA/bot check appears (never bypass it) or a question has no truthful answer on file.
   Never send email/messages on his behalf without explicit approval in the session.
   EEO answers (his own, in `data/answers.json` eeo_* rules): Male, Asian (Indian), not a protected veteran,
   heterosexual, not transgender. Never guess other demographic answers; they default to decline.
4. Skip jobs whose JD says no sponsorship / requires local work rights / EU citizenship / clearance,
   or that require Japanese/German fluency (scorer reports `language_requirements`).
5. Resume must stay 1 page (`pages` in score.json) and keep master.tex formatting.

## Each cycle
1. `python src/fetch_jobs.py` - refresh `data/jobs.csv` (new jobs get status `new`).
2. `python src/report.py --n=15` - pick the top new jobs (sponsorship yes > unknown, tier A > B,
   higher base score first). Max ~5 tailored applications per cycle - quality over volume.
3. For each chosen job:
   - `python src/app.py prepare <job_id>`; read `applications/<id>/jd.txt`.
   - Fill forms from `data/profile.json` (DOB, CTC, notice, salary asks per country, etc.).
   - Check salary: target >= 40 LPA (~EUR 40k / JPY 7M / GBP 34k / PLN 170k / SGD 60k gross); Rohit's hard floor is 30 LPA.
     Most tier A/B roles in DE/NL/IE/UK/SG/Nordics clear this; for Japan check the posting.
   - Edit `applications/<id>/resume.tex`: mirror the JD's exact keyword spellings
     (e.g. "RESTful APIs", "Spring Boot", "microservices"), tune Summary to the job title,
     reorder skills so the JD's skills come first, reword bullets to use JD vocabulary - truthfully.
   - `python src/app.py build <job_id>` first with the untouched master copy. **Rohit's rule: if the score is < 80,
     tailor resume.tex to the JD** (summary aimed at the role, JD-first skill order, JD vocabulary in true bullets) and
     rebuild; aim as high as honestly possible (95 ideal). If >= 80, the master copy may be used as-is.
   - Skip jobs needing 5+ years (`req_years` column) or saying "local candidates only" / "no relocation".
   - Write `applications/<id>/cover_letter.md` (<= 200 words, specific to company + role, truthful).
   - `python src/app.py status <job_id> ready "ATS 96.2"` (or skipped/shortlisted with reason).
4. Append a short summary of the cycle to `data/run_log.md` (date, jobs fetched, ready list, gaps seen).
5. Track recurring gaps across jobs; suggest to Rohit which skill to learn next (top gaps so far:
   Kubernetes, CI/CD, Kafka, TypeScript, distributed systems, observability, Go).

## Autopilot (default since 2026-11-02, zero tokens in the normal path)
- `tools/autopilot.cmd` runs every 2 hours (Task Scheduler "JobInJapan Autopilot"): answers queued questions with one
  short `claude -p` (prompt `tools/answer_needs.md`, only if `data/needs_queue.json` is not empty), then
  `python src/autopilot.py` fetches jobs, picks eligible ones (mid level, <= 4 yrs, sponsorship not "no", no
  Japanese/German fluency, published salary >= 30 LPA, max 2 per company per 30 days, OpenAI 5/180 days, 1 per company
  per run, `per_run`/`per_day` caps in config.json "autopilot"), tailors with `src/auto_tailor.py` (truthful skill
  reorder + summary variant + template cover letter), fills with the extension in its own Chromium profile
  (`data/autopilot_profile`) and verifies 0 open questions. It does NOT click Submit by default: on 2026-11-02 every
  automated submit got an Ashby CAPTCHA or a Greenhouse emailed security code (never bypass these). Clean forms go
  to Rohit's submit queue: `python src/submit_queue.py` (list) / `python src/submit_queue.py open 10` (opens the
  forms in his Chrome; JobFill fills them; he clicks Submit). JobFill sees the confirmation page and calls the
  server's `/applied` -> status `applied` + `data/applied_log.csv`. (`--submit` / config autopilot.submit=true
  still tries automated submits.)
- Auto-submit (Rohit, 2026-11-02: "i really dont want to submit them on own"): step 3 of `tools/autopilot.cmd` runs
  `python src/submit_queue.py auto 8`, which opens queued forms in Rohit's own Chrome (max 2 tries per job). The server
  sets `ctx.autosubmit` for `to_submit` jobs; JobFill clicks Submit itself after the form is stable with 0 needs, no
  required consent open and the resume attached, then closes the tab once the confirmation is seen (ledger how =
  `jobfill-auto`). A CAPTCHA / emailed code is never touched: that tab stays open for Rohit. Disable with config.json
  autopilot.chrome_submit=false. `tools/answer_needs.md` now decides stuck questions for him (conservative, truthful).
- Outcomes: queued (`to_submit` in `data/autopilot_state.json`), needs -> `data/needs_queue.json` (retried after
  answers), required consent it can't accept -> left `ready` with a note for Rohit, closed -> `closed`.
  Questions only Rohit can answer go to `data/questions_for_rohit.md`. Logs: `data/logs/autopilot-*.log`, screenshots
  `data/logs/shots/`. Test without submitting: `python src/autopilot.py --dry-run --job <id>`.
- When working interactively, check `data/questions_for_rohit.md` and jobs with "autopilot:" notes first.

## Filling forms: JobFill extension (token-cheap path, use this first)
- `extension/` = Chrome extension (load unpacked). `src/autofill_server.py` (localhost:8765, auto-starts via
  Startup folder) serves profile.json + data/answers.json + the job's tailored PDF/cover letter (matched by URL).
- When an application page opens, the extension fills everything it knows, uploads resume + cover letter, and
  writes `applications/<id>/form_report.json` (`needs` = required + unanswered, `consent` = Rohit ticks these).
- Your job: read `form_report.json` only (not the page), write answers for `needs` into
  `applications/<id>/answers.json` as `{"exact question text": "answer"}` (style rules apply: no colons in
  paragraphs, truthful), then trigger a refill: `window.postMessage({jobfill:"refill"}, "*")` via javascript_tool,
  or Rohit clicks Refill in the panel. Re-read form_report.json to confirm `needs_input: 0`.
- Generic answers that apply to many forms go in `data/answers.json` (regex rules; never add consent answers).
- Acknowledgements (Rohit's request, 2026-11-02): the `ack` rule in `data/answers.json` ticks plain "I have read /
  acknowledge / privacy notice" boxes (panel lists them as "Acknowledged for you"). Its `not` list keeps marketing,
  talent pool, SMS/WhatsApp, interview recording, demographic data, legal/criminal and "true and accurate"
  declarations for Rohit. The extension never clicks Submit.
- Learning: answers Rohit types/picks himself (real keystrokes/clicks only) go to the server's `/learn`. Short and
  choice answers -> `data/learned.json` (reused on every form for the same question, edit/delete freely); long free
  text or questions naming the company -> that job's `applications/<id>/answers.json`. Profile basics (name, email,
  phone...) are not learned - change `data/profile.json` instead.
- Corrections: when Rohit changes a value the extension filled, his value is kept (Refill never overwrites it) and
  if a generic rule produced it (e.g. `eeo_gender`, `eeo_ethnicity`, `eeo_veteran`, `relocate`), the new answer
  replaces that rule everywhere (`data/learned.json -> overrides`), with wording variants (Male/Man,
  Indian/South Asian/Asian). Rules with placeholders ({job_city}, {salary_ask}) only learn for that one job.
- Tests: `python tests/test_learn_ack.py` (ack ticking + learning) and `python tests/test_learn_correction.py`
  (correct a filled dropdown -> learned -> reused in a fresh tab). Both restore data files afterwards.
- Tests: `python tests/test_extension.py [name]` (live forms, headless, never submits); `python tests/show_report.py <id>`.

## Statuses
new -> shortlisted -> tailored -> ready -> applied -> interview -> offer | rejected | skipped | closed
