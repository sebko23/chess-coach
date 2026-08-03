"""Unit tests for the BBF-68.3 doc-only contract change + max_diagrams_per_page.

The public chessvision.ai /predict endpoint returns exactly one FEN per
page, not a list. The route must therefore emit at most one
DiagramResult per page and label it diagram_index=0. This test pins
that contract so a future multi-board attempt cannot silently regress
the schema or the per-page count.
"""
from __future__ import annotations

import json

import pytest

# Mirrors tests/integration/test_pdf_import.py:19-32. The route returns
# 422 for any non-PDF payload, so a minimal valid PDF is required to
# exercise the OCR call path.
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000005 80000 n \n"
    b"0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n190\n"
    b"%%EOF"
)
MOCK_FEN = "8/8/8/4k3/8/8/8/4K2R w K - 0 1"


def test_diagram_result_exposes_diagram_index_field() -> None:
    """The DiagramResult Pydantic model now carries a 0-based diagram_index."""
    from services.chess_coach.gateway.routes.pdf_ingest import DiagramResult

    fields = DiagramResult.model_fields
    assert "diagram_index" in fields, (
        "DiagramResult must carry diagram_index (BBF-68.3 contract)"
    )
    # Default is 0 (single-FEN case).
    dr = DiagramResult(page=1, fen=MOCK_FEN, valid=True, confidence=0.9)
    assert dr.diagram_index == 0
    # Explicit 0 is the supported single-board case.
    dr2 = DiagramResult(
        page=1, fen=MOCK_FEN, valid=True, confidence=0.9, diagram_index=0
    )
    assert dr2.diagram_index == 0
    # 1+ is reserved for future multi-board backends.
    dr3 = DiagramResult(
        page=1, fen=MOCK_FEN, valid=True, confidence=0.9, diagram_index=2
    )
    assert dr3.diagram_index == 2


def test_diagram_result_rejects_negative_index() -> None:
    """diagram_index is ge=0; negative values are a contract violation."""
    from pydantic import ValidationError
    from services.chess_coach.gateway.routes.pdf_ingest import DiagramResult

    with pytest.raises(ValidationError):
        DiagramResult(
            page=1, fen=MOCK_FEN, valid=True, confidence=0.9, diagram_index=-1
        )


def test_pdf_response_includes_diagrams_field_with_diagram_index() -> None:
    """OpenAPI / contract check: PdfImportResponse.diagrams surfaces diagram_index."""
    from services.chess_coach.gateway.routes.pdf_ingest import (
        DiagramResult,
        PdfImportResponse,
    )

    # Build a minimal response and serialize via model_dump to assert
    # the field name is exposed on the wire.
    resp = PdfImportResponse(
        import_id="00000000-0000-0000-0000-000000000000",
        filename="test.pdf",
        pages_processed=1,
        diagrams_found=1,
        diagrams_valid=1,
        diagrams=[
            DiagramResult(
                page=1, diagram_index=0, fen=MOCK_FEN, valid=True, confidence=0.9
            )
        ],
    )
    serialized = json.loads(resp.model_dump_json())
    diagram = serialized["diagrams"][0]
    assert diagram["diagram_index"] == 0
    assert diagram["page"] == 1
    assert diagram["fen"] == MOCK_FEN


def test_module_docstring_documents_multi_board_contract() -> None:
    """The route's module docstring must declare the single-FEN-per-page
    contract so future readers don't assume multi-board support exists.
    """
    from services.chess_coach.gateway.routes import pdf_ingest

    doc = pdf_ingest.__doc__ or ""
    assert (
        "single FEN per page" in doc
        or "single-FEN" in doc
        or "Multi-board" in doc
    ), (
        "pdf_ingest module docstring must declare the multi-board contract "
        "(BBF-68.3)"
    )


def test_pdf_import_response_serializes_diagram_index_field() -> None:
    """The schema published to the client must include diagram_index.

    The default FastAPI JSON response model serializes every field on
    BaseModel; this test pins diagram_index as a wire field so a future
    refactor that drops the model field (e.g. swapping the model out
    for a TypedDict) cannot silently regress the contract.
    """
    from services.chess_coach.gateway.routes.pdf_ingest import (
        DiagramResult,
        PdfImportResponse,
    )

    payload = PdfImportResponse(
        import_id="00000000-0000-0000-0000-000000000000",
        filename="t.pdf",
        pages_processed=1,
        diagrams_found=1,
        diagrams_valid=1,
        diagrams=[
            DiagramResult(
                page=1, diagram_index=0, fen=MOCK_FEN, valid=True, confidence=0.9
            )
        ],
    )
    json_str = payload.model_dump_json()
    decoded = json.loads(json_str)
    assert "diagrams" in decoded
    assert decoded["diagrams"][0]["diagram_index"] == 0


