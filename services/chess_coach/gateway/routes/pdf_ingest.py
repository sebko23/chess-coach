"""PDF ingestion route — extracts chess diagrams from PDF pages via chessvision.ai.

POST /v1/import/pdf
Accepts a PDF file upload, extracts pages as images, submits each to the
chessvision.ai /predict endpoint, and stores valid FEN positions in the DB.

chessvision.ai API: POST https://app.chessvision.ai/predict (BBF-sec-01)
- No API key required (public endpoint)
- Accepts base64-encoded PNG images
- Returns FEN string with underscores instead of spaces
- Returns exactly one FEN per page (success: true) or no FEN (success: false).
  Multi-board pages are NOT supported by the public endpoint. See BBF-68.3
  for the probe that established this and the doc-only contract change.
"""
# ruff: noqa: B008  -- FastAPI Depends() in argument defaults is the intended pattern; flagged uniformly across all route handlers.
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

import asyncio

import aiosqlite
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFPopplerTimeoutError
from pydantic import BaseModel, Field

from ...pdf_ocr import predict_fen
from ..auth import require_bearer
from ..config import GatewaySettings
from ..route_guard import route_guard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/import", tags=["import"])

DPI = 200
MAX_PAGES = 50
# FU-19 (A-F11): reject oversized PDFs BEFORE any parsing work.
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB cap on the upload size.


# FU-19 (A-F11): fast-fail magic-bytes check before invoking the parser.
PDF_MAGIC = b"%PDF-"


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


def _provide_settings() -> GatewaySettings:
    """Provide gateway settings as a FastAPI dependency.

    Returns a fresh ``GatewaySettings()`` (reads env / .env). Do NOT pass the
    ``BaseSettings`` class directly as ``Depends(GatewaySettings)``: FastAPI
    derives a spurious ``_cli_parse_args`` body field from a pydantic-settings
    model in that position, which pydantic 2.x rejects at import and breaks
    gateway boot. A function-based dependency sidesteps the mis-derived field.
    """
    return GatewaySettings()


class DiagramResult(BaseModel):
    page: int
    diagram_index: int = Field(
        default=0,
        ge=0,
        description=(
            "0-based index of this diagram within the page. The public "
            "chessvision.ai /predict endpoint returns at most one FEN per "
            "page, so the route always emits 0 for valid responses. A "
            "future multi-board backend (or a local page-segmentation "
            "model) would emit 0, 1, 2, ... in reading order."
        ),
    )
    fen: str | None
    valid: bool
    confidence: float
    issue: str | None = None


class PdfImportResponse(BaseModel):
    import_id: str
    filename: str
    pages_processed: int
    diagrams_found: int
    diagrams_valid: int
    # Single-FEN-per-page contract (BBF-68.3). The public
    # chessvision.ai /predict endpoint returns at most one FEN per page,
    # so len(diagrams) <= pages_processed and the per-page count is <= 1.
    # A future multi-board backend (or local page-segmentation model)
    # would either drop this field or raise the bound.
    max_diagrams_per_page: int = Field(
        default=1,
        ge=1,
        description=(
            "Upper bound on the number of DiagramResult entries produced "
            "from a single PDF page. The public chessvision.ai /predict "
            "endpoint emits at most one FEN per page, so this constant is "
            "1 today. A future multi-board backend (or local "
            "page-segmentation model) would raise this bound."
        ),
    )
    diagrams: list[DiagramResult] = Field(
        description=(
            "One DiagramResult per OCR'd page. With the chessvision "
            "default backend, at most one DiagramResult is produced per "
            "page (max_diagrams_per_page=1). Pages where the OCR backend "
            "returned success=false emit a DiagramResult with fen=None "
            "and a populated issue field; they do not produce a FEN."
        ),
    )


async def _predict_fen(
    image_png_bytes: bytes,
    *,
    settings: GatewaySettings | None = None,
) -> tuple[str | None, float, str | None]:
    """Thin delegator to the OCR backend dispatcher.

    The actual backend is selected at call time by the
    ``CHESS_COACH_OCR_BACKEND`` environment variable, see
    ``chess_coach.pdf_ocr.adapter``. Backends MUST return ``OcrResult``
    tuples; this function exists only so ``import_pdf`` keeps its existing
    call shape and existing route-integration tests stay green.

    BBF-sec-01: when the caller provides Pydantic ``GatewaySettings``,
    the route hands the configured ``chessvision_url`` to the adapter
    so a single source-of-truth governs the OCR endpoint across the
    gateway. The settings object is optional to preserve backward
    compatibility with tests that call this delegator directly.
    """
    if settings is not None:
        result = await predict_fen(image_png_bytes, url=settings.chessvision_url)
    else:
        result = await predict_fen(image_png_bytes)
    return (result.fen, result.confidence, result.error)


