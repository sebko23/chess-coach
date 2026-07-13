"""Engine pool orchestrator.

Manages a bounded set of UCI engine worker processes. Scheduling is FIFO;
engines are shared (one-fen-at-a-time). Phase 1: single Stockfish instance.
"""
from __future__ import annotations

import asyncio
import hashlib
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


class EnginePool:
    """Bounded FIFO engine pool.

    In Phase 1 this is essentially a single-Stockfish wrapper, but the
    interface is generic so we can later add Leela / Berserk / Ethereal
    without breaking callers.
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
        self._specs = {s.engine_id: s for s in specs}
        self._max_workers = max_workers
        self._sem = asyncio.Semaphore(max_workers)
        self._engines: dict[str, UCIEngine] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._default_depth = default_depth
        self._default_multipv = default_multipv
        self._default_threads = default_threads
        self._default_hash_mb = default_hash_mb

        # discover CPU arch once; used in AnalysisResult.cpu_arch
        self._cpu_arch = platform.machine() + (
            "-avx2" if "avx2" in platform.processor().lower() else ""
        )

    # ── public API ──────────────────────────────────────────────────────

    async def analyze(self, req: AnalysisRequest, engine_id: str) -> AnalysisResult:
        """Run an analysis job and return the canonical result.

        This is the primary entry-point; it handles engine lifecycle,
        UCI option forwarding, and result collection.
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
            # Per-engine lock: serializes all calls that would touch the
            # same Stockfish subprocess (which is single-coroutine — its
            # readuntil() raises if a second coroutine reads concurrently).
            if engine_id not in self._locks:
                self._locks[engine_id] = asyncio.Lock()
            async with self._locks[engine_id]:
                engine = await self._acquire(spec, options)
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
                    await self._release(engine, engine_id)

    async def engine_info(self, engine_id: str) -> dict[str, object]:
        """Return engine metadata for GET /engines/{engine_id}."""
        spec = self._specs.get(engine_id)
        if spec is None:
            raise ValueError(f"Unknown engine: {engine_id}")
        engine = await self._acquire(spec, {})
        try:
            name = getattr(engine, 'engine_name', None) or getattr(engine, '_name', 'unknown')
            version = getattr(engine, '_version', 'unknown')
            proc = getattr(engine, '_proc', None)
            opts = getattr(engine, '_options', {})
            return {
                "engine_id": engine_id,
                "name": name,
                "version": version,
                "path": spec.path,
                "state": "ready" if proc is not None else "ready",
                "capabilities": opts,
            }
        finally:
            await self._release(engine, engine_id)

    async def shutdown(self) -> None:
        """Kill all engine subprocesses."""
        async with asyncio.TaskGroup() as tg:
            for eid, engine in self._engines.items():
                if engine._proc is not None:
                    tg.create_task(engine.quit())
        self._engines.clear()
        self._locks.clear()

    # ── internal ────────────────────────────────────────────────────────

    async def _acquire(self, spec: EngineSpec, options: dict) -> UCIEngine:
        if spec.engine_id not in self._locks:
            self._locks[spec.engine_id] = asyncio.Lock()
        async with self._locks[spec.engine_id]:
            engine = self._engines.get(spec.engine_id)
            if engine is None or engine._proc is None:
                engine = UCIEngine(spec.path, engine_id=spec.engine_id, extra_args=spec.extra_args)
                await engine.start(options=options)
                self._engines[spec.engine_id] = engine
            else:
                # Filter out options that the engine doesn't support
                filtered_options = {k: v for k, v in options.items() if k not in spec.skip_options}
                try:
                    await engine.set_options(filtered_options)
                except Exception as e:
                    logger.warning(f"set_options failed for {spec.engine_id}: {e}")
            return engine

    async def _release(self, engine: UCIEngine, engine_id: str) -> None:
        # In Phase 1 we keep the engine alive across requests for speed.
        # A later pooling strategy may decide to idle-kill.
        pass


def _hash_options(options: dict) -> str:
    """Deterministic hash of UCI option key-value pairs."""
    raw = "|".join(f"{k}={v}" for k, v in sorted(options.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:12]
