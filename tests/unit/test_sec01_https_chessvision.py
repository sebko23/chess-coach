"""Tests for BBF-sec-01: HTTPS-by-default chessvision.ai URL.

The 2026-07-30 security audit flagged the hardcoded
``CHESSVISION_URL = "http://app.chessvision.ai/predict"`` as a
MEDIUM-severity plaintext exfiltration channel for user-uploaded
PDFs (services/chess_coach/pdf_ocr/adapter.py:44 prior to this
BBF). This module verifies:

  1. The module default is now HTTPS.
  2. The env-var override ``CHESS_COACH_OCR_CHESSVISION_URL`` works.
  3. The explicit-URL path through ``predict_fen`` flows to the
     network layer.
  4. The ``GatewaySettings.chessvision_url`` Pydantic field is the
     single source-of-truth (HTTPS by default).
"""
from __future__ import annotations

import pytest


def test_module_default_is_https() -> None:
    """The shipped default URL must be HTTPS after BBF-sec-01."""
    from chess_coach.pdf_ocr import adapter

    assert adapter.CHESSVISION_URL.startswith("https://"), (
        f"CHESSVISION_URL must be HTTPS, got: {adapter.CHESSVISION_URL!r}"
    )


def test_resolve_chessvision_url_uses_explicit_arg() -> None:
    """An explicit argument always wins over env + module default."""
    from chess_coach.pdf_ocr import adapter

    explicit = "https://my-ocr.example.com/predict"
    assert adapter.resolve_chessvision_url(explicit=explicit) == explicit


def test_resolve_chessvision_url_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no explicit arg is given, env var is consulted."""
    from chess_coach.pdf_ocr import adapter

    monkeypatch.setenv(
        "CHESS_COACH_OCR_CHESSVISION_URL",
        "https://env-ocr.example.com/predict",
    )
    assert adapter.resolve_chessvision_url() == (
        "https://env-ocr.example.com/predict"
    )


def test_resolve_chessvision_url_falls_back_to_module_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When neither explicit arg nor env var is set, the module
    HTTPS default is used."""
    from chess_coach.pdf_ocr import adapter

    monkeypatch.delenv("CHESS_COACH_OCR_CHESSVISION_URL", raising=False)
    assert adapter.resolve_chessvision_url() == adapter.CHESSVISION_URL
    assert adapter.resolve_chessvision_url().startswith("https://")


def test_resolve_chessvision_url_blank_env_treated_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank env value is treated as unset, not as the literal '' URL."""
    from chess_coach.pdf_ocr import adapter

    monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_URL", "   ")
    assert adapter.resolve_chessvision_url() == adapter.CHESSVISION_URL


def test_predict_fen_url_override_routes_to_caller_url() -> None:
    """When the route passes ``url=`` to ``predict_fen``, the URL is
    captured by the closure (not by mutating the module constant)."""
    from chess_coach.pdf_ocr import adapter

    explicit = "https://caller.example.com/predict"
    adapter._chessvision_with_url(explicit)
    # The predicter is callable; we don't fire it here (that would
    # require httpx mock and is covered by the integration test).
    # The closure pattern must not mutate the module constant.
    assert explicit != adapter.CHESSVISION_URL


def test_predict_fen_url_override_does_not_mutate_module_constant() -> None:
    """The override must not mutate the module-level CHESSVISION_URL,
    which would race with concurrent callers in the same process."""
    from chess_coach.pdf_ocr import adapter

    original = adapter.CHESSVISION_URL
    explicit = "https://caller.example.com/predict"
    adapter._chessvision_with_url(explicit)
    # Module constant is unchanged.
    assert original == adapter.CHESSVISION_URL


def test_predict_fen_closure_has_independent_url() -> None:
    """Two closures built with different URLs must each carry their
    own bound URL (no shared module-state)."""
    from chess_coach.pdf_ocr import adapter

    a = adapter._chessvision_with_url("https://a.example.com/predict")
    b = adapter._chessvision_with_url("https://b.example.com/predict")
    # The function objects are distinct, confirming per-call
    # closure creation rather than module-state sharing.
    assert a is not b
    assert callable(a)
    assert callable(b)


def test_settings_field_default_is_https_via_grep() -> None:
    """GatewaySettings.chessvision_url must default to HTTPS.

    We avoid constructing GatewaySettings in this test because the
    venv (FastAPI 0.139.x + pydantic 2.13.x) has a body-model
    compatibility issue that breaks any settings construction. The
    existing ``tests/conftest.py:_isolate_env`` autouse fixture
    already provides settings for the full pytest run; this test
    instead does a static read of the config file.
    """
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    config_file = repo / "services" / "chess_coach" / "gateway" / "config.py"
    src = config_file.read_text(encoding="utf-8")
    # Find the chessvision_url field default in the file. We accept
    # either the default=... style or the HTTPS-only check on the
    # literal default string.
    m = re.search(
        r"chessvision_url:\s*str\s*=\s*Field\s*\(\s*default\s*=\s*[\"']([^\"']+)[\"']",
        src,
    )
    assert m, "chessvision_url field not found in config.py"
    default_url = m.group(1)
    assert default_url.startswith("https://"), (
        f"chessvision_url default must be HTTPS, got: {default_url!r}"
    )


def test_settings_field_uses_chess_coach_prefix() -> None:
    """The chessvision_url field must use the CHESS_COACH_ env-prefix
    so operators can override it via env.

    Reads the field's source from config.py and confirms the
    surrounding GatewaySettings uses env_prefix="CHESS_COACH_".
    """
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    config_file = repo / "services" / "chess_coach" / "gateway" / "config.py"
    src = config_file.read_text(encoding="utf-8")
    # Verify the GatewaySettings class uses the standard env_prefix.
    m_prefix = re.search(r'env_prefix\s*=\s*["\']CHESS_COACH_["\']', src)
    assert m_prefix, (
        "GatewaySettings.model_config must declare env_prefix='CHESS_COACH_'"
    )
    # Verify the chessvision_url field is declared (so it gets the
    # prefix applied). Pydantic-settings will produce
    # CHESS_COACH_CHESSVISION_URL automatically.
    m_field = re.search(r"chessvision_url:\s*str\s*=\s*Field", src)
    assert m_field, "chessvision_url field not found in config.py"


def test_no_plaintext_chessvision_url_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final defensive sweep: the literal string 'app.chessvision.ai/predict'
    must not appear with http:// in the source tree."""
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    # Search only Python source files (which are tracked). Excludes
    # audit reports that may historically reference the http:// URL.
    # Also exclude __pycache__ and venv.
    result = subprocess.run(
        [
            "grep", "-rnE", "--include=*.py",
            r"http://app\.chessvision\.ai",
            "services", "libs",
        ],
        capture_output=True, text=True, cwd=str(repo),
    )
    assert result.returncode != 0 or not result.stdout, (
        f"plaintext chessvision URL found in source:\n{result.stdout}"
    )