def _validate_fen(fen: str | None) -> bool:
    if not fen:
        return False
    try:
        import chess
        board = chess.Board(fen)
        return 2 <= len(board.piece_map()) <= 32
    except Exception:
        return False


@router.post(
    "/pdf",
    response_model=PdfImportResponse,
    dependencies=[Depends(require_bearer)],
)
@route_guard
async def import_pdf(
    file: Annotated[UploadFile, File(...)],
    max_pages: int = Query(MAX_PAGES, ge=1, le=200),
    db_path: str = Depends(_db_path),
    settings: GatewaySettings = Depends(_provide_settings),
) -> PdfImportResponse:
    """Extract chess diagrams from a PDF via chessvision.ai."""
    import_id = str(uuid.uuid4())
    filename = file.filename or "unknown.pdf"

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # FU-19 (A-F11): file-size cap. Prevents the parser from being
    # asked to handle pathologically large uploads.
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF exceeds maximum size of {MAX_PDF_BYTES} bytes",
        )

    # FU-19 (A-F11): magic-bytes check before parser invocation.
    # Catches renamed non-PDF uploads (e.g. .exe renamed to .pdf)
    # that would otherwise reach pdf2image and pdftoppm.
    if pdf_bytes[: len(PDF_MAGIC)] != PDF_MAGIC:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a PDF (missing %PDF- header)",
        )

    # FU-19 (A-F11): inner timeout (per-Popen, with pdf2image; outer
    # wait_for is the FastAPI-level safety net). Per security-strategy.md
    # "Implementation (as of 2026-08-13)" section: the operative contract
    # is a 5-minute wall-clock budget per request regardless of page count;
    # a literal "5-min per page" reading is impractical with pdf2image's
    # single-threaded batched Popen model (one call processes the full
    # page range, so timeout applies to the entire batch).
    PARSER_TIMEOUT_SECONDS = 300
    ASYNCIO_WAIT_SLACK_SECONDS = 30  # outer wait_for slack over inner.

    try:
        pages = await asyncio.wait_for(
            # Run the synchronous pdf2image call in the default thread
            # pool so the FastAPI event loop is not blocked during the
            # potentially long-running pdftoppm subprocess.
            asyncio.to_thread(
                convert_from_bytes,
                pdf_bytes,
                dpi=DPI,
                first_page=1,
                last_page=max_pages,
                timeout=PARSER_TIMEOUT_SECONDS,
            ),
            timeout=PARSER_TIMEOUT_SECONDS + ASYNCIO_WAIT_SLACK_SECONDS,
        )
    except (PDFPopplerTimeoutError, asyncio.TimeoutError):
        raise HTTPException(
            status_code=504,
            detail=f"PDF parsing exceeded the {PARSER_TIMEOUT_SECONDS}s budget; "
            "the file may be malicious or pathological. Rejected per A-F11.",
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"PDF conversion failed: {exc}") from exc

    logger.info("pdf_import %s: %d pages from %s", import_id, len(pages), filename)

    results: list[DiagramResult] = []
    valid_diagrams: list[tuple[int, str]] = []

    for page_num, page_img in enumerate(pages, 1):
        buf = io.BytesIO()
        page_img.save(buf, format="PNG")

        fen, confidence, error = await _predict_fen(
            buf.getvalue(), settings=settings,
        )
        valid = _validate_fen(fen)

        results.append(DiagramResult(
            page=page_num,
            fen=fen,
            valid=valid,
            confidence=confidence if valid else 0.0,
            issue=error if not valid else None,
        ))

        if valid and fen:
            valid_diagrams.append((page_num, fen))
            logger.info("page %d: valid FEN %s", page_num, fen[:50])

    now = datetime.now(UTC).isoformat()

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO pdf_imports
               (id, filename, page_count, diagrams_found, diagrams_valid,
                errors_json, completed_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                import_id,
                filename,
                len(pages),
                len(valid_diagrams),
                len(valid_diagrams),
                json.dumps([r.issue for r in results if r.issue]),
                now,
                now,
            ),
        )
        for page_num, fen in valid_diagrams:
            await db.execute(
                """INSERT INTO pdf_import_diagrams
                   (id, ingest_id, page_number, diagram_index, fen,
                    valid, confidence, issues_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    import_id,
                    page_num,
                    0,
                    fen,
                    1,
                    0.9,
                    json.dumps([]),
                    now,
                ),
            )
        await db.commit()

    return PdfImportResponse(
        import_id=import_id,
        filename=filename,
        pages_processed=len(pages),
        diagrams_found=len(valid_diagrams),
        diagrams_valid=len(valid_diagrams),
        max_diagrams_per_page=1,
        diagrams=results,
    )
