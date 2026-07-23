"""Integration tests for BBF-65 archetype cluster via the
/v1/profile/{player}/explain/archetypes endpoint.

Uses httpx.ASGITransport + AsyncClient (matches the BBF-64.3 pattern) and
patches ``cluster_archetypes`` at the route module so the handler sees
deterministic results without real DB / engine calls beyond the metrics
that the route computes upstream.

The route is /v1/profile/{player}/explain/{metric_id}; metric_id=archetypes
takes the special-case path that calls cluster_archetypes(metric_values)
and returns the ArchetypeAssignment in the effect field plus the
passes_b4_gate top-level boolean (the BBF-65.2 field).

Note (BBF-79.x sweep): the tmp_path SQLite DB schema and the auth token
activation are now provided by the shared autouse fixtures in
tests/integration/conftest.py (_integration_db and _integration_auth).
The per-file fixtures that BBF-79 originally added have been
superseded by the shared conftest fixtures.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from chess_coach.gateway.app import create_app
from chess_coach.profile import ArchetypeAssignment
from chess_coach.profile.effect_size import EffectSize

# BBF-66: mark all tests in this file as slow (~3 min each due to real DB +
# 6 upstream metric computations per route invocation). Excluded from PR CI;
# runs nightly. See CONTRIBUTING.md for marker semantics.
pytestmark = pytest.mark.slow

AUTH = {"Authorization": "Bearer devtoken123"}


@pytest.fixture
def fastapi_app():
    """FastAPI app with CHESS_COACH_DATA_DIR pointing at a tmp_path
    containing the production schema (via the shared _integration_db
    autouse fixture in tests/integration/conftest.py). The bearer
    token is also activated by the shared _integration_auth fixture."""
    return create_app()


def _fake_assignment(label="Tactician", confidence=0.7,
                     passes_gate=True) -> ArchetypeAssignment:
    return ArchetypeAssignment(
        label=label,
        confidence=confidence,
        archetype_scores={
            "Tactician": 0.85, "Positional Player": 0.20, "Grinder": 0.15,
            "Wildcard": 0.10, "Specialist": 0.05, "Tilter": 0.05,
            "Endgame Specialist": 0.05, "Unknown": 0.0,
        },
        effect_size=EffectSize(
            point_estimate=confidence,
            d=0.6,
            ci_low=0.5,
            ci_high=0.9,
            sample_size=8,
            null_value=0.4,
        ),
        passes_b4_gate=passes_gate,
    )


@pytest.mark.asyncio
async def test_archetypes_route_surfaces_label_and_gate(fastapi_app):
    """The route must surface label + passes_b4_gate (the BBF-65.2 field)
    in its response body."""
    with patch("chess_coach.profile.cluster_archetypes",
               return_value=_fake_assignment(label="Tactician", passes_gate=True)):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/profile/ebassti/explain/archetypes",
                                 headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effect"]["label"] == "Tactician"
    assert body["passes_b4_gate"] is True


@pytest.mark.asyncio
async def test_archetypes_route_subthreshold_label_can_still_surface(fastapi_app):
    """A subthreshold archetype assignment should still include the label
    (the route surfaces the raw data; the UI decides whether to render
    'Inconclusive' based on passes_b4_gate).

    The mocked assignment has passes_b4_gate=False; the route must surface
    that exact boolean (not re-derive it from the EffectSize).
    """
    with patch("chess_coach.profile.cluster_archetypes",
               return_value=_fake_assignment(label="Wildcard", confidence=0.4,
                                             passes_gate=False)):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/profile/ebassti/explain/archetypes",
                                 headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effect"]["label"] == "Wildcard"
    assert body["passes_b4_gate"] is False
