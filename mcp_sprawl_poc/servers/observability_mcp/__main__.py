"""Run observability-mcp on its own over stdio (hand-written core tools only).

    python -m servers.observability_mcp [--manifest benchmark/catalogs/catalog_50.json]

Any MCP host can launch this command. The benchmark and gateway use the same runtime with larger manifests.
"""

import sys

from control_plane.paths import CATALOG_DIR
from servers.common import runtime

if __name__ == "__main__":
    if "--manifest" not in sys.argv:
        sys.argv += ["--manifest", str(CATALOG_DIR / "catalog_50.json")]
    sys.argv += ["--server", "observability"]
    runtime.main()
