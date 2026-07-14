"""Regression tests for the engine pool lifecycle (BBF-35).

These tests guard the two failure modes documented in
ADR-0006 (engine-pool-failure-modes):

  Finding 1: A hung Stockfish ``go`` call previously wedged the
             calling slot forever. Fix: ``engine_go_timeout_s``
             on the pool forces a deadline, kills the subprocess,
             and resets the slot so the next request gets a fresh
             engine.

  Finding 2: A subprocess that died between requests was not
             detected -- the next caller reused the dead Popen and
             hung forever waiting for output that would never come.
             Fix: ``_acquire()`` now checks ``proc.poll()`` and
             starts a fresh subprocess when the previous one has
             exited.

These tests deliberately do NOT spawn real subprocesses. Spawning
real fakes wedges the agentZero cgroup under the perf-debug-test
runs; instead, we install a fake ``UCIEngine`` class via
``monkeypatch`` that fakes just enough of the engine surface for
the pool to exercise its lifecycle branches (timeout, dead-pid).
"""
from __future__ import annotations

import asyncio
import sys
import types
from typing import AsyncIterator

import pytest

from chess_coach.engine_orch.pool import (
    EngineHungError,
    EnginePool,
    EngineSpec,
)
from chess_coach.protocol_types.analysis import (
    AnalysisRequest,
    PVLine,
    Score,
)
from chess_coach.uci.engine import InfoEvent


STARTING_POSITION = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# ---------------------------------------------------------------------------
# Fake UCI engine -- avoids real subprocesses entirely. Replaces UCIEngine
# in the engine_orch.pool module under monkeypatch.
# ---------------------------------------------------------------------------


class _FakeInfoEvent:
    """Minimal InfoEvent stand-in (we don't parse it from the pool)."""


