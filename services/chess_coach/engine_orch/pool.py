"""Engine pool orchestrator.

Manages a bounded set of UCI engine worker processes. Scheduling is FIFO;
each worker has its own subprocess and per-worker asyncio.Lock so N
analyses can run truly in parallel.

BBF-19: replaced single-slot-per-engine with N-slot-per-engine. Each
slot owns its own UCIEngine subprocess and its own lock. The semaphore
(max_workers) caps concurrent in-flight analyses; the per-slot lock
serializes access to that slot's single-coroutine Stockfish process.
Round-robin slot selection keeps load balanced and avoids starvation.
"""
from __future__ import annotations

import asyncio
import hashlib
import itertools
import logging
import platform
from dataclasses import dataclass, field

from chess_coach.protocol_types.analysis import AnalysisRequest, AnalysisResult, PVLine
from chess_coach.uci.engine import UCIEngine, InfoEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineSpec:
    """Describes an engine binary and its human-readable id."""

    engine_id: str
    path: str  # absolute path on the backend host
    extra_args: list[str] = field(default_factory=list)
    skip_options: set[str] = field(default_factory=set)


class _EngineSlot:
    """One UCI engine subprocess + its per-slot asyncio.Lock.

    The lock is held by EnginePool.analyze() for the entire analysis
    body (position + go() + collect), so the same slot is never
    touched by two coroutines concurrently. asyncio.Lock is NOT
    reentrant; callers must not re-acquire it inside the held region.
    """

    __slots__ = ("engine_id", "slot_index", "lock", "engine")

    def __init__(self, engine_id: str, slot_index: int) -> None:
        self.engine_id = engine_id
        self.slot_index = slot_index
        self.lock: asyncio.Lock = asyncio.Lock()
        self.engine: UCIEngine | None = None  # lazy-init on first acquire

    def __repr__(self) -> str:
        return f"_EngineSlot(engine_id={self.engine_id!r}, slot_index={self.slot_index})"


