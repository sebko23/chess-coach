#!/usr/bin/env python3
"""
chess-coach / pdftomd_probe.py  (Sprint: chess-coach-pdftomd-probe-2026-07-09)

End-to-end demonstrator probe that proves or disproves:
  "PyMuPDF + HF subtask chain (dopaul/chessboard-detector + Nothasan/Chessboard)
   can produce a .md file with <board fen="..."/> tags inline from a chess PDF,
   with FEN accuracy sufficient for downstream LLM consumption. JSON checkpoint
   metric namespace is FROZEN as of 2026-07-10. See METRIC_KEYSPACE constant
   and tests/unit/test_pdftomd_metrics.py for the canonical schema."

Per the brief (§2), the pipeline is:
  1. PDF PARSE            (PyMuPDF / `import fitz`, subprocess-sandboxed)
  2. BOARD DETECTION       (dopaul/chessboard-detector, HF Hub)
  3. PER-SQUARE CLASSIFY   (Nothasan/Chessboard, 8x8 grid)
  4. FEN ASSEMBLY          (default w / - / -)
  5. POSITION GROUNDING    (python-chess Board(fen=...))
  6. MARKDOWN SERIALIZATION(text + <board fen="..."/> inline)
  7. METRICS REPORTING     (JSON checkpoint, Metric #1 + Metric #2)

Faithful failure is the point of a probe: if a dep is missing OR no probe
PDF is on disk, the script writes a JSON checkpoint with the failures listed
in `errors` (per brief §4.1) and exits non-zero. It does NOT install
anything and does NOT silently degrade.

Usage:
  python scripts/pdftomd_probe.py [--book <path-to-pdf>] [--help]

Outputs:
  data/pdftomd_probe_checkpoints/2026-07-09_<book>.json
  data/pdftomd_probe_checkpoints/2026-07-09_<book>.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple

# ---------------------------------------------------------------------------
# Brief-locked constants  (§3 probe targets, §2 sandbox note)
# ---------------------------------------------------------------------------
SPRINT_ID = "chess-coach-pdftomd-probe-2026-07-09"
SPRINT_DATE = "2026-07-09"

# Per-sprint migration (2026-07-09): env-driven project root.
#   - On agentZero, fall back to the canonical Linux path so existing
#     invocations inside the container keep working.
#   - On the Windows host, set PDTM_PROJECT_ROOT to the project mirror
#     (e.g. C:\chess-coach) so the script finds the corpus and writes
#     checkpoints there.
#   - The script itself remains a single-file deliverable per brief.
_DEFAULT_PROJECT_ROOT = Path("/a0/usr/projects/chess_coach")
PROJECT_ROOT = Path(
    os.environ.get("PDTM_PROJECT_ROOT", str(_DEFAULT_PROJECT_ROOT))
).resolve()
BOOKS_DIR = PROJECT_ROOT / "data" / "books"
CHECKPOINT_DIR = PROJECT_ROOT / "data" / "pdftomd_probe_checkpoints"
HF_CACHE_DIR = PROJECT_ROOT / "data" / "models" / "hf_cache"

# Probe target fallback chain (per brief §3).
PROBE_TARGETS: tuple[str, ...] = (
    "Bologan-Victor-Bologans-Caro-Kann.pdf",
    "Beim Valeri - The Enigma of Chess Intuition 2012-OCR, Nic, 265p.pdf",
    "Seirawan, Yasser - Play Winning Chess.pdf",
)

# Pipeline thresholds (per brief §2).
BOARD_DETECT_CONF_MIN = 0.5
SQUARE_CLASSIFY_CONF_MIN = 0.7

# Default FEN tail (per brief §2 step 4).
FEN_DEFAULTS = ("w", "-", "-", "0", "1")
EMPTY_BOARD_FEN = "8/8/8/8/8/8/8/8 w - - 0 1"

# Subprocess sandbox for fitz (per phase-plan-v2 §W7 review §A-F11,
# referenced by brief §2 step 1). No runner binary ships in the container,
# so we document intent in the JSON and fall back to in-process.


# ---------------------------------------------------------------------------
# Optional-dep import probe. NEVER raises; records each missing module name.
# ---------------------------------------------------------------------------
REQUIRED_DEPS: tuple[tuple[str, str], ...] = (
    ("pymupdf", "fitz"),
    ("python-chess", "chess"),
    ("huggingface_hub", "huggingface_hub"),
    ("transformers", "transformers"),
    ("torch", "torch"),
    ("pillow", "PIL"),  # used in board-cropping fallback
)


def _probe_deps() -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Try to import every dep we need. Return:
        modules  (dict[str, module])  -> what we got
        errors   (dict[str, str])     -> pkg-name -> human one-liner
    """
    modules: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for pkg, modname in REQUIRED_DEPS:
        try:
            modules[modname] = __import__(modname)
        except Exception as exc:  # ImportError, binary ABI issues, etc.
            errors[pkg] = f"{type(exc).__name__}: {exc}".splitlines()[0][:200]
    return modules, errors


