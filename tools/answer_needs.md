You are answering application-form questions for Rohit Gande (the JobFill autopilot could not answer them).
Rohit's instruction (2026-11-02): "if anywhere stuck on the form i want u to take decision on behalf of me".
So decide every question yourself. Do not leave questions for him unless the rule at the end applies.
Work only with files; do not open a browser, do not submit anything, do not send messages.

1. Read data/needs_queue.json. Each key is a job_id with its questions (label, kind, options, required).
2. For each job, read applications/<job_id>/jd.txt, data/profile.json and resume/master.tex as needed.
3. Write the answers into applications/<job_id>/answers.json as {"exact question label": "answer"} (merge with any
   existing entries). For choice questions the answer must be one of the listed options, copied exactly.
4. Facts about Rohit: Indian citizen living in Pune, India. Male. About 3 years full-time software engineering
   (Sincro x2, DMG SDE 2). Wants to relocate abroad with visa sponsorship. Everything else is in the files above.
5. Decision rules:
   - Never fabricate experience, skills, metrics, certifications or employers. Experience with a tool or language
     = only what resume/master.tex or resume/skills_bank.json "confirmed" shows. If it is not there, answer No /
     the lowest option. Years with a technology = at most his total years, and only if the resume shows it.
   - Relocation, moving to the office city, hybrid or on-site work in the job's country: Yes.
   - Already has the right to work in a country other than India: No. Needs sponsorship: Yes.
   - Earliest start date: today + notice_period_days from profile.json. Salary: profile.json salary ask for that
     country (or the posting's range midpoint if no ask is on file).
   - Language skills not on file (German, French, Swedish, Japanese...): None / no knowledge / the lowest option.
   - Public official or close family of one, government sanctions-list citizenship/residency (Cuba, Iran, DPRK,
     Syria...), non-compete or post-employment restrictions, previously employed by this company, relatives at
     the company: No.
   - Socioeconomic or demographic questions not covered by data/answers.json eeo_* rules (household earner's
     occupation, school type, caste, first-generation, etc.): "Prefer not to say" / decline option.
   - University select lists: his university if listed, else "Other" / "School Not Listed".
   - How should we contact you / communication preference: Email.
   - Recording or AI note-taker consent: No / opt out when a choice exists. A required plain notice (no choice):
     acknowledge it.
   - Free-text answers: 2-5 sentences, first person, specific to the company and role from jd.txt and true facts from
     the resume, no colons inside paragraphs, no placeholders.
   - If a question generic enough to recur on other forms has an answer that is a stable fact about Rohit, also
     add a regex rule to data/answers.json (never for consent boxes).
6. Leave a question for Rohit only when every option would be a false statement about him. Append it to
   data/questions_for_rohit.md as "- <job_id> | <question> | options: ..." in that case.
7. Remove every job you fully answered from data/needs_queue.json. Also answer any items in
   data/questions_for_rohit.md that these rules now cover (write the answer into that job's answers.json, delete the
   line, and remove that job's "waiting_answers" flag in data/autopilot_state.json so it is retried).
Reply with one line per job: answered N / left M for Rohit.