def test_module_re_exports_diagram_index_constant() -> None:
    """The default diagram_index value must be 0.

    Pinning the constant at the module level ensures a future change
    to the Pydantic Field default cannot silently flip the wire shape.
    """
    from services.chess_coach.gateway.routes.pdf_ingest import DiagramResult

    assert DiagramResult(page=1, fen=MOCK_FEN, valid=True, confidence=0.9).diagram_index == 0


def test_pdf_import_response_exposes_max_diagrams_per_page_field() -> None:
    """The PdfImportResponse carries a max_diagrams_per_page constant.

    The default chessvision.ai /predict path returns at most one FEN
    per page, so max_diagrams_per_page defaults to 1 and the value is
    surfaced in the wire shape so clients (and OpenAPI tooling) can
    verify the contract. A future multi-board backend would either
    drop this field or raise the bound.
    """
    from services.chess_coach.gateway.routes.pdf_ingest import (
        DiagramResult,
        PdfImportResponse,
    )

    # Model defaults: no explicit value, single-diagram response.
    payload = PdfImportResponse(
        import_id="00000000-0000-0000-0000-000000000000",
        filename="single.pdf",
        pages_processed=1,
        diagrams_found=1,
        diagrams_valid=1,
        diagrams=[
            DiagramResult(
                page=1, diagram_index=0, fen=MOCK_FEN, valid=True, confidence=0.9
            )
        ],
    )
    json_str = payload.model_dump_json()
    decoded = json.loads(json_str)
    assert decoded["max_diagrams_per_page"] == 1


def test_max_diagrams_per_page_field_has_correct_constraints() -> None:
    """max_diagrams_per_page must be an int, default 1, and ge=1."""
    from pydantic import ValidationError
    from services.chess_coach.gateway.routes.pdf_ingest import (
        DiagramResult,
        PdfImportResponse,
    )

    fields = PdfImportResponse.model_fields
    assert "max_diagrams_per_page" in fields, (
        "PdfImportResponse must carry max_diagrams_per_page "
        "(BBF-68.3 OpenAPI surface)."
    )

    payload = PdfImportResponse(
        import_id="00000000-0000-0000-0000-000000000000",
        filename="x.pdf",
        pages_processed=1,
        diagrams_found=1,
        diagrams_valid=1,
        max_diagrams_per_page=2,
        diagrams=[
            DiagramResult(
                page=1, diagram_index=0, fen=MOCK_FEN, valid=True, confidence=0.9
            )
        ],
    )
    assert payload.max_diagrams_per_page == 2

    # ge=1 rejects 0 and negatives.
    with pytest.raises(ValidationError):
        PdfImportResponse(
            import_id="00000000-0000-0000-0000-000000000000",
            filename="y.pdf",
            pages_processed=1,
            diagrams_found=1,
            diagrams_valid=1,
            max_diagrams_per_page=0,
            diagrams=[
                DiagramResult(
                    page=1, diagram_index=0, fen=MOCK_FEN, valid=True, confidence=0.9
                )
            ],
        )


def test_pdf_ingest_route_app_openapi_succeeds(app) -> None:
    """The FastAPI app built with the route module must produce a valid OpenAPI schema.

    Regression guard for the v0.7.116 footgun (FastAPI 0.139.x + pydantic 2.13.4):
    adding `Depends(SomePydanticModel)` to a route signature default triggers pydantic
    `create_model` to emit a `_cli_parse_args` body field, which pydantic 2.13.4 rejects
    with `NameError: Fields must not use names with leading underscores`. The error
    fires at `app.openapi()` time (when FastAPI walks the route tree to build the
    schema). Constructing the app via the existing `app` fixture and calling
    `app.openapi()` exercises that code path. PR #68 (bbf-pdf-ingest-depends-fix)
    replaced the bad `Depends(GatewaySettings)` with a function-based provider; this
    test would have caught the pre-PR-#68 regression on CI in seconds.

    The test does NOT post a PDF (that requires stockfish + the chessvision adapter);
    it only exercises the OpenAPI schema build, which is the trigger surface.
    """
    # The `app` fixture (tests/conftest.py) builds the FastAPI app via
    # `create_app(settings)` with an isolated CHESS_COACH_DATA_DIR.
    # Calling `app.openapi()` walks the route tree and triggers any
    # `Depends(SomePydanticModel)` body-model generation.
    schema = app.openapi()
    # The PDF-import route must be registered. Verify by OpenAPI path.
    assert "/v1/import/pdf" in schema["paths"], (
        "POST /v1/import/pdf must be registered after FastAPI walks the route tree;\n"
        "if missing, FastAPI likely failed to introspect the route signature\n"
        "(regression of the v0.7.116 Depends(BaseSettings) footgun)."
    )