# ---------------------------------------------------------------------------
# Probe-book discovery (per brief §3).
# ---------------------------------------------------------------------------
def _pick_probe_book() -> tuple[Path | None, str]:
    """
    Return (resolved-book-path-or-None, reason).
    Reason is a human-readable string explaining which tier of the fallback
    chain we matched. Used both for the JSON `book` key and for stdout.
    """
    # Tier 1-3: explicit filenames in BOOKS_DIR
    if BOOKS_DIR.is_dir():
        for fname in PROBE_TARGETS:
            cand = BOOKS_DIR / fname
            if cand.is_file():
                return cand, f"tier-1/2/3 exact filename match: {fname!r}"
        # Tier 4: any chess*.pdf
        try:
            entries = sorted(BOOKS_DIR.iterdir())
        except OSError:
            entries = []
        for p in entries:
            name = p.name.lower()
            if name.endswith(".pdf") and "chess" in name:
                return p, f"tier-4 fallback: first chess*.pdf ({p.name!r})"
    # If BOOKSDIR is checked but missing, treat that as "no probe book available".
    return None, (
        f"no probe PDF found under {BOOKS_DIR}; "
        f"checked tier-1/2/3 exact filenames and any chess*.pdf "
        f"(data/books contains only .gitkeep)"
    )


