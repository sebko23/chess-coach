"""Regression tests for eval-graph dedup (BBF-36).

These tests guard ADR-0006 Finding 3: the eval-graph route can be
hit by multiple concurrent first-viewers on the same (game_id,
ply, engine_id, depth) cache key, and the analyses table's
``INSERT OR IGNORE`` only prevents corruption, not redundant
Stockfish work. ``_coalesce_analyze`` collapses the duplicates
into one Stockfish call by sharing a single ``asyncio.Future``
across all waiters.

Tests intentionally avoid importing the full FastAPI app: the
_route_ is exercised end-to-end by manual smoke testing, not by
this unit test file. We import only the helper functions
(``_coalesce_analyze``, ``_dedup_get``, etc.) and exercise them
in isolation, with ``monkeypatch`` resetting the module-level
``_inflight`` dict before each test.
"""
from __future__ import annotations

import asyncio

import pytest

import chess_coach.gateway.routes.eval_graph as eval_graph_module
from chess_coach.gateway.routes.eval_graph import (
    _coalesce_analyze,
    _dedup_get,
    _dedup_put,
    _get_dedup_lock,
)

KEY_A: tuple[str, int, str, int] = ("game-1", 5, "stockfish", 6)
KEY_B: tuple[str, int, str, int] = ("game-1", 7, "stockfish", 6)
KEY_C: tuple[str, int, str, int] = ("game-2", 5, "stockfish", 6)


@pytest.fixture(autouse=True)
def _reset_dedup_state():
    """Clear _inflight dict and reset the cached lock before each test.

    The lock is reset because it bound to whatever event loop was
    active when the first test ran; subsequent tests (with a fresh
    loop from pytest-asyncio) cannot reuse a lock already bound
    to a closed loop.
    """
    eval_graph_module._inflight.clear()
    eval_graph_module._dedup_lock = None
    yield
    eval_graph_module._inflight.clear()
    eval_graph_module._dedup_lock = None


# ---------------------------------------------------------------------------
# Lock construction
# ---------------------------------------------------------------------------


class TestDedupLock:
    def test_get_dedup_lock_returns_singleton(self):
        a = _get_dedup_lock()
        b = _get_dedup_lock()
        assert a is b

    def test_get_dedup_lock_lazily_creates(self):
        # Before first call, the lock is None (autouse fixture resets it).
        assert eval_graph_module._dedup_lock is None
        lock = _get_dedup_lock()
        assert lock is not None
        assert isinstance(lock, asyncio.Lock)
        # Now the module has bound the lock.
        assert eval_graph_module._dedup_lock is lock


# ---------------------------------------------------------------------------
# _dedup_get / _dedup_put round-trip
# ---------------------------------------------------------------------------


class TestDedupGetPut:
    async def test_get_returns_none_when_dict_empty(self):
        assert _dedup_get(KEY_A) is None

    async def test_put_then_get_returns_future(self):
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        _dedup_put(KEY_A, fut)
        assert _dedup_get(KEY_A) is fut

    async def test_get_drops_completed_future(self):
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        fut.set_result(True)
        _dedup_put(KEY_A, fut)
        # Completed future lingering in the dict must be removed on
        # get, not returned.
        assert _dedup_get(KEY_A) is None
        assert KEY_A not in eval_graph_module._inflight

    async def test_get_drops_stale_ttl_entry(self, monkeypatch):
        """A future older than _DEDUP_TTL_S is stale and dropped."""
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        # Force expiry to the past so the TTL check fires.
        eval_graph_module._inflight[KEY_A] = (fut, 0.0)
        assert _dedup_get(KEY_A) is None
        assert KEY_A not in eval_graph_module._inflight


# ---------------------------------------------------------------------------
# _coalesce_analyze -- the actual race-prevention helper
# ---------------------------------------------------------------------------


