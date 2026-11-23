"""Print a JobFill form report compactly:  python tests/show_report.py <job_id | path-to-json>"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
arg = sys.argv[1]
p = Path(arg) if arg.endswith(".json") else ROOT / "applications" / arg / "form_report.json"
r = json.loads(p.read_text(encoding="utf-8"))
print(r.get("summary"))
for url, fr in r["frames"].items():
    print("frame:", url[:100])
    for k in ["filled", "needs", "consent", "optional"]:
        for f in fr.get(k, []):
            opts = f.get("options")
            o = (" | opts: " + "; ".join(opts[:8])[:160]) if opts and k != "filled" else ""
            print(f"  {k[:6].upper():6} {('*' if f.get('required') else ' ')} {f['label'][:70]:70} [{f.get('key')}] {f.get('value', '')[:50]}{o}")
