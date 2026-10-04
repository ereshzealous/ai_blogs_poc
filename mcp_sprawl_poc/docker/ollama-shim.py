#!/usr/bin/env python3
"""A minimal `ollama` for the container: `ollama list` and `ollama --version`, answered over HTTP.

The frozen harness records the model digests and the Ollama version by calling the ollama CLI (bench/runner.py,
scripts/freeze.py).  The container has no Ollama, only the API of an Ollama server reached through sprawl's
forwarder on 127.0.0.1:11434, which reports the same 12-hex model ids that `ollama list` prints.
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:11434"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.load(r)


def main() -> None:
    args = sys.argv[1:]
    if args in (["--version"], ["-v"]):
        print(f"ollama version is {get('/api/version')['version']}")
    elif args[:1] in (["list"], ["ls"]):
        print(f"{'NAME':<27}{'ID':<16}SIZE")
        for m in get("/api/tags")["models"]:
            print(f"{m['name']:<27}{m['digest'][:12]:<16}{m.get('size', 0) / 1e9:.1f} GB")
    else:
        sys.exit("ollama (container shim): only `list` and `--version` are available here; run Ollama on the host")


if __name__ == "__main__":
    try:
        main()
    except OSError as e:
        sys.exit(f"ollama (container shim): no Ollama server at {BASE} ({e.__class__.__name__}); pass --ollama-host")
