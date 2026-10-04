# Learning 01 POC: the same `sprawl` pipeline on any platform.
#
# The recorded runs were made natively on macOS (Apple silicon).  This image reproduces the environment for
# Linux, Windows and macOS hosts: Python 3.12.13, the locked dependencies (MCP Python SDK 2.2.0), the POC, the
# recorded evidence and the embedding-cache snapshot.  The model is never inside the image: live runs reach an
# Ollama server through --ollama-host (by default the Docker host's Ollama).
#
#   docker compose run --rm poc                      # evidence mode: verify, test and replay (no model)
#   docker compose run --rm poc run --preset quick   # a live run against the host's Ollama
FROM ghcr.io/astral-sh/uv:0.11.7 AS uv

FROM python:3.12.13-slim
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*'
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    SPRAWL_IN_CONTAINER=1 \
    SPRAWL_OLLAMA_HOST=http://host.docker.internal:11434
WORKDIR /work

# dependencies first (cached layer), then the project itself as an editable install at /work/poc
COPY poc/pyproject.toml poc/uv.lock poc/README.md poc/
RUN cd poc && uv sync --frozen --no-install-project
COPY . .
RUN cd poc && uv sync --frozen \
 && install -m 0755 /work/docker/ollama-shim.py /usr/local/bin/ollama

ENV PYTHONPATH=/work/runner
ENTRYPOINT ["python", "-m", "sprawl_cli"]
CMD ["all"]
