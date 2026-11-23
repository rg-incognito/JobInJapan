# One unattended job-search cycle: fetch -> filter -> score -> tailor -> cover letters -> log.
# Runs headless (no browser), so it PREPARES applications; form filling + submission happens in an
# interactive Claude Code session with Chrome ("submit the ready applications").
# Registered as Windows Scheduled Task "JobInJapan" (every 6 hours).
Set-Location $PSScriptRoot
$log = "data\logs\cycle_$(Get-Date -Format yyyyMMdd_HHmm).log"
New-Item -ItemType Directory -Force "data\logs" | Out-Null
$prompt = "Run one job-search cycle exactly as described in CLAUDE.md. Prepare at most 5 new applications (status ready). Do not open a browser and do not submit anything. Append a summary to data/run_log.md."
& "$env:USERPROFILE\.local\bin\claude.exe" -p $prompt `
  --permission-mode acceptEdits `
  --allowedTools "Bash(python *)" "PowerShell(python *)" "Read" "Edit" "Write" "Glob" "Grep" *> $log
