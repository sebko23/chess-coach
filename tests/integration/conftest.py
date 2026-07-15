"""Shared pytest fixtures for integration tests under tests/integration/.

Mirrors the pattern in tests/perf/conftest.py: certain integration
tests deliberately need real external services (a live Qdrant, the
gateway with full lifespan, etc.) and must bypass the top-level
tests/conftest.py autouse `_isolate_env` fixture, which would
otherwise strip CHESS_COACH_* env vars and force a private tmp_path
data dir.

The default `_isolate_env` fixture is fine for unit tests that want
to mock the gateway in-process. The tests in tests/integration/
that need real services opt out by using the fixtures defined here.

Marker convention: tests in this directory should carry either
`@pytest.mark.integration` or `@pytest.mark.smoke` (defined in
pyproject.toml). The --strict-markers addopts means a test with no
marker will be rejected.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI


# Tests in tests/integration/ that need a live Qdrant set the env
# var CHESS_COACH_QDRANT_URL before invoking pytest. The autouse
# _isolate_env fixture in tests/conftest.py would strip it; this
# fixture re-installs the pre-test value into the monkeypatch'd env.
#
# The `request` fixture lets us read the captured value and re-set
# it after _isolate_env runs. Without this, the GatewaySettings()
# call inside tests/integration/test_kb_qdrant_live.py reads from
# the (now-stripped) env and returns qdrant_url=":memory:".

@pytest.fixture(autouse=True)
def _restore_qdrant_env(request, monkeypatch) -> Iterator[None]:
    """Re-install CHESS_COACH_QDRANT_URL after tests/conftest.py strips it.

    The pytest CLI is invoked with `CHESS_COACH_QDRANT_URL=...` set in
    the qdrant-smoke job (see .github/workflows/smoke.yml). The top-level
    autouse fixture wipes it before the test body runs; we put it back
    so the test can actually use the sidecar.
    """
    saved = getattr(request, "config", None)
    # The env var that was set before pytest's collection phase
    # is captured by monkeypatch automatically -- but the top-level
    # _isolate_env has already called delenv on it. We re-set it
    # from os.environ (which still has the pre-test value because
    # monkeypatch.delenv doesn't touch the parent process env).
    qdrant_url = os.environ.get("CHESS_COACH_QDRANT_URL")
    if qdrant_url:
        monkeypatch.setenv("CHESS_COACH_QDRANT_URL", qdrant_url)
    qdrant_key = os.environ.get("CHESS_COACH_QDRANT_API_KEY")
    if qdrant_key is not None:
        monkeypatch.setenv("CHESS_COACH_QDRANT_API_KEY", qdrant_key)
    yield


@pytest.fixture
def settings():
    """GatewaySettings that reads CHESS_COACH_QDRANT_URL from env.

    The qdrant-smoke CI job sets this env var via the `env:` block
    on the pytest step. Local `pytest tests/integration/` runs will
    see the default (":memory:") unless the dev sets the var.
    """
    from chess_coach.gateway.config import GatewaySettings

    return GatewaySettings()


@pytest.fixture
def app(settings):
    """FastAPI app with the live env-driven settings."""
    from chess_coach.gateway import create_app

    return create_app(settings)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c