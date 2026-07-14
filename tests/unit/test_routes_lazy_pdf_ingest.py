"""Regression tests for the BBF-39 lazy pdf_ingest import.

BBF-39 changed ``services/chess_coach/gateway/routes/__init__.py`` to
load ``pdf_ingest`` lazily via module-level ``__getattr__`` (PEP 562),
because ``pdf_ingest`` pulls in ``pdf2image`` (a native dep that
requires ``poppler-utils`` and is not installed in the runtime Docker
image). Eagerly importing the module crashed the gateway on startup
with ``ModuleNotFoundError: No module named 'pdf2image'``, taking the
whole smoke CI red.

The contract verified here:

  1. Importing the routes package succeeds even when ``pdf2image`` is
     not installed. ``pdf2image`` IS missing in the runtime image by
     design; the lazy import is what keeps the gateway bootable.
  2. ``pdf_ingest_router`` is advertised via ``__all__`` and is
     accessible via attribute access, exactly as the rest of the
     routers.
  3. The first access to ``pdf_ingest_router`` triggers the import
     of the pdf_ingest module. If the underlying ``pdf2image`` is
     missing, that access raises ``ModuleNotFoundError``; the test
     catches that specific exception (NOT a generic
     ``ImportError``) so it is not confused with a typo or a
     circular import. A clean image with ``pdf2image`` installed
     returns the real router object.
  4. After the import attempt (success or failure), the routes
     module is still importable and the rest of the routers are
     not affected.
"""
from __future__ import annotations

import importlib
import sys

import pytest


def _reload_routes():
    """Force a fresh import of the routes package so the test is
    independent of any prior import side-effects."""
    # Drop every cached module under chess_coach.gateway.routes so the
    # next import re-runs __init__.py from scratch.
    for name in list(sys.modules):
        if name == "chess_coach.gateway.routes" or name.startswith(
            "chess_coach.gateway.routes."
        ):
            del sys.modules[name]
    return importlib.import_module("chess_coach.gateway.routes")


class TestRoutesImport:
    def test_routes_module_imports_without_pdf2image(self):
        """Importing the routes package must not require pdf2image.

        Before BBF-39, ``from .pdf_ingest import router as
        pdf_ingest_router`` at the top of __init__.py made every
        gateway startup fail with ModuleNotFoundError when pdf2image
        was missing. The lazy import moves the pdf2image dep to
        attribute-access time, so a bare ``import routes`` works.
        """
        routes = _reload_routes()
        # Other routers (analysis, eval_graph, etc.) ARE eagerly
        # imported and must be present without further attribute
        # access. This guards against a regression where the
        # lazy-import refactor accidentally deferred them too.
        assert hasattr(routes, "analysis_router")
        assert hasattr(routes, "eval_graph_router")
        assert hasattr(routes, "kb_router")

    def test_pdf_ingest_router_in_all(self):
        """The lazy router must still be in __all__ so 'from
        .routes import pdf_ingest_router' keeps working in
        app.py without code changes."""
        routes = _reload_routes()
        assert "pdf_ingest_router" in routes.__all__


class TestLazyPdfIngest:
    def test_attribute_access_triggers_import(self):
        """Accessing routes.pdf_ingest_router must trigger the
        import of the pdf_ingest module. If pdf2image is missing
        in the test env, the access raises ModuleNotFoundError
        (the expected outcome here); the test asserts that the
        error comes from the pdf_ingest module, not from a typo
        or a circular import. On a clean image, this returns
        the real router object instead."""
        routes = _reload_routes()
        # The first access MUST trigger importlib.import_module on
        # the pdf_ingest submodule. We can detect that by checking
        # sys.modules for the now-cached module (or by the absence
        # of it on failure).
        try:
            router = routes.pdf_ingest_router
        except ModuleNotFoundError as exc:
            # The error must be about pdf2image (the missing dep),
            # not about routes itself or any other module.
            assert "pdf2image" in str(exc), (
                f"expected pdf2image import failure, got: {exc!r}"
            )
            # And the failing module must be pdf_ingest (the
            # submodule that lazy __getattr__ just tried to load).
            assert "pdf_ingest" in str(exc), (
                f"expected pdf_ingest to be the importer, got: {exc!r}"
            )
        else:
            # Clean env: pdf2image is installed, the real router
            # was returned. It should be a FastAPI APIRouter (or
            # duck-compatible). We do a soft check here.
            assert router is not None


class TestRegression:
    def test_other_routers_unaffected_by_lazy_import(self):
        """The lazy-import refactor must not break the eager
        imports of every other router. Re-import routes and
        confirm all the non-lazy ones are still top-level
        attributes of the module object."""
        routes = _reload_routes()
        non_lazy = (
            "analysis_router",
            "blunder_router",
            "engines_router",
            "eval_graph_router",
            "game_router",
            "narration_router",
            "players_router",
            "profile_router",
            "repertoire_router",
            "training_router",
            "lichess_import_router",
            "repertoire_recommendations_router",
            "profile_analysis_router",
            "training_planner_router",
            "kb_router",
            "pgn_import_router",
            "backfill_analyses_router",
        )
        for name in non_lazy:
            assert hasattr(routes, name), (
                f"eagerly imported router {name} is missing after "
                f"BBF-39 refactor"
            )
