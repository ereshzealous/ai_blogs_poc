"""`mcpcp discover` runs either discovery profile without a model (lexical retrieval)."""

from __future__ import annotations

import json
import sys

import pytest

from control_plane import cli

REQUEST = "Get the logs for pod checkout-api-7d9f8c6b5-2kq8x."


def discover(monkeypatch, capsys, *extra):
    monkeypatch.setattr(sys, "argv", ["mcpcp", "discover", REQUEST, "--lexical-only", *extra])
    cli.main()
    return json.loads(capsys.readouterr().out)


def test_discover_defaults_to_the_published_profile(monkeypatch, capsys):
    out = discover(monkeypatch, capsys)
    assert "kubernetes.get_pod_logs" not in out["tool_ids"]
    assert all("identifier_match" in r for r in out["ranking"])


def test_discover_runs_profile_v2_for_the_given_caller(monkeypatch, capsys):
    out = discover(monkeypatch, capsys, "--discovery", "v2", "--user", "oncall-1", "--roles", "sre-oncall")
    assert "kubernetes.get_pod_logs" in out["tool_ids"]
    assert all(r["scope_ok"] is not None for r in out["ranking"])


def test_discover_rejects_an_unknown_profile(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["mcpcp", "discover", REQUEST, "--discovery", "v9"])
    with pytest.raises(SystemExit):
        cli.main()
