# CHESS COACH backend — single-image Docker build.
#
# BBF-28: the backend now runs without the agentZero container.
# This Dockerfile builds an image that boots the gateway on
# 0.0.0.0:18080, with Stockfish installed via apt. New dev workflow:
#
#   cd <repo>
#   docker compose up --build
#   curl -sS http://127.0.0.1:18080/v1/system/health \
#     -H "Authorization: Bearer devtoken123"
#
# The compose file is at the repo root as docker-compose.yml. The
# data directory is bind-mounted to a host directory (default
# ./data) so the SQLite DB and runtime descriptor survive container
# restarts.
#
# BBF-29 will add a Python smoke test that runs against this image.

# ---- build stage: nothing to compile, single-stage is fine ----
# Bookworm (Debian 12) because it has stockfish in apt and matches
# pyproject's python_requires=">=3.11" via python:3.11-slim-bookworm.
FROM python:3.11-slim-bookworm

# ---- system deps ----
# stockfish: the chess engine. Apt's stockfish package puts the
# binary at /usr/games/stockfish; we symlink to /usr/local/bin so
# the gateway's default (services/chess_coach/gateway/app.py:
# stockfish_path = '/usr/local/bin/stockfish') Just Works.
# ca-certificates: lets Python's httpx + openai libraries verify
# TLS chains (otherwise the LLM narration path fails).
# curl: used by the HEALTHCHECK.
# tini: PID 1 that reaps zombies and forwards signals. Critical
# for `docker stop` (sends SIGTERM, must reach uvicorn).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        stockfish \
        ca-certificates \
        curl \
        tini \
    && ln -sf /usr/games/stockfish /usr/local/bin/stockfish \
    && rm -rf /var/lib/apt/lists/*

# ---- non-root user ----
# The gateway writes to ${CHESS_COACH_DATA_DIR} (default /data).
# Running as non-root is best practice; we chown the data dir at
# runtime via a volume.
RUN groupadd --system --gid 1000 chesscoach \
    && useradd --system --uid 1000 --gid chesscoach \
        --home-dir /data --shell /sbin/nologin \
        chesscoach \
    && mkdir -p /data && chown -R chesscoach:chesscoach /data

# ---- Python toolchain ----
# We use `uv` (https://github.com/astral-sh/uv) for fast, reproducible
# installs. Pin the version so the image is reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /uvx /usr/local/bin/

WORKDIR /app

# ---- Python deps ----
# Copy only the metadata first so Docker can cache the install
# layer. Re-running with only source changes won't re-install
# every dep.
COPY pyproject.toml ./
COPY libs/ ./libs/
COPY services/ ./services/
COPY apps/ ./apps/

# Install the package editable. No `--no-deps` because we want the
# runtime deps (fastapi, uvicorn, aiosqlite, etc.). The `.[dev]`
# extra is NOT used in production; it's only for tests.
RUN uv pip install --system --no-cache -e .

# ---- runtime config ----
ENV CHESS_COACH_HOST=0.0.0.0 \
    CHESS_COACH_PORT=18080 \
    CHESS_COACH_DATA_DIR=/data \
    CHESS_COACH_BACKEND_TOKEN=devtoken123 \
    CHESS_COACH_MAX_WORKERS=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER chesscoach:chesscoach
WORKDIR /data

EXPOSE 18080

# tini as PID 1. Forwards SIGTERM/SIGINT to the gateway, reaps
# zombies, exits with the right code. Without tini, `docker stop`
# takes 10 seconds (the default SIGTERM grace period) because
# uvicorn doesn't get the signal.
ENTRYPOINT ["/usr/bin/tini", "--"]
# The entry point script is chess-coach-gateway, installed by
# `uv pip install -e .` (see [project.scripts] in pyproject.toml).
CMD ["chess-coach-gateway"]

# Healthcheck: requires the dev token. `curl` is in the apt deps
# above. The gateway's /v1/system/health endpoint requires bearer
# auth, so we set Authorization: Bearer devtoken123 (matching
# CHESS_COACH_BACKEND_TOKEN).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:18080/v1/system/health \
        -H "Authorization: Bearer devtoken123" || exit 1
