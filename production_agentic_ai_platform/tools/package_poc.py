"""The POC package for independent verification: release/production-agentic-ai-platform-poc.zip (make poc-zip).

    python3 tools/package_poc.py

One implementation: the POC's own publication package (production_agentic_ai_platform: uv run pap package, which writes
dist/production-agentic-ai-platform-poc.zip with REDACTIONS.json and PACKAGE-SHA256SUMS, scanned after redaction). This
copies it, and its SHA-256, to release/ for the article repository.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "production_agentic_ai_platform"
NAME = "production-agentic-ai-platform-poc.zip"

if subprocess.run(["uv", "run", "--project", str(POC), "python", "tools/package_proof.py"], cwd=POC).returncode:
    sys.exit(1)
(ROOT / "release").mkdir(exist_ok=True)
for f in (NAME, NAME + ".sha256"):
    shutil.copy2(POC / "dist" / f, ROOT / "release" / f)
print(f"release/{NAME} ({(ROOT / 'release' / NAME).stat().st_size // 1024} KB) · {(ROOT / 'release' / (NAME + '.sha256')).read_text().split()[0]}")
