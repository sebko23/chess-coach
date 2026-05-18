"""``python -m chess_coach.gateway`` entrypoint.

Boots uvicorn, binds the configured (or kernel-assigned) port, then writes
``backend.json`` so clients can discover us. On signal/exception the lifespan
shutdown hook removes the descriptor.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

import uvicorn

# Load .env before any application code reads OPENROUTER_API_KEY.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .app import BACKEND_VERSION, PROTOCOL_MAX, create_app
from .auth import get_active_token
from .config import GatewaySettings
from .descriptor import Descriptor, write_descriptor

logger = logging.getLogger(__name__)


async def _run_async(settings: GatewaySettings) -> int:
    app = create_app(settings)
    config = uvicorn.Config(
        app=app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        # access logs are silenced in app._configure_logging
        access_log=False,
        # one event loop, no reload (ADR-0001)
        loop="asyncio",
        lifespan="on",
        reload=False,
    )
    server = uvicorn.Server(config)

    # Handle Ctrl-C cleanly on POSIX (Windows uses uvicorn's own handler).
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, server.handle_exit, sig, None)

    serve_task = asyncio.create_task(server.serve(), name="uvicorn.serve")

    # Wait until the server has actually bound a socket so we can read the
    # real port (matters when settings.port == 0).
    while not server.started and not serve_task.done():
        await asyncio.sleep(0.01)
    if serve_task.done():
        # Startup failed before binding; let the exception propagate.
        return await serve_task or 1  # type: ignore[func-returns-value]

    bound_port = _resolve_bound_port(server, fallback=settings.port)
    if settings.enable_descriptor:
        token = get_active_token() or ""
        descriptor = Descriptor(
            host=settings.host,
            port=bound_port,
            session_token=token,
            protocol_version=PROTOCOL_MAX,
            backend_version=BACKEND_VERSION,
        )
        write_descriptor(settings.descriptor_path, descriptor)
        # Stamp on app state so the lifespan shutdown knows to clean up.
        app.state.gateway.descriptor = descriptor  # type: ignore[attr-defined]
        logger.info(
            "gateway.ready: serving %s:%d  descriptor=%s",
            settings.host, bound_port, settings.descriptor_path,
        )
    else:
        logger.info("gateway.ready: serving %s:%d  (descriptor disabled)", settings.host, bound_port)

    await serve_task
    return 0


def _resolve_bound_port(server: uvicorn.Server, *, fallback: int) -> int:
    """Read the bound port off uvicorn's underlying server, or fall back."""
    servers: Any = getattr(server, "servers", None)
    if not servers:
        return fallback
    for s in servers:
        for sock in getattr(s, "sockets", []) or []:
            try:
                addr = sock.getsockname()
                if isinstance(addr, tuple) and len(addr) >= 2:
                    port = int(addr[1])
                    if port:
                        return port
            except OSError:
                continue
    return fallback


def main() -> int:
    settings = GatewaySettings()
    try:
        return asyncio.run(_run_async(settings))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
