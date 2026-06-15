"""Async UCI client — speaks the Universal Chess Interface protocol over an asyncio subprocess.

Protocol reference: http://wbec-ridderkerk.nl/html/UCIProtocol.html

Usage::

    engine = UCIEngine("/usr/local/bin/stockfish")
    await engine.start()
    info = []
    async for ev in engine.go(fen="...", depth=18):
        info.append(ev)
    print(engine.bestmove, engine.ponder)
    await engine.quit()
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import AsyncIterator

from ..protocol_types.analysis import Score

logger = logging.getLogger(__name__)

# ── regex helpers ──────────────────────────────────────────────────────────

_RE_INFO = re.compile(
    r"""
    depth\s+(?P<depth>\d+)
    (?:\s+seldepth\s+(?P<seldepth>\d+))?
    (?:\s+multipv\s+(?P<multipv>\d+))?
    (?:\s+score\s+(?P<score_kind>cp|mate)\s+(?P<score_value>-?\d+))?
    (?:\s+nodes\s+(?P<nodes>\d+))?
    (?:\s+nps\s+(?P<nps>\d+))?
    (?:\s+hashfull\s+\d+)?
    (?:\s+tbhits\s+\d+)?
    (?:\s+time\s+(?P<time>\d+))?
    (?:\s+pv\s+(?P<pv>.+))?
    """,
    re.VERBOSE,
)

_BESTMOVE = re.compile(r"^bestmove\s+(?P<move>\S+)(?:\s+ponder\s+(?P<ponder>\S+))?")


@dataclass
class InfoEvent:
    """One ``info ...`` line parsed into typed fields."""

    depth: int
    multipv: int = 1
    seldepth: int | None = None
    score: Score | None = None
    nodes: int | None = None
    nps: int | None = None
    time_ms: int | None = None
    pv: list[str] = field(default_factory=list)


class UCIEngine:
    """Asynchronous UCI protocol client wrapping a single subprocess."""

    def __init__(self, binary: str, engine_id: str | None = None, extra_args: list[str] | None = None) -> None:
        self.binary: str = binary
        self.engine_id: str = engine_id or binary
        self._proc: asyncio.subprocess.Process | None = None
        self.extra_args: list[str] = extra_args or []
        self._name: str = ""
        self._author: str = ""
        self._version: str = ""
        self._options: list[dict[str, object]] = []
        self.bestmove: str = ""
        self.ponder: str = ""

    # ── lifecycle ──────────────────────────────────────────────────────

    async def start(self, *, options: dict[str, str | int | bool] | None = None) -> None:
        """Launch the engine subprocess and run the UCI handshake."""
        if self._proc is not None:
            return
        self._proc = await asyncio.create_subprocess_exec(
            self.binary,
            *self.extra_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert self._proc.stdout is not None
        await self._send("uci")
        # consume until uciok
        while True:
            line = await self._readline()
            if line.startswith("id name "):
                self._name = line[8:].strip()
            elif line.startswith("id author "):
                self._author = line[10:].strip()
            elif line.startswith("option "):
                self._options.append(_parse_option(line[7:]))
            elif line == "uciok":
                break
        self._version = self._name  # we can refine later
        logger.info("uci: engine %s ready (uciok)", self.engine_id)
        await self.set_options(options or {})
        await self._send("isready")
        await self._expect("readyok")

    async def quit(self) -> None:
        """Gracefully stop the engine."""
        if self._proc is None:
            return
        try:
            await self._send("quit")
            await asyncio.wait_for(self._proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            self._proc.kill()
            await self._proc.wait()
        finally:
            self._proc = None

    # ── commands ────────────────────────────────────────────────────────

    async def set_options(self, options: dict[str, str | int | bool]) -> None:
        """Send ``setoption`` for each key-value pair."""
        for name, value in options.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            await self._send(f"setoption name {name} value {value}")

    async def position(
        self, *, fen: str | None = None, moves: list[str] | None = None
    ) -> None:
        """Send the ``position`` command."""
        if fen is not None:
            cmd = f"position fen {fen}"
        else:
            cmd = "position startpos"
        if moves:
            cmd += " moves " + " ".join(moves)
        await self._send(cmd)

    async def go(
        self,
        *,
        depth: int | None = None,
        nodes: int | None = None,
        movetime: int | None = None,
        wtime: int | None = None,
        btime: int | None = None,
        winc: int | None = None,
        binc: int | None = None,
        movestogo: int | None = None,
    ) -> AsyncIterator[InfoEvent]:
        """Send the ``go`` command and yield ``InfoEvent``s until ``bestmove``.

        This is an async generator; you must consume it (or break early and
        call ``stop()``).
        """
        parts = ["go"]
        if depth is not None:
            parts.append(f"depth {depth}")
        if nodes is not None:
            parts.append(f"nodes {nodes}")
        if movetime is not None:
            parts.append(f"movetime {movetime}")
        if wtime is not None:
            parts.append(f"wtime {wtime}")
            if btime is not None:
                parts.append(f"btime {btime}")
            if winc is not None:
                parts.append(f"winc {winc}")
            if binc is not None:
                parts.append(f"binc {binc}")
            if movestogo is not None:
                parts.append(f"movestogo {movestogo}")
        await self._send(" ".join(parts))
        assert self._proc is not None and self._proc.stdout is not None
        self.bestmove = ""
        self.ponder = ""
        while True:
            line = await self._readline()
            if line.startswith("info "):
                ev = _parse_info(line)
                if ev is not None:
                    yield ev
            elif line.startswith("bestmove "):
                m = _BESTMOVE.match(line)
                if m:
                    self.bestmove = m.group("move")
                    self.ponder = m.group("ponder") or ""
                return

    async def stop(self) -> None:
        """Send ``stop`` (idempotent)."""
        await self._send("stop")

    # ── internal ────────────────────────────────────────────────────────

    async def _send(self, cmd: str) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("Engine not started")
        self._proc.stdin.write((cmd + "\n").encode())
        await self._proc.stdin.drain()

    async def _readline(self) -> str:
        assert self._proc is not None and self._proc.stdout is not None
        line = await self._proc.stdout.readline()
        if not line:
            raise EOFError("Engine stdout closed unexpectedly")
        return line.decode().rstrip("\r\n")

    async def _expect(self, expected: str) -> None:
        """Read lines until ``expected`` appears (or timeout)."""
        for _ in range(1000):  # safety valve
            line = await self._readline()
            if line == expected:
                return
            if line.startswith("info "):
                continue  # skip info lines (e.g. "info string Using 1 thread")
            logger.warning("uci: expected %r, got unexpected %r", expected, line)


# ── private helpers ────────────────────────────────────────────────────────


def _parse_info(line: str) -> InfoEvent | None:
    """Parse a single ``info ...`` line into an ``InfoEvent``."""
    m = _RE_INFO.search(line)
    if not m:
        return None
    score = None
    if m.group("score_kind") and m.group("score_value") is not None:
        score = Score(kind=m.group("score_kind"), value=int(m.group("score_value")))
    pv_str = m.group("pv")
    pv = pv_str.split() if pv_str else []
    return InfoEvent(
        depth=int(m.group("depth")),
        multipv=int(m.group("multipv")) if m.group("multipv") else 1,
        seldepth=int(m.group("seldepth")) if m.group("seldepth") else None,
        score=score,
        nodes=int(m.group("nodes")) if m.group("nodes") else None,
        nps=int(m.group("nps")) if m.group("nps") else None,
        time_ms=int(m.group("time")) if m.group("time") else None,
        pv=pv,
    )


def _parse_option(text: str) -> dict[str, object]:
    """Parse one ``option ...`` line into a dict (simplified)."""
    result: dict[str, object] = {}
    # We do a quick split instead of a full UCI option parser.
    parts = text.split()
    i = 0
    while i < len(parts):
        tok = parts[i]
        if tok == "name":
            i += 1
            name_parts = []
            while i < len(parts) and parts[i] not in (
                "type",
                "default",
                "min",
                "max",
            ):
                name_parts.append(parts[i])
                i += 1
            result["name"] = " ".join(name_parts)
            continue
        if tok == "type":
            i += 1
            if i < len(parts):
                result["type"] = parts[i]
                i += 1
            continue
        if tok == "default":
            i += 1
            if i < len(parts):
                result["default"] = parts[i]
                i += 1
            continue
        if tok == "min":
            i += 1
            if i < len(parts):
                result["min"] = int(parts[i])
                i += 1
            continue
        if tok == "max":
            i += 1
            if i < len(parts):
                result["max"] = int(parts[i])
                i += 1
            continue
        i += 1
    return result