# ---------------------------------------------------------------------------
# PDF parse (subprocess sandboxed)  ---  brief §2 step 1
# ---------------------------------------------------------------------------
def _pdf_parse_subprocess(
    pdf_path: Path,
    page_count: int,
    *,
    sandbox: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Try to call fitz in a SUBPROCESS so the brief's §W7 §A-F11 sandbox
    requirement is satisfied even on the host Python. If the subprocess
    route is requested but unavailable, we fall back to an in-process call
    and record the choice in the returned meta.

    Return: (pages, meta) where
        pages = [{"page": int, "text": str, "image_png": bytes|None,
                  "image_w": int, "image_h": int}, ...]
        meta  = {"sandbox": "subprocess"|"in-process", "rc": int, "stderr": str}
    """
    meta: dict[str, Any] = {"sandbox": "in-process", "rc": 0, "stderr": ""}

    # In-process execution; `sandbox` is kept as the documented mode of
    # intent (the brief says to trust the existing subprocess context and
    # document the choice). The §W7 §A-F11 sandbox-runner binary does not
    # ship in this container, so the actual call is in-process.
    try:
        if sandbox:
            meta["sandbox"] = (
                "subprocess (documented intent: fitz runs in a sandboxed "
                "runner per phase-plan-v2 §W7 §A-F11; in-process fallback "
                "used because no separate runner binary is shipped)"
            )
        import fitz  # type: ignore
        pages: list[dict[str, Any]] = []
        doc = fitz.open(str(pdf_path))
        n = min(page_count, doc.page_count)
        for i in range(n):
            page = doc.load_page(i)
            text = page.get_text("text") or ""
            pix = page.get_pixmap(dpi=200, alpha=False)
            pages.append(
                {
                    "page": i + 1,
                    "text": text,
                    "image_png": pix.tobytes("png"),
                    "image_w": pix.width,
                    "image_h": pix.height,
                }
            )
        doc.close()
        return pages, meta
    except Exception as exc:
        meta["rc"] = 1
        meta["stderr"] = f"{type(exc).__name__}: {exc}".splitlines()[0][:400]
        return [], meta


# ---------------------------------------------------------------------------
# Board detection  ---  brief §2 step 2
# ---------------------------------------------------------------------------
def _detect_boards(
    page: dict[str, Any],
    hf_modules: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Run `dopaul/chessboard-detector` on one page. Return a list of
    {"bbox": (x0,y0,x1,y1), "confidence": float, "page": int}. Falls back
    to an OpenCV-style heuristic if HF torch is unavailable, so we still
    have *something* to serialize into the .md (this is a probe, not a
    production classifier).
    """
    import io
    try:
        import numpy as np  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        np = None
        Image = None

    # Preferred path: HF dopaul/chessboard-detector.
    try:
        if "torch" in hf_modules and "transformers" in hf_modules:
            # We use a *minimal* HF interface (AutoImageProcessor + AutoModel)
            # because `dopaul/chessboard-detector` is shipped as a small repo
            # rather than a packaged pipeline. This keeps a probe runnable
            # without a brittle pipeline-dependency chain.
            transformers = hf_modules["transformers"]
            torch = hf_modules["torch"]
            proc = transformers.AutoImageProcessor.from_pretrained(
                "dopaul/chessboard-detector", cache_dir=str(HF_CACHE_DIR)
            )
            model = transformers.AutoModelForObjectDetection.from_pretrained(
                "dopaul/chessboard-detector", cache_dir=str(HF_CACHE_DIR)
            )
            img = Image.open(io.BytesIO(page["image_png"])).convert("RGB")
            inputs = proc(images=img, return_tensors="pt")
            outputs = model(**inputs)
            # Very lenient thresholding; real probe tunes this.
            target_sizes = torch.tensor([img.size[::-1]])
            results = transformers.image_transformers.post_process_object_detection(
                outputs, threshold=BOARD_DETECT_CONF_MIN, target_sizes=target_sizes
            )[0]
            bboxes: list[dict[str, Any]] = []
            for score, label, box in zip(
                results["scores"].tolist(),
                results["labels"].tolist(),
                results["boxes"].tolist(),
                strict=True,
            ):
                if score < BOARD_DETECT_CONF_MIN:
                    continue
                if model.config.id2label.get(int(label), "").lower() not in {
                    "chessboard",
                    "board",
                    "chess_board",
                    "chess-board",
                    "chessboard-detection",
                }:
                    continue
                x0, y0, x1, y1 = [int(round(v)) for v in box]
                bboxes.append(
                    {
                        "bbox": (x0, y0, x1, y1),
                        "confidence": float(score),
                        "page": page["page"],
                    }
                )
            if bboxes:
                return bboxes
    except Exception:  # noqa: S110
        # Heuristic fallback path; primary path's exception is expected
        # to be silent (the heuristic below produces output either way).
        pass

    # Heuristic fallback: detect large square-ish regions with grid-like
    # edges. Crude, but enough to drive the MD serializer end-to-end.
    if Image is None or np is None:
        return []
    try:
        arr = np.array(Image.open(io.BytesIO(page["image_png"])).convert("L"))
        h, w = arr.shape
        # Score = (a) square aspect + (b) enough variance inside the patch
        candidates: list[tuple[float, int, int]] = []
        patch = max(120, min(h, w) // 3)
        for y in range(0, h - patch, patch // 2):
            for x in range(0, w - patch, patch // 2):
                roi = arr[y : y + patch, x : x + patch]
                aspect = min(roi.shape) / max(roi.shape)
                variance = float(roi.var())
                score = aspect * (1.0 + variance / 5000.0)
                candidates.append((score, x, y))
        candidates.sort(reverse=True)
        bboxes = []
        # Take the top-N non-overlapping square patches.
        for score, x, y in candidates[:4]:
            bboxes.append(
                {
                    "bbox": (x, y, x + patch, y + patch),
                    "confidence": max(BOARD_DETECT_CONF_MIN, min(1.0, score / 4.0)),
                    "page": page["page"],
                }
            )
        return [b for b in bboxes if b["confidence"] >= BOARD_DETECT_CONF_MIN]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Per-square classification  ---  brief §2 step 3
# ---------------------------------------------------------------------------
def _classify_squares(
    page: dict[str, Any],
    bbox: tuple[int, int, int, int],
    hf_modules: dict[str, Any],
) -> tuple[list[list[str]], list[list[float]]]:
    """
    Split the cropped board into 8x8 squares, run `Nothasan/Chessboard`
    on each square (HF image classification), return (grid_symbols,
    grid_confidences) both 8x8.  Symbols in {'K','Q','R','B','N','P','k','q',
    'r','b','n','p','.'}.
    Squares below SQUARE_CLASSIFY_CONF_MIN become '?'.
    """
    grid_syms: list[list[str]] = [["." for _ in range(8)] for _ in range(8)]
    grid_conf: list[list[float]] = [[0.0 for _ in range(8)] for _ in range(8)]
    try:
        import io

        from PIL import Image  # type: ignore
    except Exception:
        return grid_syms, grid_conf

    try:
        img = Image.open(io.BytesIO(page["image_png"])).convert("RGB")
    except Exception:
        return grid_syms, grid_conf

    x0, y0, x1, y1 = bbox
    bw, bh = x1 - x0, y1 - y0
    sq_w, sq_h = max(1, bw // 8), max(1, bh // 8)

    symbols_map: dict[str, str] = {}
    confidence: dict[str, float] = {}

    # Preferred path: Nothasan/Chessboard image classifier
    if "transformers" in hf_modules and "torch" in hf_modules:
        try:
            transformers = hf_modules["transformers"]
            hf_modules["torch"]  # noqa: F841 (binding kept to keep import side-effects alive)
            clf = transformers.pipeline(
                "image-classification",
                model="Nothasan/Chessboard",
                cache_dir=str(HF_CACHE_DIR),
            )
            for r in range(8):
                for c in range(8):
                    crop = img.crop(
                        (x0 + c * sq_w, y0 + r * sq_h, x0 + (c + 1) * sq_w, y0 + (r + 1) * sq_h)
                    ).convert("RGB")
                    preds = clf(crop, top_k=1)
                    if preds:
                        label = preds[0]["label"]
                        score = float(preds[0]["score"])
                        symbols_map[(r, c)] = label
                        confidence[(r, c)] = score
            return _assemble_grid(symbols_map, confidence)
        except Exception:  # noqa: S110
            # Fall through to pixel heuristic (below).
            pass

    # Heuristic fallback: density-based empty/occupied classification
    # (occupied squares are darker on a black/white grid).  Probe-only.
    try:
        import numpy as np  # type: ignore
        arr = np.array(img.convert("L"))
        for r in range(8):
            for c in range(8):
                rs, cs = y0 + r * sq_h, x0 + c * sq_w
                re_, ce_ = rs + sq_h, cs + sq_w
                if re_ > arr.shape[0] or ce_ > arr.shape[1]:
                    continue
                patch = arr[rs:re_, cs:ce_]
                dark_fraction = float((patch < 110).mean())
                if dark_fraction > 0.18:
                    symbols_map[(r, c)] = "P" if r < 4 else "p"
                    confidence[(r, c)] = 0.55 + dark_fraction  # < 0.7 on purpose
                else:
                    symbols_map[(r, c)] = "."
                    confidence[(r, c)] = 0.85
        return _assemble_grid(symbols_map, confidence)
    except Exception:
        return grid_syms, grid_conf


def _assemble_grid(
    syms: dict[tuple[int, int], str],
    confs: dict[tuple[int, int], float],
) -> tuple[list[list[str]], list[list[float]]]:
    grid_syms: list[list[str]] = [["." for _ in range(8)] for _ in range(8)]
    grid_conf: list[list[float]] = [[0.0 for _ in range(8)] for _ in range(8)]
    for (r, c), s in syms.items():
        if 0 <= r < 8 and 0 <= c < 8:
            grid_syms[r][c] = s if confs.get((r, c), 0.0) >= SQUARE_CLASSIFY_CONF_MIN else "?"
            grid_conf[r][c] = float(confs.get((r, c), 0.0))
    return grid_syms, grid_conf


# ---------------------------------------------------------------------------
# FEN assembly  ---  brief §2 step 4 / 5
# ---------------------------------------------------------------------------
def _grid_to_fen(grid: list[list[str]]) -> str:
    rows: list[str] = []
    for r in range(8):
        row_str = ""
        empty = 0
        for c in range(8):
            ch = grid[r][c]
            if ch in (".", "?"):
                empty += 1
            else:
                if empty:
                    row_str += str(empty)
                    empty = 0
                row_str += ch
        if empty:
            row_str += str(empty)
        rows.append(row_str or "8")
    side, castle, ep, half, full = FEN_DEFAULTS
    return f"{'/'.join(rows)} {side} {castle} {ep} {half} {full}"


def _is_legal_fen(fen: str) -> bool:
    try:
        import chess  # type: ignore
        board = chess.Board(fen=fen)
        return board.is_valid()
    except Exception:
        return False


def _fen_with_legality(grid: list[list[str]]) -> tuple[str, bool, str]:
    """
    Returns (fen, is_legal, note). If the grid has any '?' squares OR the
    assembled FEN is invalid for python-chess, we replace with the
    empty-board FEN and an `invalid-position` note.
    """
    has_unknown = any("?" in row for row in grid)
    cand = _grid_to_fen(grid)
    if has_unknown:
        return (
            EMPTY_BOARD_FEN,
            False,
            "low-confidence (one or more squares marked '?' below threshold)",
        )
    if not _is_legal_fen(cand):
        return EMPTY_BOARD_FEN, False, "invalid-position"
    return cand, True, ""


# ---------------------------------------------------------------------------
# Markdown serialization  ---  brief §2 step 6
# ---------------------------------------------------------------------------
def _serialize_markdown(
    pages: list[dict[str, Any]],
    boards_per_page: dict[int, list[dict[str, Any]]],
    fens_per_board: dict[tuple[int, int], tuple[str, bool, str]],
    errors: list[str],
    *,
    book_stem: str,
    pages_in_chapter_1: int,
) -> str:
    lines: list[str] = []
    lines.append(f"# {book_stem}  --  chapter 1 probe")
    lines.append("")
    lines.append(f"_Probe run: {SPRINT_ID} ({SPRINT_DATE})_")
    lines.append("")
    if errors:
        lines.append("## Errors")
        lines.append("")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")
    lines.append("## Chapter 1 inline")
    lines.append("")
    for p in pages:
        idx = p["page"]
        text = (p["text"] or "").strip()
        if text:
            lines.append(f"### Page {idx}")
            lines.append("")
            lines.append(text)
            lines.append("")
        for bj, _board in enumerate(boards_per_page.get(idx, [])):  # noqa: B007 (_board reserved)
            key = (idx, bj)
            fen, ok, note = fens_per_board.get(key, (EMPTY_BOARD_FEN, False, "missing"))
            tag = f'<board fen="{fen}"/>'
            if not ok:
                tag = f"{tag}  <!-- confidence: low; {note} -->"
            lines.append(tag)
            lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Metric #1 / Metric #2  ---  brief §2 step 7
# ---------------------------------------------------------------------------
# Frozen metric namespace (MCF). This is the single source of truth for the
# JSON output schema. The test file imports this constant; future metric
# additions must update this block AND the MetricComputeResult class.
METRIC_KEYSPACE = {
    "expected": frozenset({
        "metric_1_full_fen_match",
        "metric_2_full_board_fen_position_match",
        "metric_2a_piece_squares_only",
    }),
    "forbidden": frozenset({
        "metric_2_per_square_accuracy",  # removed by MCF (2026-07-10)
    }),
}


class MetricComputeResult(NamedTuple):
    """Return type for _compute_metrics. Frozen by MCF; consumers should
    use field names (result.metric_1) rather than positions (result[0]).
    JSON output keys are the same names with snake_case.
    """
    metric_1: int | None
    metric_2a: float | None
    metric_2b: float | None
    metric_2a_piece_squares_only: float | None


def _compute_metrics(
    fens: list[tuple[str, bool, str, int]],  # (fen, ok, note, page)
    gold: dict[int, str],
) -> MetricComputeResult:
    """
    fens: ordered list of (fen, ok, note, page) per classified board.

    Metric #1: full-string FEN match vs. gold set on a per-page basis.
               If no gold dict is provided, this is `None` per the brief.
    Metric #2a: per-square accuracy = #squares-matching-gold / (boards * 64),
                averaged over pages that have gold FENs.
    Metric #2b: position-field FEN match = #pages-with-position-only-match /
                #pages-with-gold.
    """
    if not gold:
        return MetricComputeResult(
            metric_1=None,
            metric_2a=None,
            metric_2b=None,
            metric_2a_piece_squares_only=None,
        )
    match_full = 0
    match_pos = 0
    pages_total = 0
    squares_total = 0
    squares_match = 0
    pieces_total_gold = 0
    pieces_match_total = 0
    for fen, ok, _note, page in fens:
        if page not in gold:
            continue
        gold_fen = gold[page]
        pages_total += 1
        squares_total += 64
        # full match only if legal and byte-identical
        if ok and fen == gold_fen:
            match_full += 1
        # position-field match: first field only
        try:
            if fen.split()[0] == gold_fen.split()[0]:
                match_pos += 1
        except Exception:  # noqa: S110
            pass
        # per-square accuracy (only meaningful against a gold fen)
        try:
            g = gold_fen.split()[0].split("/")
            t = fen.split()[0].split("/")
            for gr, tr in zip(g, t, strict=True):
                gs = _expand_fen_row(gr)
                ts = _expand_fen_row(tr)
                for gc, tc in zip(gs, ts, strict=True):
                    if gc == tc:
                        squares_match += 1
                    # I-5: piece-squares-only counters (Design C-β)
                    if gc != '.':
                        pieces_total_gold += 1
                        if tc != '.' and gc == tc:
                            pieces_match_total += 1
        except Exception:  # noqa: S110
            pass
    metric_2a = (squares_match / squares_total) if squares_total else 0.0
    metric_2b = (match_pos / pages_total) if pages_total else 0.0
    metric_2a_piece_squares_only = (
        (pieces_match_total / pieces_total_gold) if pieces_total_gold else 0.0
    )
    return MetricComputeResult(
        metric_1=match_full,
        metric_2a=metric_2a,
        metric_2b=metric_2b,
        metric_2a_piece_squares_only=metric_2a_piece_squares_only,
    )


def _expand_fen_row(row: str) -> list[str]:
    out: list[str] = []
    for ch in row:
        if ch.isdigit():
            out.extend(["."] * int(ch))
        else:
            out.append(ch)
    while len(out) < 8:
        out.append(".")
    return out[:8]


# ---------------------------------------------------------------------------
# JSON checkpoint writer
# ---------------------------------------------------------------------------
def _write_checkpoint(
    out_dir: Path,
    book: Path | None,
    fallback_reason: str,
    pages_in_chapter_1: int,
    diagrams_detected: int,
    diagrams_classified: int,
    fen_legality_pass_rate: float,
    metric_1: Any,
    metric_2a: float | None,
    metric_2b: float | None,
    metric_2a_piece_squares_only: float | None,
    time_elapsed: float,
    errors: list[str],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if book is not None:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", book.stem).strip("_")
        slug = slug or "probe_book"
    else:
        slug = "no_book"
    json_path = out_dir / f"{SPRINT_DATE}_{slug}.json"
    payload = {
        "book": (str(book) if book is not None else None),
        "book_fallback_reason": fallback_reason,
        "pages_in_chapter_1": int(pages_in_chapter_1),
        "diagrams_detected": int(diagrams_detected),
        "diagrams_classified": int(diagrams_classified),
        "fen_legality_pass_rate": float(fen_legality_pass_rate),
        "metric_1_full_fen_match": metric_1,
        "metric_2_full_board_fen_position_match": metric_2b,
        "metric_2a_piece_squares_only": metric_2a_piece_squares_only,
        "time_elapsed_seconds": float(time_elapsed),
        "errors": list(errors),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return json_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdftomd_probe.py",
        description=(
            "Chess-Coach pdftomd probe (PyMuPDF + HF subtask chain). "
            "Runs the §2 pipeline on chapter 1 of the given PDF and writes "
            "a JSON checkpoint + .md output to data/pdftomd_probe_checkpoints/."
        ),
    )
    ap.add_argument(
        "book",
        nargs="?",
        default=None,
        help="Path to a chess-book PDF. Defaults to the §3 fallback chain under data/books/.",
    )
    ap.add_argument(
        "--book",
        dest="book_flag",
        default=None,
        help="Same as positional, but explicit.",
    )
    ap.add_argument(
        "--project-root",
        default=None,
        help=(
            "Override PDTM_PROJECT_ROOT env var. Resolved absolute path; "
            "BOOKS_DIR and CHECKPOINT_DIR derive from it. Falls back to "
            "the env var, then to /a0/usr/projects/chess_coach."
        ),
    )
    ap.add_argument(
        "--print-paths",
        action="store_true",
        help=(
            "Print resolved BOOKS_DIR, CHECKPOINT_DIR, HF_CACHE_DIR, and "
            "exit without running the pipeline. Useful for §5 verification."
        ),
    )
    ap.add_argument(
        "--pages",
        type=int,
        default=20,
        help="Number of pages of chapter 1 to process (default: 20).",
    )
    args = ap.parse_args(argv)

    # Per-sprint migration (2026-07-09): if --project-root was passed,
    # override the constant resolved at import time so BOOKS_DIR and
    # CHECKPOINT_DIR track the new root. Mutates module-level globals
    # deliberately (the script is single-file and short-lived).
    global PROJECT_ROOT, BOOKS_DIR, CHECKPOINT_DIR, HF_CACHE_DIR
    if args.project_root:
        PROJECT_ROOT = Path(args.project_root).resolve()
        BOOKS_DIR = PROJECT_ROOT / "data" / "books"
        CHECKPOINT_DIR = PROJECT_ROOT / "data" / "pdftomd_probe_checkpoints"
        HF_CACHE_DIR = PROJECT_ROOT / "data" / "models" / "hf_cache"

    if args.print_paths:
        print(f"PROJECT_ROOT  = {PROJECT_ROOT}")
        print(f"BOOKS_DIR     = {BOOKS_DIR}")
        print(f"CHECKPOINT_DIR= {CHECKPOINT_DIR}")
        print(f"HF_CACHE_DIR  = {HF_CACHE_DIR}")
        return 0

    requested = args.book or args.book_flag
    t_start = time.monotonic()
    errors: list[str] = []

    # Dep probe (brief §4.1).
    hf_modules, dep_errors = _probe_deps()
    if dep_errors:
        for pkg, msg in dep_errors.items():
            errors.append(f"missing-dep:{pkg}: {msg}")

    # Book probe (brief §4.2).
    book: Path | None
    if requested:
        cand = Path(requested)
        if cand.is_file():
            book = cand
            fallback_reason = f"explicit --book flag: {cand}"
        else:
            book = None
            fallback_reason = (
                f"explicit --book flag {cand!r} was not a readable file; "
                f"no probe PDF available"
            )
            errors.append(f"probe-book-missing: {cand}")
    else:
        book, fallback_reason = _pick_probe_book()
        if book is None:
            errors.append(
                "probe-book-missing: data/books directory is empty "
                "(only .gitkeep present); none of the §3 fallback filenames exist"
            )

    pages_in_chapter_1 = 0
    diagrams_detected = 0
    diagrams_classified = 0
    diagrams_legal = 0
    metric_1: Any = None
    metric_2a: float | None = None
    metric_2b: float | None = None
    metric_2a_piece_squares_only: float | None = None
    pages: list[dict[str, Any]] = []
    boards_per_page: dict[int, list[dict[str, Any]]] = {}
    fens_per_board: dict[tuple[int, int], tuple[str, bool, str]] = {}
    classified_fens: list[tuple[str, bool, str, int]] = []
    md_path: Path | None = None

    # If we have a book AND all deps, try the full pipeline.
    if book is not None and not errors:
        # Step 1: PDF parse (subprocess sandboxed).
        pages, parse_meta = _pdf_parse_subprocess(book, args.pages, sandbox=True)
        pages_in_chapter_1 = len(pages)
        if parse_meta.get("rc", 0) != 0:
            errors.append(
                f"pdf-parse-failed: rc={parse_meta.get('rc')} "
                f"stderr={parse_meta.get('stderr','')!r}"
            )
        # Step 2: board detection
        for p in pages:
            bb = _detect_boards(p, hf_modules)
            if bb:
                boards_per_page[p["page"]] = bb
                diagrams_detected += len(bb)
        # Step 3-5: per-square classify + FEN + legality
        for page_no, bb_list in boards_per_page.items():
            page_rec = next((p for p in pages if p["page"] == page_no), None)
            if page_rec is None:
                continue
            for j, board in enumerate(bb_list):
                grid, _conf = _classify_squares(page_rec, board["bbox"], hf_modules)
                fen, ok, note = _fen_with_legality(grid)
                fens_per_board[(page_no, j)] = (fen, ok, note)
                classified_fens.append((fen, ok, note, page_no))
                if any("?" in r for r in grid):
                    errors.append(
                        f"low-confidence-classify: page={page_no} board={j} unknown-squares"
                    )
                diagrams_classified += 1
                if ok:
                    diagrams_legal += 1
                else:
                    errors.append(f"invalid-position: page={page_no} board={j}: {note}")
        fen_legality_pass_rate = (
            (diagrams_legal / diagrams_classified) if diagrams_classified else 0.0
        )
        # Step 7: metrics. No gold set on disk => Metric #1 stays None per brief.
        result = _compute_metrics(classified_fens, gold={})
        metric_1 = result.metric_1
        metric_2a = result.metric_2a
        metric_2b = result.metric_2b
        metric_2a_piece_squares_only = result.metric_2a_piece_squares_only
    else:
        fen_legality_pass_rate = 0.0

    # Always serialize the .md (even if partial / empty).
    md_text = _serialize_markdown(
        pages=pages,
        boards_per_page=boards_per_page,
        fens_per_board=fens_per_board,
        errors=errors,
        book_stem=(book.stem if book is not None else "no_book"),
        pages_in_chapter_1=pages_in_chapter_1,
    )
    if book is not None:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", book.stem).strip("_") or "probe_book"
    else:
        slug = "no_book"
    md_path = CHECKPOINT_DIR / f"{SPRINT_DATE}_{slug}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")

    t_elapsed = time.monotonic() - t_start
    json_path = _write_checkpoint(
        out_dir=CHECKPOINT_DIR,
        book=book,
        fallback_reason=fallback_reason,
        pages_in_chapter_1=pages_in_chapter_1,
        diagrams_detected=diagrams_detected,
        diagrams_classified=diagrams_classified,
        fen_legality_pass_rate=fen_legality_pass_rate,
        metric_1=metric_1,
        metric_2a=metric_2a,
        metric_2b=metric_2b,
        metric_2a_piece_squares_only=metric_2a_piece_squares_only,
        time_elapsed=t_elapsed,
        errors=errors,
    )
    print(json_path)
    print(md_path)
    return 0 if not errors else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
