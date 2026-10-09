"""experiment-runner: the shared parts of the Production AI Engineering POC runners.

Each POC's command-line module (``<poc>_cli/cli.py``) lists its commands as short functions; this package supplies
what every POC needs: headings and ok/FAIL marks, running a step in the POC's own environment (printed as it runs),
compare-and-restore, recorded-evidence guards, the pipeline with --skip and --keep-going, and an Ollama relay.
Standard library only.  A pinned copy lives in each POC repository (``runner/experiment_runner``); the source is
claude/ai/experiment-runner.  Do not edit the copy: change the template and re-copy it (check.py reports drift).
"""

from . import ollama  # noqa: F401
from .runner import FAIL, INFO, MARK_W, OK, WARN, Runner, head, paint, say  # noqa: F401

__version__ = "1.1.0"