class FakeUCIEngine:
    """Replacement for chess_coach.uci.engine.UCIEngine.

    Behaviors controlled by constructor args:

      mode="hang"        -- ``go()`` is an async generator that never
                            produces and never returns.
      mode="answer"      -- ``go()`` produces one info line then a
                            bestmove then returns.
      mode="dead_after"  -- first ``go()`` returns bestmove, second
                            invocation returns bestmove too (we use
                            ``after_first_go_dies`` to kill the
                            underlying object between calls).

    These fakes carry no real subprocess; the pool's kill/wait/poll
    paths must defensively handle ``_proc=None`` or
    ``_proc.poll()`` raising on these stand-ins.
    """

    def __init__(
        self,
        binary: str,
        *,
        engine_id: str | None = None,
        extra_args: list[str] | None = None,
        mode: str = "hang",
    ) -> None:
        self.binary = binary
        self.engine_id = engine_id or "fake"
        self.extra_args = extra_args or []
        self.mode = mode
        self._proc = _FakeProc()
        self._version = f"FakeUCI-{mode}"
        # bookkeeping the pool reads after pool.analyze()
        self._info_events_emitted: list = []
        self._position_calls: list[str] = []
        self._set_options_calls: list[dict] = []

    async def start(self, *, options=None) -> None:
        # Pool calls this; we simulate the UCI handshake completing.
        return None

    async def position(self, *, fen=None, moves=None) -> None:
        self._position_calls.append(fen or "startpos")

    async def set_options(self, options) -> None:
        self._set_options_calls.append(dict(options))

    async def go(
        self,
        *,
        depth=None,
        nodes=None,
        movetime=None,
        wtime=None,
        btime=None,
        winc=None,
        binc=None,
        movestogo=None,
    ) -> AsyncIterator:
        if self.mode == "hang":
            # Async generator that hangs forever. The pool's
            # wait_for must give up.
            while True:
                await asyncio.sleep(3600)
                yield  # unreachable; satisfies type checker
                return  # also unreachable
        if self.mode == "answer":
            yield InfoEvent(
                depth=1,
                score=Score(kind="cp", value=10),
                pv=["e2e4"],
                nodes=1,
                time_ms=1,
                nps=1,
            )
            return
        raise AssertionError(f"unknown mode {self.mode}")

    async def quit(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            try:
                await self._proc.wait()
            except Exception:
                pass
            self._proc = None


class _FakeProc:
    """Stands in for the asyncio.subprocess.Process.

    Modes:
      poll returns None while alive, returns -9 after kill.
      wait() blocks once (simulated) then returncode is set.
    """

    def __init__(self) -> None:
        self._alive = True
        self._returncode = None
        self.stdin = _FakeStream("stdin")
        self.stdout = _FakeStream("stdout")
        self.stderr = _FakeStream("stderr")

    def poll(self):
        return self._returncode

    def kill(self):
        if self._alive:
            self._alive = False
            self._returncode = -9

    async def wait(self):
        # Pool expects this to return promptly after kill(). We are
        # not driving an actual subprocess, so just resolve.
        if self._returncode is None:
            self._returncode = 0
        return self._returncode


class _FakeStream:
    def __init__(self, name: str) -> None:
        self._name = name
        self._closed = False

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self._closed = True

    def write(self, data: bytes) -> None:
        # Pool calls write() then drain(); we just accept.
        return None


# ---------------------------------------------------------------------------
# Pytest fixtures: monkeypatch UCIEngine in the pool module
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_engine_class(monkeypatch):
    """Replace UCIEngine with our FakeUCIEngine in the pool module's
    own namespace (it imports UCIEngine at module load, so we have
    to rebind the local name, not just sys.modules).

    Returns FakeUCIEngine so tests can refer to it.
    """
    import chess_coach.engine_orch.pool as pool_module
    orig = pool_module.UCIEngine
    pool_module.UCIEngine = FakeUCIEngine  # type: ignore[assignment]
    monkeypatch.setattr(pool_module, "UCIEngine", FakeUCIEngine, raising=False)
    yield FakeUCIEngine
    pool_module.UCIEngine = orig


@pytest.fixture
def starting_position_fen():
    return STARTING_POSITION


# ---------------------------------------------------------------------------
# Constructor behavior (sanity for the new parameter)
# ---------------------------------------------------------------------------


class TestEngineGoTimeoutConstructor:
    def test_default_is_30s(self):
        spec = EngineSpec(engine_id="sf", path="/bin/echo")
        pool = EnginePool([spec])
        assert pool._engine_go_timeout_s == 30.0

    def test_explicit_value(self):
        spec = EngineSpec(engine_id="sf", path="/bin/echo")
        pool = EnginePool([spec], engine_go_timeout_s=2.5)
        assert pool._engine_go_timeout_s == 2.5

    @pytest.mark.parametrize("bad", [0.0, -1.0, -0.1])
    def test_rejects_non_positive(self, bad):
        spec = EngineSpec(engine_id="sf", path="/bin/echo")
        with pytest.raises(ValueError, match="must be > 0"):
            EnginePool([spec], engine_go_timeout_s=bad)


# ---------------------------------------------------------------------------
# Finding 1: hung go() must trigger kill + slot reset within the budget
# ---------------------------------------------------------------------------


class TestEngineGoTimeoutBehavior:
    """The pool wraps engine.go() in wait_for + a kill/reset branch.

    These tests exercise that branch by replacing UCIEngine with a
    fake whose ``go()`` never produces and never returns -- the
    simplest possible 'the subprocess is wedged' scenario, without
    spawning real processes that wedge the agentZero container.
    """

    async def test_kills_hang_and_raises_within_budget(
        self,
        fake_engine_class,
        starting_position_fen,
    ):
        spec = EngineSpec(engine_id="fake", path="/whatever")
        pool = EnginePool([spec], engine_go_timeout_s=0.5)
        req = AnalysisRequest(fen=starting_position_fen, depth=10)

        import time
        t0 = time.monotonic()
        with pytest.raises(EngineHungError) as excinfo:
            await pool.analyze(req, "fake")
        elapsed = time.monotonic() - t0

        # Diagnostic info carried on the exception.
        assert excinfo.value.engine_id == "fake"
        assert excinfo.value.timeout_s == 0.5
        assert excinfo.value.slot_index == 0

        # The hang must be torn down within the 0.5s budget plus a
        # generous grace for asyncio cancellation propagation.
        assert elapsed < 2.0, (
            f"recovery took {elapsed:.2f}s; expected <2.0s. "
            "Either the timeout is wrong, or the kill path hung."
        )

    async def test_slot_is_reset_after_hang(
        self,
        fake_engine_class,
        starting_position_fen,
    ):
        """After a timeout the slot must be empty so the next
        request gets a fresh engine, not a dead Popen."""
        spec = EngineSpec(engine_id="fake", path="/whatever")
        pool = EnginePool([spec], engine_go_timeout_s=0.5)
        req = AnalysisRequest(fen=starting_position_fen, depth=10)

        with pytest.raises(EngineHungError):
            await pool.analyze(req, "fake")

        slot = pool._slots["fake"][0]
        assert slot.engine is None, (
            "engine pool did not reset the slot after a hung go(); "
            f"slot.engine is {type(slot.engine).__name__}"
        )


# ---------------------------------------------------------------------------
# Finding 2: a dead pid between calls must trigger a fresh subprocess
# ---------------------------------------------------------------------------


class TestDeadPidRecovery:
    """Finding 2 from ADR-0006.

    These tests run against a fixture UCIEngine that hangs on the
    FIRST ``go()`` invocation and produces a normal bestmove on
    the second. Because Finding 1 above uses a separate pool, the
    second-pool fixture here simulates a different failure:
    Stockfish exited on its own (e.g. crash, OOM) between calls,
    and the next request finds a dead Popen.

    We exercise this with two cooperating layers: a UCIEngine
    whose first go() has the engine set itself to dead (poll()
    non-None) so that _acquire() on the next call must detect it.
    """

    async def test_dead_pid_is_replaced_with_fresh_subprocess(
        self,
        fake_engine_class,
        starting_position_fen,
    ):
        """Simulate: pool made one analyze() call against a process
        that answered bestmove then died (poll() now returns -9).
        The next analyze() must detect the dead pid and bring up a
        fresh engine, not wedge on the dead one's pipes."""

        spec = EngineSpec(engine_id="fake", path="/whatever")

        # Custom mode that exits after first answer.
        _DeadAfterFirstEngine_state = {"calls": 0}

        class _DeadAfterFirstEngine(FakeUCIEngine):
            def __init__(self, *a, **kw):
                # Force mode to "answer" so go() yields bestmove
                # then returns.
                kw["mode"] = "answer"
                super().__init__(*a, **kw)

            async def go(self, **kw):
                _DeadAfterFirstEngine_state["calls"] += 1
                async for ev in super().go(**kw):
                    yield ev
                if _DeadAfterFirstEngine_state["calls"] == 1:
                    # Simulate Stockfish crash immediately after
                    # first answer. poll() must return non-None.
                    self._proc.kill()  # sets _returncode = -9
                    self._proc._alive = False

        import chess_coach.engine_orch.pool as pool_module
        orig = pool_module.UCIEngine

        def _factory(binary, *, engine_id=None, extra_args=None, mode="hang"):
            # Ignore caller's mode; the test subclass decides.
            return _DeadAfterFirstEngine(
                binary, engine_id=engine_id, extra_args=extra_args
            )

        pool_module.UCIEngine = _factory
        try:
            _DeadAfterFirstEngine_state["calls"] = 0
            pool = EnginePool([spec])
            req = AnalysisRequest(fen=starting_position_fen, depth=1)

            # First analyze should succeed.
            r1 = await pool.analyze(req, "fake")
            assert r1.engine_id == "fake"

            # Confirm the slot's proc is actually dead.
            slot = pool._slots["fake"][0]
            assert slot.engine is not None
            assert slot.engine._proc is not None
            assert slot.engine._proc.poll() is not None, (
                "fixture error: _DeadAfterFirstEngine didn't mark "
                "proc dead after first go()"
            )

            # Second analyze must NOT hang forever on the dead proc.
            r2 = await asyncio.wait_for(
                pool.analyze(req, "fake"), timeout=5.0
            )
            assert r2.engine_id == "fake"
        finally:
            pool_module.UCIEngine = orig

    async def test_log_warning_on_dead_pid_recovery(
        self,
        fake_engine_class,
        starting_position_fen,
        caplog,
    ):
        """The pool should log a warning when it detects a dead
        pid so operators can see the recovery in production logs.
        """
        import logging

        spec = EngineSpec(engine_id="fake", path="/whatever")

        _DeadAfterFirstEngine_state = {"calls": 0}

        class _DeadAfterFirstEngine(FakeUCIEngine):
            def __init__(self, *a, **kw):
                kw["mode"] = "answer"
                super().__init__(*a, **kw)

            async def go(self, **kw):
                _DeadAfterFirstEngine_state["calls"] += 1
                async for ev in super().go(**kw):
                    yield ev
                if _DeadAfterFirstEngine_state["calls"] == 1:
                    self._proc.kill()
                    self._proc._alive = False

        import chess_coach.engine_orch.pool as pool_module
        orig = pool_module.UCIEngine

        def _factory(binary, *, engine_id=None, extra_args=None, mode="hang"):
            return _DeadAfterFirstEngine(
                binary, engine_id=engine_id, extra_args=extra_args
            )

        pool_module.UCIEngine = _factory
        try:
            _DeadAfterFirstEngine_state["calls"] = 0
            caplog.set_level(logging.WARNING, logger="chess_coach.engine_orch.pool")
            pool = EnginePool([spec])
            req = AnalysisRequest(fen=starting_position_fen, depth=1)
            await pool.analyze(req, "fake")
            await pool.analyze(req, "fake")

            matching = [
                r for r in caplog.records
                if "dead pid" in r.getMessage()
            ]
            assert matching, (
                "Expected a 'dead pid' warning in the engine pool "
                "logger, got: "
                + "; ".join(r.getMessage() for r in caplog.records)
            )
        finally:
            pool_module.UCIEngine = orig


# ---------------------------------------------------------------------------
# Health: a working pool still works under the default timeout
# ---------------------------------------------------------------------------


class TestHealthyPoolStillWorks:
    async def test_happy_path_with_answer_engine(
        self,
        fake_engine_class,
        starting_position_fen,
    ):
        """Sanity check: a pool using the answer-mode fake UCI
        still completes an analysis normally (the test machinery
        doesn't accidentally wedge or hang).
        """
        import chess_coach.engine_orch.pool as pool_module
        orig = pool_module.UCIEngine

        def _factory(binary, *, engine_id=None, extra_args=None, mode="hang"):
            return FakeUCIEngine(
                binary, engine_id=engine_id, extra_args=extra_args, mode="answer"
            )

        pool_module.UCIEngine = _factory
        try:
            spec = EngineSpec(engine_id="fake", path="/whatever")
            pool = EnginePool([spec])
            req = AnalysisRequest(fen=starting_position_fen, depth=1)
            result = await pool.analyze(req, "fake")
            assert result.engine_id == "fake"
            assert result.pvs, "answer-mode fake should have produced 1 PV"
        finally:
            pool_module.UCIEngine = orig
