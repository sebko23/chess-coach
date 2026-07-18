"""PDF ingestion route — extracts chess diagrams from PDF pages via chessvision.ai.

POST /v1/import/pdf
Accepts a PDF file upload, extracts pages as images, submits each to the
chessvision.ai /predict endpoint, and stores valid FEN positions in the DB.

chessvision.ai API: POST http://app.chessvision.ai/predict
- No API key required (public endpoint)
- Accepts base64-encoded PNG images
- Returns FEN string with underscores instead of spaces
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pdf2image import convert_from_bytes
from pydantic import BaseModel

from ...pdf_ocr import predict_fen
from ..auth import require_bearer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/import", tags=["import"])

DPI = 200
MAX_PAGES = 50


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


class DiagramResult(BaseModel):
    page: int
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
    diagrams: list[DiagramResult]


async def _predict_fen(image_png_bytes: bytes) -> tuple[str | None, float, str | None]:
    """Thin delegator to the OCR backend dispatcher.

    The actual backend is selected at call time by the
    ``CHESS_COACH_OCR_BACKEND`` environment variable, see
    ``chess_coach.pdf_ocr.adapter``. Backends MUST return ``OcrResult``
    tuples; this function exists only so ``import_pdf`` keeps its existing
    call shape and existing route-integration tests stay green.
    """
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
async def import_pdf(
    file: Annotated[UploadFile, File(...)],
    max_pages: int = Query(MAX_PAGES, ge=1, le=200),
    db_path: str = Depends(_db_path),
) -> PdfImportResponse:
    """Extract chess diagrams from a PDF via chessvision.ai."""
    import_id = str(uuid.uuid4())
    filename = file.filename or "unknown.pdf"

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        pages = convert_from_bytes(
            pdf_bytes, dpi=DPI, first_page=1, last_page=max_pages
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"PDF conversion failed: {exc}") from exc

    logger.info("pdf_import %s: %d pages from %s", import_id, len(pages), filename)

    results: list[DiagramResult] = []
    valid_diagrams: list[tuple[int, str]] = []

    for page_num, page_img in enumerate(pages, 1):
        buf = io.BytesIO()
        page_img.save(buf, format="PNG")

        fen, confidence, error = await _predict_fen(buf.getvalue())
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
        diagrams=results,
    )
