"""OCR backend dispatch for Phase 6 PDF ingestion.

This package isolates the chess-diagram OCR step from the FastAPI route so
the backend can be swapped (chessvision.ai -> local model) without touching
the route handler.

The active backend is selected by the ``CHESS_COACH_OCR_BACKEND`` environment
variable. Valid values are ``chessvision`` (default, current behavior) and
``local`` (placeholder for the BBF-68.1 follow-up). Unknown values raise
:class:`UnknownOcrBackend`.
"""
from .adapter import (
    DEFAULT_BACKEND,
    OcrResult,
    UnknownOcrBackend,
    get_backend,
    predict_fen,
)

__all__ = [
    "DEFAULT_BACKEND",
    "OcrResult",
    "UnknownOcrBackend",
    "get_backend",
    "predict_fen",
]
