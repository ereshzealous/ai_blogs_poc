"""Repository paths used by the control plane, benchmark and CLI."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = REPO_ROOT / "benchmark" / "catalogs"
CACHE_DIR = REPO_ROOT / "benchmark" / ".cache"
POLICY_FILE = REPO_ROOT / "control_plane" / "policy" / "policies.yaml"
SCENARIO_FILE = REPO_ROOT / "mock_data" / "inc4917" / "scenario.yaml"