class EnginePool:
    """Bounded FIFO engine pool with N parallel workers per engine_id.

    In Phase 2 this provides true parallelism: max_workers stockfish
    subprocesses for engine_id='stockfish', so asyncio.gather() of N
    plies in pgn_import.py runs ~N times faster (modulo UCI overhead).
    The interface is unchanged for callers; only the implementation
    scales.
    """

    def __init__(
        self,
        specs: list[EngineSpec],
        *,
        max_workers: int = 1,
        default_depth: int = 22,
        default_multipv: int = 1,
        default_threads: int = 1,
        default_hash_mb: int = 128,
    ) -> None:
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers}")
        self._specs = {s.engine_id: s for s in specs}
        self._max_workers = max_workers
        # Semaphore caps total concurrent analyses across all slots.
        self._sem = asyncio.Semaphore(max_workers)
        # Per-engine slot ring: _slots[engine_id] = [_EngineSlot, _EngineSlot, ...]
        self._slots: dict[str, list[_EngineSlot]] = {
            s.engine_id: [_EngineSlot(s.engine_id, i) for i in range(max_workers)]
            for s in specs
        }
        # Round-robin cursor per engine_id. itertools.count is monotonic
        # and atomic at the bytecode level for next(); with asyncio
        # (single-threaded event loop) this is race-free without a lock.
        self._rr: dict[str, itertools.count] = {
            s.engine_id: itertools.count() for s in specs
        }
        self._default_depth = default_depth
        self._default_multipv = default_multipv
        self._default_threads = default_threads
        self._default_hash_mb = default_hash_mb

        # discover CPU arch once; used in AnalysisResult.cpu_arch
        self._cpu_arch = platform.machine() + (
            "-avx2" if "avx2" in platform.processor().lower() else ""
        )

    @property
    def max_workers(self) -> int:
        return self._max_workers

    # ── public API ──────────────────────────────────────────────────────

    async def analyze(self, req: AnalysisRequest, engine_id: str) -> AnalysisResult:
        """Run an analysis job and return the canonical result.

        Round-robins to a slot, holds the slot's per-engine lock for the
        entire body (position + go() + collect), then releases.
        """
        spec = self._specs.get(engine_id)
        if spec is None:
            raise ValueError(f"Unknown engine: {engine_id}")

        depth = req.depth or self._default_depth
        multipv = req.multipv
        options = dict(req.options)
        # ensure sensible defaults
        skip = getattr(spec, "skip_options", frozenset())
        if "Threads" not in skip:
            options.setdefault("Threads", self._default_threads)
        if "Hash" not in skip:
            options.setdefault("Hash", self._default_hash_mb)
        if multipv > 1:
            options["MultiPV"] = multipv

        async with self._sem:
            slot = self._next_slot(engine_id)
            # Per-slot lock: serializes all calls that would touch the
            # same Stockfish subprocess (which is single-coroutine — its
            # readuntil() raises if a second coroutine reads concurrently).
            async with slot.lock:
                engine = await self._acquire(spec, slot, options)
                try:
                    await engine.position(fen=req.fen)
                    pvs_dict: dict[int, PVLine] = {}
                    use_nodes = spec.path.endswith("lc0") or any("lc0" in a for a in spec.extra_args)
                    async for ev in engine.go(depth=None if use_nodes else depth, nodes=1 if use_nodes else None):
                        if ev.score is not None and ev.pv:
                            pv = PVLine(
                                multipv=ev.multipv,
                                score=ev.score,
                                depth=ev.depth,
                                moves=ev.pv,
                                nodes=ev.nodes,
                                time_ms=ev.time_ms,
                                nps=ev.nps,
                            )
                            # keep the deepest line per multipv slot
                            if (
                                ev.multipv not in pvs_dict
                                or pv.depth > pvs_dict[ev.multipv].depth
                            ):
                                pvs_dict[ev.multipv] = pv
                    # sort by multipv index
                    pvs = [pvs_dict[k] for k in sorted(pvs_dict)]
                    if not pvs:
                        raise RuntimeError("Engine returned no PVs")

                    settings_hash = _hash_options(options)

                    return AnalysisResult(
                        engine_id=engine_id,
                        engine_version=engine._version,
                        fen=req.fen,
                        depth_reached=max(pv.depth for pv in pvs),
                        multipv=multipv,
                        settings_hash=settings_hash,
                        cpu_arch=self._cpu_arch,
                        thread_count=options.get("Threads", self._default_threads),
                        pvs=pvs,
                    )
                finally:
                    await self._release(engine, engine_id, slot)

    async def engine_info(self, engine_id: str) -> dict[str, object]:
        """Return engine metadata for GET /engines/{engine_id}."""
        spec = self._specs.get(engine_id)
        if spec is None:
            raise ValueError(f"Unknown engine: {engine_id}")
        slot = self._slots[engine_id][0]  # any slot is representative
        async with slot.lock:
            engine = await self._acquire(spec, slot, {})
            try:
                name = getattr(engine, "engine_name", None) or getattr(engine, "_name", "unknown")
                version = getattr(engine, "_version", "unknown")
                proc = getattr(engine, "_proc", None)
                opts = getattr(engine, "_options", {})
                return {
                    "engine_id": engine_id,
                    "name": name,
                    "version": version,
                    "path": spec.path,
                    "state": "ready" if proc is not None else "ready",
                    "capabilities": opts,
                    "workers": self._max_workers,
                }
            finally:
                await self._release(engine, engine_id, slot)

    async def warmup(self) -> None:
        """Eagerly start one UCIEngine subprocess per slot.

        Called from app.py lifespan so the first PGN import doesn't pay
        N times the cold-start cost (one per slot). Acquires every
        slot's lock in order, then releases.
        """
        for engine_id, slots in self._slots.items():
            spec = self._specs[engine_id]
            for slot in slots:
                async with slot.lock:
                    await self._acquire(spec, slot, {})

    async def shutdown(self) -> None:
        """Kill all engine subprocesses across all slots."""
        async with asyncio.TaskGroup() as tg:
            for slots in self._slots.values():
                for slot in slots:
                    if slot.engine is not None and slot.engine._proc is not None:
                        tg.create_task(slot.engine.quit())
        for slots in self._slots.values():
            for slot in slots:
                slot.engine = None

    # ── internal ────────────────────────────────────────────────────────

    def _next_slot(self, engine_id: str) -> _EngineSlot:
        """Round-robin slot selection. O(1), no lock needed (asyncio is
        single-threaded; itertools.count() is safe under the event loop)."""
        slots = self._slots[engine_id]
        idx = next(self._rr[engine_id]) % len(slots)
        return slots[idx]

    async def _acquire(
        self, spec: EngineSpec, slot: _EngineSlot, options: dict
    ) -> UCIEngine:
        # NOTE: caller MUST already hold slot.lock. asyncio.Lock is NOT
        # reentrant, so we cannot re-acquire it here.
        if slot.engine is None or slot.engine._proc is None:
            engine = UCIEngine(
                spec.path, engine_id=spec.engine_id, extra_args=spec.extra_args
            )
            await engine.start(options=options)
            slot.engine = engine
            logger.info(
                "engine_pool: started slot %d for %s (pid=%s)",
                slot.slot_index,
                spec.engine_id,
                getattr(engine._proc, "pid", "?") if engine._proc else "?",
            )
        else:
            # Filter out options that the engine doesn't support
            filtered_options = {
                k: v for k, v in options.items() if k not in spec.skip_options
            }
            try:
                await slot.engine.set_options(filtered_options)
            except Exception as e:
                logger.warning(
                    "set_options failed for %s slot %d: %s",
                    spec.engine_id,
                    slot.slot_index,
                    e,
                )
        return slot.engine

    async def _release(
        self, engine: UCIEngine, engine_id: str, slot: _EngineSlot
    ) -> None:
        # In Phase 2 we keep each engine alive across requests for speed.
        # A later pooling strategy may decide to idle-kill.
        pass


def _hash_options(options: dict) -> str:
    """Deterministic hash of UCI option key-value pairs."""
    raw = "|".join(f"{k}={v}" for k, v in sorted(options.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:12]