class TestCoalesceAnalyze:
    async def test_same_key_collapses_into_one_call(self):
        """Two callers hitting KEY_A while the leader is mid-coroutine
        must trigger exactly ONE invocation of coro_factory."""
        call_count = 0
        leader_started = asyncio.Event()
        release_leader = asyncio.Event()

        async def slow_factory():
            nonlocal call_count
            call_count += 1
            leader_started.set()
            await release_leader.wait()
            return "ok"

        async def caller():
            return await _coalesce_analyze(KEY_A, slow_factory)

        # Schedule two concurrent callers on the same key.
        # asyncio.gather waits for both; they share the same future.
        results_task = asyncio.gather(caller(), caller())

        # Wait for the leader to actually start, then release.
        await leader_started.wait()
        release_leader.set()

        r1, r2 = await results_task
        assert r1 == "ok"
        assert r2 == "ok"
        # The contract: only ONE call to slow_factory, regardless of
        # how many concurrent awaiters there were.
        assert call_count == 1, (
            f"expected exactly one Stockfish call for the same key; "
            f"got {call_count}"
        )

    async def test_different_keys_proceed_in_parallel(self):
        """Two callers hitting DIFFERENT keys must each get their own
        coro_factory invocation."""
        counts = {}

        async def make_factory(label):
            async def factory():
                counts[label] = counts.get(label, 0) + 1
                await asyncio.sleep(0.05)
                return label
            return factory

        # Run 3 different keys in parallel.
        results = await asyncio.gather(
            _coalesce_analyze(KEY_A, await make_factory("A")),
            _coalesce_analyze(KEY_B, await make_factory("B")),
            _coalesce_analyze(KEY_C, await make_factory("C")),
        )
        assert sorted(results) == ["A", "B", "C"]
        assert counts == {"A": 1, "B": 1, "C": 1}

    async def test_follower_receives_leader_exception(self):
        """If the leader raises, every follower sees the same exception.

        We construct the test by pre-registering the future in
        ``_inflight`` (with a far-future expiry) so the awaiter is
        guaranteed to be a follower regardless of timing. The leader
        task we create independently calls ``set_exception`` on the
        same future, then we assert that the awaiter raised.
        """
        import time as _time

        class BoomError(Exception):
            pass

        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        # Pre-register so the awaiter sees an existing future.
        eval_graph_module._inflight[KEY_A] = (fut, _time.monotonic() + 60.0)

        async def leader_task():
            # Yield once so the follower's task is scheduled.
            await asyncio.sleep(0)
            exc = BoomError("stockfish fell over")
            fut.set_exception(exc)

        leader = asyncio.create_task(leader_task())

        # This becomes a follower because the future is already
        # registered. It awaits the leader's exception. Because
        # the leader set_exception before we awaited, the await
        # itself raises BoomError -- we wrap in try/except to
        # catch the propagation and assert.
        with pytest.raises(BoomError, match="stockfish fell over"):
            await _coalesce_analyze(KEY_A, lambda: asyncio.sleep(0))

        await leader  # ensure the leader completes

        # Future's exception was retrieved (by the follower); the
        # asyncio "never retrieved" warning should NOT fire.
        assert fut.done()
        assert fut.exception() is not None

    async def test_entry_cleared_after_leader_completes(self):
        """After the leader finishes (success or failure), the dict
        entry must be removed so the next caller starts fresh."""
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            return call_count

        # First call -- leader inserts, completes, removes.
        r1 = await _coalesce_analyze(KEY_A, factory)
        assert r1 == 1
        assert KEY_A not in eval_graph_module._inflight

        # Second call -- leader again, fresh.
        r2 = await _coalesce_analyze(KEY_A, factory)
        assert r2 == 2
        assert KEY_A not in eval_graph_module._inflight

    async def test_concurrent_100_callers_same_key_one_call(self):
        """Stress: 100 concurrent callers on the same key -> one call."""
        call_count = 0
        leader_started = asyncio.Event()
        release = asyncio.Event()

        async def slow_factory():
            nonlocal call_count
            call_count += 1
            leader_started.set()
            await release.wait()
            return "shared"

        results_task = asyncio.gather(
            *[_coalesce_analyze(KEY_A, slow_factory) for _ in range(100)]
        )
        # Wait for the leader to actually start, then release it so
        # the gather completes. Without this the test deadlocks on
        # release.wait() inside the leader.
        await leader_started.wait()
        release.set()

        results = await results_task
        assert all(r == "shared" for r in results)
        assert call_count == 1, (
            f"100 callers on same key should share one Stockfish call; "
            f"got {call_count}"
        )

    async def test_cancellation_propagates_to_followers(self):
        """If the leader's task is cancelled, the followers see the
        same outcome.

        In CPython, setting ``CancelledError`` on a future cancels
        every awaiter. We mirror that here: we cancel the leader
        task and assert the follower's future also resolves with
        ``CancelledError``.

        A subtle Python detail: ``asyncio.Future.set_exception``
        with a ``CancelledError`` instance cancels all waiters of
        that future, which is the same shape as a normal task
        cancellation propagating through ``await``. The follower
        sees a ``CancelledError`` whether the leader was cancelled
        or set ``CancelledError`` directly on the future.
        """
        import time as _time

        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        eval_graph_module._inflight[KEY_A] = (fut, _time.monotonic() + 60.0)

        async def leader_cancels():
            # Yield so the follower task schedules and starts
            # awaiting fut. THEN set_exception(CancelledError) --
            # asyncio special-cases this and cancels awaiters,
            # which is exactly the shape of a task.cancel() that
            # propagates through the gather.
            await asyncio.sleep(0)
            fut.set_exception(asyncio.CancelledError())

        leader = asyncio.create_task(leader_cancels())

        # Catch the CancelledError so the test doesn't itself get
        # cancelled; assert it is what we expected.
        with pytest.raises(asyncio.CancelledError):
            await _coalesce_analyze(KEY_A, lambda: asyncio.sleep(0))

        await leader
        # Note: in this synthetic test the leader is not running
        # _coalesce_analyze, so the cleanup that would happen in
        # its `finally:` does not fire. The TTL on the _inflight
        # entry handles this in production; for the test we
        # simulate it by popping the entry explicitly so subsequent
        # tests don't see leakage.
        eval_graph_module._inflight.pop(KEY_A, None)
