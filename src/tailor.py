"""Apply a JSON list of [old, new] replacements to applications/<job_id>/resume.tex (fails loudly if any old text is missing).
python src/tailor.py <job_id> <edits.json>"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
jid, edits = sys.argv[1], json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
p = ROOT / "applications" / jid / "resume.tex"
s = p.read_text(encoding="utf-8")
for old, new in edits:
    if old not in s:
        sys.exit(f"NOT FOUND: {old[:80]}")
    s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print(f"applied {len(edits)} edits")
