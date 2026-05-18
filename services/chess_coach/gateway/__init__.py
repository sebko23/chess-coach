"""FastAPI gateway service — protocol-conforming HTTP/WS surface.

ADR-0002 + protocol §3 §4 §10. Run with ``python -m chess_coach.gateway``.
"""
from __future__ import annotations

from .app import (
    BACKEND_VERSION,
    CAPABILITIES,
    PROTOCOL_MAX,
    PROTOCOL_MIN,
    create_app,
)
from .config import GatewaySettings

__all__ = [
    "BACKEND_VERSION",
    "CAPABILITIES",
    "GatewaySettings",
    "PROTOCOL_MAX",
    "PROTOCOL_MIN",
    "create_app",
]
