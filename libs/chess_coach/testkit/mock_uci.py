"""Mock UCI engine for tests.

Provides a :class:`MockUCIEngine` that behaves like :class:`UCIEngine`
but returns pre-programmed output lines. No real subprocess required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator

from chess_coach.uci.engine import InfoEvent
from chess_coach.protocol_types.analysis import Score


@dataclass
class MockUCIEngine:
    """Drop-in UCI mock: same interface as UCIEngine, no subprocess."""

    engine_id: str = "mock"
    engine_name: str = "Mock Engine 1.0"
    _version: str = "1.0"
    _started: bool = False
    _options: dict[str, str | int | bool] = field(default_factory=dict)
    _fen: str = ""
    _moves: list[str] = field(default_factory=list)
    bestmove: str = ""
    ponder: str = ""
    #: Pre-programmed go output
    _go_output: list[InfoEvent] = field(default_factory=list)

    async def start(self, *, options: dict[str, str | int | bool] | None = None) -> None:
        self._started = True
        if options:
            self._options.update(options)

    async def quit(self) -> None:
        self._started = False

    async def set_options(self, options: dict[str, str | int | bool]) -> None:
        self._options.update(options)

    async def position(self, *, fen: str | None = None, moves: list[str] | None = None) -> None:
        self._fen = fen or ""
        self._moves = moves or []

    async def go(self, **kwargs) -> AsyncIterator[InfoEvent]:
        if not self._go_output:
            # Default output: a single 1.d4 at depth 10
            ev = InfoEvent(
                depth=10,
                multipv=1,
                score=Score(kind="cp", value=38),
                pv=["d2d4", "d7d5"],
                nodes=12345,
                time_ms=100,
            )
            self.bestmove = "d2d4"
            self.ponder = "d7d5"
            yield ev
            return
        for ev in self._go_output:
            if ev.pv:
                self.bestmove = ev.pv[0]
                self.ponder = ev.pv[1] if len(ev.pv) > 1 else ""
            yield ev

    async def stop(self) -> None:
        pass
