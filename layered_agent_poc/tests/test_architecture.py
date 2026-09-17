"""The layer diagram is a test: import contracts in .importlinter must hold."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_layer_boundaries_hold():
    out = subprocess.run([str(Path(sys.executable).parent / "lint-imports")], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout[-2000:]
    assert "7 kept, 0 broken" in out.stdout


def test_agents_do_not_mention_models_or_transports():
    """No model name, provider option or MCP detail appears in agent code."""
    for path in (ROOT / "agent_platform" / "agents").glob("*.py"):
        text = path.read_text()
        for needle in ("gpt-oss", "qwen", "ollama", "think", "stdio", "idempotency_key"):
            assert needle not in text.lower(), f"{path.name} mentions {needle!r}"
