"""BBF-86.6 — Integration test for the gateway health endpoint's
narration_grounding component.

Exercises the full FastAPI lifespan with a deliberately missing
narrative corpus path so the corpus load fails gracefully (BBF-86
F2). Asserts:

  1. The gateway starts despite the missing corpus.
  2. A WARNING log is emitted at the gateway logger level (BBF-86.6
     requirement: the degradation must be visible in the gateway
     startup log, not just the grounding constructor).
  3. `GET /v1/system/health` returns `status="degraded"` and the
     `narration_grounding` component is present with status
     `"degraded"` and a non-empty message.

Strategy:

  - Pre-inject `app.state.engine_pool = NoopEnginePool()` so the
    lifespan's engine-pool init branch (`if not hasattr(app.state,
    'engine_pool') ...`) skips spawning Stockfish.
  - Set `CHESS_COACH_DATA_DIR` to a fresh tmp_path so the v2
    narrative corpus path under it is guaranteed missing.
  - Run with `qdrant_url=":memory:"` (the default; kept here
    explicitly) so KB init takes the
    "skipping eager index in :memory: mode" path.
  - Drive the full lifespan via `TestClient(app).__enter__()`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chess_coach.gateway import create_app
from chess_coach.gateway.auth import set_active_token
from chess_coach.gateway.config import GatewaySettings


class _NoopEnginePool:
    """Pre-injected engine pool that skips Stockfish spawn.

    The gateway's `_lifespan` checks `app.state.engine_pool`
    before constructing the real `EnginePool`. Injecting any
    non-`None` value causes the auto-init branch to be skipped.
    The lifespan's `finally:` block calls
    `await engine_pool.shutdown()` — `NoopEnginePool` provides it.
    """

    def __init__(self) -> None:
        self.shutdown_calls = 0

    async def shutdown(self) -> None:  # noqa: D401 — async signature
        self.shutdown_calls += 1

    async def warmup(self) -> None:  # BBF-19 compatibility
        return None


def _build_settings(tmp_data_dir: Path) -> GatewaySettings:
    """Pin GatewaySettings to a private tmp data dir; Qdrant stays
    in :memory: mode (the default for local dev / CI)."""
    os.environ["CHESS_COACH_DATA_DIR"] = str(tmp_data_dir)
    os.environ.pop("CHESS_COACH_QDRANT_URL", None)
    os.environ.pop("CHESS_COACH_QDRANT_API_KEY", None)
    return GatewaySettings()


@pytest.mark.integration
class TestHealthEndpointGrounding:
    def test_missing_corpus_yields_degraded_health(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End-to-end: monkeypatch load_narrative_gold so the corpus
        load fails; run the real lifespan; hit /v1/system/health
        and assert the degraded rollup + grounding component +
        WARNING log.

        We monkeypatch instead of deleting the corpus from disk
        because the corpus ships in the repo (tests/gold/narrative/
        v2/corpus.json) and we can't safely mutate the working
        tree from a CI sandbox. A forced FileNotFoundError is the
        equivalent of "production deploy where Dockerfile COPY
        forgot the corpus" — which is the BBF-86 F2 scenario this
        health check is meant to surface.

        Note on log capture: the lifespan reconfigures root logging
        via `_configure_logging()` (app.py:92-106) which detaches
        caplog's handler. We capture stderr instead — every log
        record re-emerges through the root stderr handler that
        `_configure_logging` installs.
        """
        from chess_coach.narration import grounding as _grounding_mod

        # Force load_narrative_gold to raise FileNotFoundError,
        # exactly like a missing Dockerfile COPY would. The
        # GroundingIndex constructor (BBF-86 F2) catches this and
        # builds an empty index.
        def _boom(*_args, **_kwargs):
            raise FileNotFoundError(
                "test-forced: simulated missing narrative corpus "
                "(tests/gold/narrative/v2/corpus.json)"
            )
        monkeypatch.setattr(
            _grounding_mod, "load_narrative_gold", _boom,
        )

        settings = _build_settings(tmp_path)

        # Build the app and pre-inject a noop engine pool so the
        # lifespan takes the "engine pool pre-injected, skipping
        # auto-init" branch (app.py:121 + :168-170).
        app = create_app(settings)
        engine_pool = _NoopEnginePool()
        app.state.engine_pool = engine_pool  # type: ignore[attr-defined]

        with TestClient(app) as client:
            # The lifespan stamps the active token; pull it via the
            # gateway helper and seed the in-process token store so
            # the request passes auth.
            from chess_coach.gateway.auth import get_active_token

            token = get_active_token()
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.get("/v1/system/health", headers=headers)
            assert resp.status_code == 200, resp.text
            d = resp.json()["data"]

            # 1. narration_grounding component exists.
            components_by_name = {
                c["name"]: c for c in d["components"]
            }
            assert "narration_grounding" in components_by_name, (
                f"expected narration_grounding in "
                f"{list(components_by_name)}"
            )
            ng = components_by_name["narration_grounding"]

            # 2. Component reports degraded (size==0) with a message.
            assert ng["status"] == "degraded", ng
            assert ng.get("message"), ng
            # The message should mention grounding / corpus so an
            # operator can correlate it to the lifespan warning.
            assert (
                "grounding" in ng["message"].lower()
                or "corpus" in ng["message"].lower()
            ), ng["message"]

            # 3. Overall rollup flips to degraded.
            assert d["status"] == "degraded", d

            # 4. A WARNING log was emitted. _configure_logging
            # reinstalls a stderr handler at lifespan start, so
            # the WARNING appears on stderr.
            captured = capsys.readouterr()
            stderr = captured.err
            assert "WARNING" in stderr, (
                "expected WARNING on stderr; got:\n" + stderr
            )
            assert (
                "grounding" in stderr.lower()
                or "corpus" in stderr.lower()
            ), (
                "expected WARNING mentioning grounding / corpus; "
                "got:\n" + stderr
            )
            # The BBF-86.6 gateway-level WARNING must be present;
            # the older F2 module-level WARNING also fires. We
            # care that the gateway logger emits one.
            assert "chess_coach.gateway.app" in stderr, (
                "expected at least one WARNING from "
                "chess_coach.gateway.app; got:\n" + stderr
            )

        # Once TestClient.__exit__() runs, the lifespan's finally
        # block has executed engine_pool.shutdown(). We assert this
        # *outside* the with-block to be sure.
        assert engine_pool.shutdown_calls == 1

    def test_health_endpoint_401_without_token(
        self, tmp_path: Path,
    ) -> None:
        """Auth still required — adding a new component must not
        weaken the auth envelope."""
        settings = _build_settings(tmp_path)
        # Clear any active token so the gateway rejects unauth'd requests.
        set_active_token(None)

        app = create_app(settings)
        app.state.engine_pool = _NoopEnginePool()  # type: ignore[attr-defined]

        with TestClient(app) as client:
            resp = client.get("/v1/system/health")
            assert resp.status_code == 401
            body = resp.json()
            assert "error" in body
            assert body["error"]["code"] == "client.unauthorized"
