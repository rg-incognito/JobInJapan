"""Prepare jobs and print JD snippets around sponsorship / language / years keywords.
Usage: python tools/scan_jd.py <job_id> [<job_id> ...]"""
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ['sponsor', 'visa', 'relocat', 'citizen', 'clearance', 'vetting', 'German', 'Japanese', 'French',
        'years', 'local', 'work permit', 'right to work', 'salary', '€', 'B2B', 'freelance', 'based in', 'eligib']
for i in sys.argv[1:]:
    subprocess.run([sys.executable, str(ROOT / "src" / "app.py"), "prepare", i], capture_output=True)
    t = (ROOT / "applications" / i / "jd.txt").read_text(encoding="utf-8")
    print("===", i, "len", len(t))
    for k in KEYS:
        for m in list(re.finditer(re.escape(k), t, re.I))[:2]:
            print("  [%s]" % k, re.sub(r"\s+", " ", t[max(0, m.start() - 110):m.end() + 110]))
