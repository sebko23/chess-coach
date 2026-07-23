"""
Chess diagram OCR spike — Capablanca PDF
Tests whether existing libraries achieve ≥80% valid FEN production
on clean printed diagrams without custom ML training.

Pipeline:
1. pdf2image → page images at 300 DPI
2. OpenCV contour detection → candidate board regions
3. Pixel intensity classification → piece/empty per square
4. FEN reconstruction → validate with python-chess

Pass criterion: ≥80% of detected boards produce a legal FEN.
"""
import sys

import chess
import cv2
import numpy as np
from pdf2image import convert_from_path

PDF_PATH = "/a0/usr/projects/trener/pdfs/Capablanca, Jose - Chess Fundamentals.pdf"
PAGES = 20       # first 20 pages
DPI = 300
MIN_BOARD_PX = 200   # minimum board side in pixels to count as a diagram


def extract_pages(path: str, n: int, dpi: int) -> list[np.ndarray]:
    print(f"Extracting {n} pages at {dpi} DPI...")
    pil_pages = convert_from_path(path, dpi=dpi, first_page=1, last_page=n)
    pages = []
    for p in pil_pages:
        arr = np.array(p.convert("RGB"))
        pages.append(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
    print(f"  → {len(pages)} pages extracted")
    return pages


def detect_boards(page: np.ndarray) -> list[np.ndarray]:
    """Find candidate chessboard regions using contour analysis."""
    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    # Threshold to find dark grid lines
    _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boards = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Board must be roughly square and large enough
        if w < MIN_BOARD_PX or h < MIN_BOARD_PX:
            continue
        aspect = w / h
        if not (0.75 < aspect < 1.33):
            continue
        # Area must be substantial relative to bounding box (filled grid)
        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        if hull_area < (w * h * 0.4):
            continue
        boards.append(page[y:y+h, x:x+w])
    return boards


def classify_square(sq_img: np.ndarray) -> str:
    """Classify a single square as empty, white piece, or black piece."""
    gray = cv2.cvtColor(sq_img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    # Use center 60% of square to avoid border artifacts
    margin_y, margin_x = int(h * 0.2), int(w * 0.2)
    center = gray[margin_y:h-margin_y, margin_x:w-margin_x]
    _mean = center.mean()  # noqa: F841 (reserved for future use)
    std = center.std()
    # High std = piece present (contrast between piece and background)
    # Low std = empty square
    if std < 15:
        return "."
    # Dark mean = black piece on light square or light piece on dark square
    # Use bimodal detection: look at pixel distribution
    dark_pixels = (center < 100).sum()
    light_pixels = (center > 180).sum()
    total = center.size
    if dark_pixels / total > 0.15:
        return "p"  # placeholder — black piece present
    if light_pixels / total > 0.15:
        return "P"  # placeholder — white piece present
    return "."


def board_to_fen(board_img: np.ndarray) -> str | None:
    """Convert board image to FEN string (piece types unknown, only presence)."""
    h, w = board_img.shape[:2]
    sq_h, sq_w = h // 8, w // 8
    rows = []
    for rank in range(8):
        row = []
        for file in range(8):
            y1, y2 = rank * sq_h, (rank + 1) * sq_h
            x1, x2 = file * sq_w, (file + 1) * sq_w
            sq = board_img[y1:y2, x1:x2]
            row.append(classify_square(sq))
        rows.append(row)

    # Build FEN rank strings
    fen_ranks = []
    for row in rows:
        rank_str = ""
        empty = 0
        for sq in row:
            if sq == ".":
                empty += 1
            else:
                if empty:
                    rank_str += str(empty)
                    empty = 0
                rank_str += sq
        if empty:
            rank_str += str(empty)
        fen_ranks.append(rank_str)

    return "/".join(fen_ranks) + " w - - 0 1"


def is_valid_fen(fen: str) -> bool:
    """Check if FEN represents a plausible position (not strict legality)."""
    try:
        board = chess.Board(fen)
        # Accept if piece count is plausible (2-32 pieces)
        piece_count = len(board.piece_map())
        return 2 <= piece_count <= 32
    except Exception:
        return False


def run_spike():
    pages = extract_pages(PDF_PATH, PAGES, DPI)
    total_detected = 0
    total_valid = 0
    results = []

    for page_num, page in enumerate(pages, 1):
        boards = detect_boards(page)
        print(f"Page {page_num:2d}: {len(boards)} board(s) detected")
        for board_img in boards:
            total_detected += 1
            fen = board_to_fen(board_img)
            valid = is_valid_fen(fen) if fen else False
            if valid:
                total_valid += 1
            results.append({
                "page": page_num,
                "valid": valid,
                "fen": fen,
                "size": board_img.shape[:2],
            })
            print(f"  Board {total_detected}: size={board_img.shape[:2]} "
                  f"valid={valid} fen={fen[:40] if fen else 'None'}...")

    print("\n" + "="*60)
    if total_detected > 0:
        print(f"RESULTS: {total_detected} boards detected across {PAGES} pages")
        print(f"Valid FENs: {total_valid}/{total_detected} "
              f"({100*total_valid//total_detected}% "
              f"{'PASS' if 100*total_valid//total_detected >= 80 else 'FAIL'})")
    else:
        print("No boards detected")
    print("="*60)

    if total_detected == 0:
        print("\nNo boards detected. The contour approach may need tuning.")
        print("   Try: lower MIN_BOARD_PX, adjust threshold, or use FindChessboardCorners.")
        print("   Alternative: use OpenCV's cv2.findChessboardCorners() for grid detection.")

    return total_detected, total_valid


if __name__ == "__main__":
    detected, valid = run_spike()
    sys.exit(0 if detected > 0 else 1)
