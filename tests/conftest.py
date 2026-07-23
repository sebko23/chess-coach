"""Shared pytest fixtures.

Fast unit tests do not boot uvicorn: we use ``httpx.AsyncClient`` with
``ASGITransport`` directly against the FastAPI app. This sidesteps real
sockets and keeps each test ~ms-fast.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Force every test to use a private CHESS_COACH_DATA_DIR.

    Also clears the few CHESS_COACH_* env vars that could leak from the host.
    """
    for k in list(os.environ):
        if k.startswith("CHESS_COACH_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CHESS_COACH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHESS_COACH_LOG_LEVEL", "WARNING")
    return tmp_path


@pytest.fixture
def settings(_isolate_env: Path):
    """Fresh GatewaySettings reading from the isolated env."""
    from chess_coach.gateway.config import GatewaySettings

    return GatewaySettings()


@pytest.fixture
def app(settings) -> FastAPI:
    """FastAPI app with lifespan disabled-by-default for unit tests.

    Tests that need lifespan side effects (migrations, descriptor) wrap the
    app in :class:`httpx.LifespanManager`-equivalent; the simpler tests just
    call routes through ASGITransport without lifespan and pre-set the token
    via :func:`chess_coach.gateway.auth.set_active_token`.
    """
    from chess_coach.gateway import create_app

    return create_app(settings)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c
