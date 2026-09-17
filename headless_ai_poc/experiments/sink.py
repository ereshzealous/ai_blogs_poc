"""A stand-in for Slack's Web API: records every message the Slack adapter posts.

    python -m experiments.sink --port 8791 --log messages.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request


def create(log: Path) -> FastAPI:
    app = FastAPI()

    @app.post("/api/chat.postMessage")
    async def post(request: Request) -> dict:
        body = await request.json()
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.time(), **body}) + "\n")
        return {"ok": True}

    @app.get("/healthz")
    async def health() -> dict:
        return {"ok": True}

    return app


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--log", required=True)
    a = p.parse_args()
    uvicorn.run(create(Path(a.log)), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
