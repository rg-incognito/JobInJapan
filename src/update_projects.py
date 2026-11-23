"""One-off: replace the Projects section in master + every application resume (2026-11-01)."""
import glob, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEW = r"""\section{Projects}
\listbegin
  \project{\textbf{ClipForge -- AI Video Editor SaaS} $|$ \emph{Spring Boot, Python, Next.js, PostgreSQL, Redis, Docker}}{May 2026 -- Jun 2026}
  \bullets
    \item Built a full-stack SaaS that turns long videos into vertical shorts: Spring Boot REST API, PostgreSQL, Redis job queue, async webhooks and a Next.js/TypeScript UI on Docker Compose.
    \item Built Python AI workers for Whisper transcription, Gemini LLM viral-moment detection (multi-model fallback), MediaPipe face-tracking 9:16 reframing and FFmpeg captions.
  \bulletsend

  \project{\textbf{Website Migration Automation (Sincro to DealerOn)} $|$ \emph{Spring Boot, Angular, Python, ChatGPT API}}{Jan 2025 -- Apr 2025}
  \bullets
    \item Built scraping and migration microservices with LLM-based layout analysis, migrating \textbf{10+} websites without data loss and cutting manual effort by \textbf{75\%+}.
    \item Added a feature that copies a dealer site's data and components into the destination DealerOn template, replacing manual re-entry by operations teams during vendor migration.
  \bulletsend
\listend

"""
for f in [ROOT / "resume/master.tex", *map(Path, glob.glob(str(ROOT / "applications/*/resume.tex")))]:
    s = f.read_text(encoding="utf-8")
    s2, n = re.subn(r"\\section\{Projects\}.*?\\listend\n\n", lambda m: NEW, s, flags=re.S)
    assert n == 1, f
    f.write_text(s2, encoding="utf-8")
    print("updated", f.relative_to(ROOT))
