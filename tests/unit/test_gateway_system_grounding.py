"""BBF-86.6 — Unit tests for `narration_grounding` health component.

The gateway's `GET /v1/system/health` endpoint now reports a
`narration_grounding` component whose status reflects whether the
in-process `GroundingIndex` has any entries. Empty => `degraded`,
non-empty => `ok`. A `degraded` component flips the overall rollup
to `degraded`.

These tests don't run the FastAPI lifespan (no Stockfish, no real
GroundingIndex load against the v2 corpus); they construct
GroundingIndex instances via `base_path=None` and only feed them
in through `app.state.narration_pipeline`. Integration coverage of
the lifespan path + startup WARNING log is in
`tests/integration/test_health_endpoint_grounding.py`.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from chess_coach.gateway.auth import set_active_token
from chess_coach.narration.grounding import GroundingIndex
from chess_coach.narration.pipeline import NarrationPipeline

VALID = "unit-test-bearer"
AUTH = {"Authorization": f"Bearer {VALID}"}


@pytest.fixture(autouse=True)
def _seed_token() -> Iterator[None]:
    set_active_token(VALID)
    yield
    set_active_token(None)


def _empty_pipeline(tmp_path: Path) -> NarrationPipeline:
    """Pipeline backed by an empty GroundingIndex (corpus dir missing).

    `load_narrative_gold` for a non-existent base_path with
    `fail_on_missing=False` (the BBF-86 F2 graceful default) returns
    `[]`; we mirror that by directly instantiating an empty
    `GroundingIndex`-equivalent.
    """
    empty_index = GroundingIndex.__new__(GroundingIndex)
    # Manually populate the private fields the way __init__ would
    # in graceful-mode after a missing corpus. This bypasses the
    # disk read so the unit test runs offline.
    empty_index._version = "v2"  # noqa: SLF001 — test fixture setup
    empty_index._entries = []     # noqa: SLF001
    empty_index._by_fen = {}      # noqa: SLF001
    # Attach as the pipeline's grounding so the system router's
    # grounding_size callback can introspect it.
    fake_router = MagicMock()
    pipeline = NarrationPipeline(
        router=fake_router,
        grounding=empty_index,
    )
    # The NarrationPipeline may need explicit grounding wiring;
    # fall back to direct attribute assignment.
    if getattr(pipeline, "_grounding", None) is not empty_index:
        pipeline._grounding = empty_index  # type: ignore[attr-defined]
    return pipeline


def _populated_pipeline() -> NarrationPipeline:
    """Pipeline backed by a populated (synthetic) GroundingIndex.

    Constructs a real GroundingIndex against the v2 corpus shipped
    in BBF-87. Falls back to `_empty_pipeline` if the v2 corpus file
    is absent in the working tree (CI sandbox).
    """
    try:
        index = GroundingIndex(version="v2")
    except (FileNotFoundError, ValueError):
        return _empty_pipeline(Path("."))
    fake_router = MagicMock()
    pipeline = NarrationPipeline(
        router=fake_router,
        grounding=index,
    )
    if getattr(pipeline, "_grounding", None) is not index:
        pipeline._grounding = index  # type: ignore[attr-defined]
    return pipeline


@pytest_asyncio.fixture
async def empty_grounding_client(
    app: FastAPI, tmp_path: Path,
) -> httpx.AsyncClient:
    """Build an app whose narration pipeline has an empty GroundingIndex."""
    app.state.narration_pipeline = _empty_pipeline(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def populated_grounding_client(
    app: FastAPI,
) -> httpx.AsyncClient:
    """Build an app whose narration pipeline has a populated GroundingIndex."""
    app.state.narration_pipeline = _populated_pipeline()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver",
    ) as c:
        yield c


class TestSystemHealthGrounding:
    """BBF-86.6: health endpoint surfaces narration_grounding component."""

    async def test_grounding_component_is_present_in_response(
        self, populated_grounding_client: httpx.AsyncClient,
    ) -> None:
        r = await populated_grounding_client.get(
            "/v1/system/health", headers=AUTH,
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        names = {c["name"] for c in d["components"]}
        # The new component is registered alongside gateway + storage.
        assert "narration_grounding" in names

    async def test_populated_grounding_yields_ok_status(
        self, populated_grounding_client: httpx.AsyncClient,
    ) -> None:
        r = await populated_grounding_client.get(
            "/v1/system/health", headers=AUTH,
        )
        assert r.status_code == 200
        d = r.json()["data"]
        grounding_comp = next(
            c for c in d["components"] if c["name"] == "narration_grounding"
        )
        assert grounding_comp["status"] == "ok"
        assert grounding_comp.get("message") in (None, "")
        # Overall rollup must NOT flip to degraded for an ok component.
        assert d["status"] == "ok"

    async def test_empty_grounding_yields_degraded_status(
        self, empty_grounding_client: httpx.AsyncClient,
    ) -> None:
        r = await empty_grounding_client.get(
            "/v1/system/health", headers=AUTH,
        )
        assert r.status_code == 200
        d = r.json()["data"]
        grounding_comp = next(
            c for c in d["components"] if c["name"] == "narration_grounding"
        )
        assert grounding_comp["status"] == "degraded"
        assert grounding_comp.get("message")
        # The rollup must flip to `degraded` because the worst
        # severity is now 1 (degraded), not 0 (ok).
        assert d["status"] == "degraded"

    async def test_existing_components_still_present(
        self, populated_grounding_client: httpx.AsyncClient,
    ) -> None:
        """Backwards compat: gateway + storage still present alongside
        the new narration_grounding component. The pre-BBF-86.6
        contract was {gateway, storage}; it is now a superset."""
        r = await populated_grounding_client.get(
            "/v1/system/health", headers=AUTH,
        )
        names = {c["name"] for c in r.json()["data"]["components"]}
        assert "gateway" in names
        assert "storage" in names
        assert "narration_grounding" in names
