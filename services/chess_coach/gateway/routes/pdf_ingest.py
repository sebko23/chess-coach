"""PDF ingest route.

Protocol §4.x:
  POST /v1/import/pdf  — upload a PDF, extract text, attempt chess diagram detection

Returns a PdfIngestResponse envelope immediately (synchronous processing for
Phase 1; async job-based processing may replace this in a later iteration).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, UploadFile

from chess_coach.gateway.auth import require_bearer

_log = logging.getLogger(__name__)

router = APIRouter(tags=["pdf"], dependencies=[Depends(require_bearer)])

# ── minimal FEN-like pattern (light detection) ──────────────────────────
_FEN_PATTERN = (
    r"[rnbqkpRNBQKP1-8]{1,8}/[rnbqkpRNBQKP1-8]{1,8}/"
    r"[rnbqkpRNBQKP1-8]{1,8}/[rnbqkpRNBQKP1-8]{1,8}/"
    r"[rnbqkpRNBQKP1-8]{1,8}/[rnbqkpRNBQKP1-8]{1,8}/"
    r"[rnbqkpRNBQKP1-8]{1,8}/[rnbqkpRNBQKP1-8]{1,8}"
)


async def _parse_pdf(content: bytes) -> dict:
    """Parse a PDF, extract text and attempt diagram/position detection.

    Returns a dict with keys:
        page_count, diagrams_detected, diagrams_valid, diagrams, errors
    """
    import re
    import fitz  # PyMuPDF

    doc = fitz.Document(stream=content, filetype="pdf")
    page_count = len(doc)
    diagrams: list[dict] = []
    errors: list[str] = []

    for page_num in range(page_count):
        page = doc[page_num]
        try:
            text = page.get_text(sort=True)
        except Exception as exc:
            errors.append(f"Page {page_num + 1}: text extraction failed — {exc}")
            continue

        # Look for FEN-like strings in extracted text
        for match in re.finditer(_FEN_PATTERN, text):
            candidate = match.group()
            # Very basic validation: must have exactly 7 slashes, no invalid chars
            if candidate.count("/") != 7:
                continue
            diagrams.append({
                "page_number": page_num + 1,
                "diagram_index": len(diagrams),
                "fen": candidate,
                "valid": True,
                "confidence": 0.8,
                "issues": [],
                "game_id": None,
                "job_id": None,
            })

        # Check for images that might be chess diagrams (future enhancement)
        # For now, we tag pages with images as potential diagram candidates
        try:
            images = page.get_images(full=True)
            if images and not any(d["page_number"] == page_num + 1 for d in diagrams):
                # Page has images but no FEN detected — could be scanned diagram
                diagrams.append({
                    "page_number": page_num + 1,
                    "diagram_index": len(diagrams),
                    "fen": "",
                    "valid": False,
                    "confidence": 0.1,
                    "issues": ["Image detected but no FEN could be extracted; OCR not yet implemented"],
                    "game_id": None,
                    "job_id": None,
                })
        except Exception:
            pass

    doc.close()

    valid_count = sum(1 for d in diagrams if d["valid"])
    return {
        "page_count": page_count,
        "diagrams_detected": len(diagrams),
        "diagrams_valid": valid_count,
        "diagrams": diagrams,
        "errors": errors,
    }


@router.post("/v1/import/pdf")
async def ingest_pdf(file: UploadFile) -> dict:
    """Ingest a PDF file, detect chess diagrams, and return a summary."""
    ingest_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    content = await file.read()

    try:
        result = await _parse_pdf(content)
    except Exception as exc:
        _log.exception("PDF ingest %s failed", ingest_id)
        return {
            "ingest_id": ingest_id,
            "filename": file.filename or "unknown.pdf",
            "page_count": 0,
            "diagrams_detected": 0,
            "diagrams_valid": 0,
            "diagrams": [],
            "errors": [f"Parsing failed: {exc}"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    completed_at = datetime.now(timezone.utc)
    return {
        "ingest_id": ingest_id,
        "filename": file.filename or "unknown.pdf",
        "page_count": result["page_count"],
        "diagrams_detected": result["diagrams_detected"],
        "diagrams_valid": result["diagrams_valid"],
        "diagrams": result["diagrams"],
        "errors": result["errors"],
        "completed_at": completed_at.isoformat(),
    }
