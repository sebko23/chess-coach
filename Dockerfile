# CHESS COACH backend -- single-image Docker build.
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
# BBF-52: the HEALTHCHECK below was fixed (Bearer *** -> Bearer
# devtoken123). The old *** marker was a TODO that was never
# replaced; the healthcheck always 401'd, .State.Health.Status
# never reached "healthy", and any docker-compose healthcheck
# gating broke. The CI smoke workflow had already worked around
# this with a direct curl loop (BBF-38), but `docker compose up`
# users saw a perpetually "unhealthy" backend. Fix is one line.

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
# wget: used by the qdrant healthcheck in docker-compose.yml.
# tini: PID 1 that reaps zombies and forwards signals. Critical
# for `docker stop` (sends SIGTERM, must reach uvicorn).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        stockfish \
        ca-certificates \
        curl \
        wget \
        tini \
        poppler-utils \
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
#
# BBF-sec-03: bump from 0.4.18 to 0.11.28 so the install line below
# can use `uv sync --frozen`. The new pin matches the version used
# by the local dev environment, so local-vs-CI behavior is consistent.
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /usr/local/bin/

WORKDIR /app

# ---- Python deps ----
# Split the COPY+RUN layers so that source-only changes don't
# re-trigger the full `uv sync` resolver pass. The first layer
# (pyproject + uv.lock) only changes when deps change; the second
# layer (libs/ services/ apps/) changes on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra dev

COPY libs/ ./libs/
COPY services/ ./services/
COPY apps/ ./apps/

# Install the package editable. No `--no-deps` because we want the
# runtime deps (fastapi, uvicorn, aiosqlite, etc.). The layered
# split above means this RUN only re-executes on source changes.
# BBF-sec-03: `--no-install-project` on the sync layer keeps sync
# from trying to install the editable project twice; this line
# handles the editable install. The lock is the source of truth
# (tracked in BBF-sec-03); the build fails loudly when the lock is
# stale.
RUN uv pip install --system --no-cache -e .

# BBF-86.7: BUILD_ARG version flags for the gold corpora. Defaults
# match what the loaders expect today (v2 narrative, v0 archetype).
# Future versions can override at build time:
#   docker build --build-arg NARRATIVE_VERSION=v3 --build-arg ARCHETYPE_VERSION=v0 .
# The Dockerfile COPY paths use the args so the shipped artifact
# matches the build-time intent. The loaders' advisory version
# check (libs/chess_coach/datasets/*_gold.py) logs a WARNING if
# the requested version doesn't match the corpus _metadata.version.
ARG NARRATIVE_VERSION=v2
ARG ARCHETYPE_VERSION=v0

# BBF-87.1: copy the v2 narrative gold corpus into the image.
# The narration pipeline loads GroundingIndex(version="v2") at
# startup, and the corpus must be reachable at the path the
# loader resolves to (tests/gold/narrative/v2/corpus.json
# relative to the repo root). Production deployments without
# this COPY would FileNotFoundError at gateway startup.
COPY tests/gold/narrative/${NARRATIVE_VERSION}/ /app/tests/gold/narrative/${NARRATIVE_VERSION}/

# BBF-87.1.y follow-up: copy the v0 archetype gold corpus into
# the image. The kNN classifier at services/chess_coach/profile/
# archetypes.py loads the v0 corpus (auto-derived in BBF-88.x) at
# startup per the brief's "ship v0 alongside v1, default for new
# code" decision. Without this COPY, gateway startup would
# FileNotFoundError when the kNN classifier attempts to load
# its reference vectors.
COPY tests/gold/archetypes/${ARCHETYPE_VERSION}/ /app/tests/gold/archetypes/${ARCHETYPE_VERSION}/

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
# CHESS_COACH_BACKEND_TOKEN). BBF-52 fixed this from the previous
# Bearer *** placeholder.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:18080/v1/system/health \
        -H "Authorization: Bearer devtoken123" || exit 1