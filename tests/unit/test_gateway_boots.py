"""Regression test for the BBF-39/40/41/42 missing-dep cascade.

The earlier unit test
``tests/unit/test_routes_lazy_pdf_ingest.py`` (now deleted in
BBF-43) only checked
``routes.pdf_ingest_router`` directly. It "expected" the
``ModuleNotFoundError`` it observed, which masked the
real bug: ``from .routes import pdf_ingest_router`` in
``app.py`` triggers the lazy ``__getattr__`` lookup at
*import* time (PEP 562 gotcha), so the import in
``app.py`` crashed the whole process anyway.

This test exercises the real boot path -- building the
FastAPI app the way ``chess_coach-gateway`` does at
runtime -- so any future missing runtime dep (or
broken import pattern) surfaces as a clean failure
in CI before a push lands.

Mirrors the smoke workflow's step 5 ("Build backend
image") and step 6 ("Start backend") in a unit-test
shape: no Docker, no real Stockfish subprocess, no
network. Just an in-process ``create_app()`` call.
"""
from __future__ import annotations


def test_create_app_does_not_raise():
    """The gateway can build its FastAPI app without raising.

    Catches every flavour of the "missing runtime dep" bug
    that took the smoke workflow red from BBF-32 through
    BBF-42: pdf2image (BBF-39/42), aiohttp (BBF-40),
    numpy + sentence-transformers + qdrant-client
    (BBF-41), and any future dep that gets added to a
    route module without being declared in
    ``pyproject.toml``.
    """
    # Ensure the env vars the gateway expects at startup
    # are set, so this test runs cleanly under pytest
    # without depending on test fixtures. CHESS_COACH_DATA_DIR
    # is pointed at a per-run tmp dir so the test never
    # touches /data (which may not be writable in CI).
    import os
    import tempfile
    os.environ.setdefault("CHESS_COACH_BACKEND_TOKEN", "devtoken123")
    os.environ.setdefault("CHESS_COACH_MAX_WORKERS", "1")
    os.environ.setdefault(
        "CHESS_COACH_DATA_DIR",
        tempfile.mkdtemp(prefix="chess-coach-boot-test-"),
    )

    from chess_coach.gateway.app import create_app

    app = create_app()
    # FastAPI app has a non-zero route count when the
    # import chain in app.py / routes/__init__.py
    # succeeds. We don't pin the exact count because
    # new routes are added over time; we just assert
    # the chain completed.
    route_count = sum(1 for _ in app.routes)
    assert route_count > 0, (
        "create_app() returned a FastAPI app with no routes; "
        "the import chain completed but no routers registered. "
        "This usually means the import in app.py returned but "
        "the include_router calls inside create_app() did not run."
    )
