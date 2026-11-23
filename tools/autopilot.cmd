@echo off
rem JobFill autopilot - run by Windows Task Scheduler every 2 hours ("JobInJapan Autopilot").
rem 1) answer questions queued by the previous run (one short Claude run, only when the queue is not empty)
rem 2) fetch, tailor, fill and submit the next batch of jobs
cd /d C:\Users\rohit\Desktop\JobInJapan
if not exist data\logs mkdir data\logs
set PYTHONIOENCODING=utf-8
"C:\Python314\python.exe" -c "import json,sys; q=json.load(open('data/needs_queue.json',encoding='utf-8')); sys.exit(0 if q else 1)" 2>nul
if %errorlevel%==0 (
  echo [%date% %time%] answering queued questions >> data\logs\autopilot_task.log
  type tools\answer_needs.md | "C:\Users\rohit\.local\bin\claude.exe" -p --model sonnet --allowedTools "Read,Write,Edit,Glob,Grep" >> data\logs\autopilot_task.log 2>&1
)
"C:\Python314\python.exe" src\autopilot.py >> data\logs\autopilot_task.log 2>&1
rem 3) open verified forms in Rohit's own Chrome; JobFill submits them itself (CAPTCHA / code tabs stay open for him)
"C:\Python314\python.exe" src\submit_queue.py auto 8 >> data\logs\autopilot_task.log 2>&1
