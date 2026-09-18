"""Repository paths used by the control plane, benchmark and CLI."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = REPO_ROOT / "benchmark" / "catalogs"
CACHE_DIR = REPO_ROOT / "benchmark" / ".cache"
# Policy v1 is the published policy and never changes; v2 adds argument-aware rules. The latest is the default.
POLICY_FILES = {"v1": REPO_ROOT / "control_plane" / "policy" / "policies.yaml",
                "v2": REPO_ROOT / "control_plane" / "policy" / "policies_v2.yaml"}
LATEST_POLICY = "v2"
POLICY_FILE = POLICY_FILES["v1"]
SCENARIO_FILE = REPO_ROOT / "mock_data" / "inc4917" / "scenario.yaml"
