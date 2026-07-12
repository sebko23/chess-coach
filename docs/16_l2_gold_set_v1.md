# L-2 Gold Set v1 — Methodology + Extension Guide

**Sprint**: chess-coach-pdftomd-probe-l2-gold-set-2026-07-10
**Stub deliverable**: 8-page gold set for end-to-end probe verification.
**Status**: stub (real gold set is multi-week per §22.6 of idea memo).

## What is this file?

The probe (`scripts/pdftomd_probe.py`, post-MCF-FU canonical) emits Metric #1, Metric #2a, Metric #2b, and Metric #2a-pso, all of which are computed *against a gold set*. Without a gold set, all three metrics return `None` (the I-4 tri-state contract). This file documents the **stub gold set** that closes the loop enough to verify the gate-evaluation pipeline.

## Methodology

Each entry in `tests/gold/chess_gold_set_v1.json` is a JSON object mapping page numbers (1-indexed) to verified FEN strings. FENs are 6-field standard chess FEN strings (piece placement, side to move, castling, en-passant, halfmove clock, fullmove number).

Construction steps that produced this v1 stub:

1. **Inventory PDFs** — Inspected `data/books/` in the agentZero container. Directory is empty (only `.gitkeep` present), as confirmed by prior sprint `pdftomd-probe-2026-07-09`'s checkpoint at `data/pdftomd_probe_checkpoints/2026-07-09_no_book.md`. Therefore no PDF-derived FENs were possible for this stub.
2. **Synthesize from canonical positions** — Selected 8 unambiguous, well-known positions spanning initial setup, one-pawn opening moves, common endgames (kings-only, K+R vs K), and an empty board (no-diagram placeholder).
3. **Hand-verify each FEN** — For every entry, manually confirmed: (a) 6 space-separated fields; (b) each of the 8 ranks sums to exactly 8 squares; (c) castling rights match which king/rook have moved; (d) en-passant target square sits immediately behind the just-moved pawn; (e) halfmove counter resets on pawn moves/captures; (f) fullmove counter increments after Black's move.

## What's in this v1 stub

- **8 pages**, hand-verified (brief specifies minimum 5; extended to 8).
- Each page sourced from a canonical chess position (no PDF-derived entries possible in this sprint because `data/books/` is empty).
- Position types covered: initial setup (1), opening pawn move (2, 5), opening pawn move + response (6), empty board (3), king-vs-king endgame (4), K+R vs K endgame setup (7), castling-rights position (8).

## What's NOT in this stub

- LICHESS / chess.com diagram annotations.
- YOLOv8-detected diagram crops.
- Hand-annotated variation trees.
- Statistical accuracy claims of any kind — 8 pages is far too few for a meaningful measurement.
- Any PDF-derived FENs (blocked by empty `data/books/`; deferred to follow-up sprint that populates the corpus).

## Schema

The JSON file uses page numbers (1-indexed, as JSON-string keys) mapped to FEN strings:

```json
{
  "1": "<FEN>",
  "2": "<FEN>",
  ...
  "8": "<FEN>"
}
```

The `_meta` block at the top is a non-page-numbered descriptive header. Test code ignores it (loads only integer-keyed entries).

A valid FEN has exactly **6 space-separated fields**:

| # | Field          | Example        |
|---|----------------|----------------|
| 1 | piece placement | `rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR` |
| 2 | side to move   | `w` or `b`     |
| 3 | castling       | `KQkq`, `K`, `-`, etc. |
| 4 | en-passant     | `e3`, `-`     |
| 5 | halfmove clock | `0`            |
| 6 | fullmove number | `1`           |

## How to extend

1. Add a real chess-book PDF to `data/books/` (out of stub scope — Phase 6 corpus assembly).
2. Run the probe on a new page.
3. Note the probe's classified FEN.
4. Verify the FEN by looking it up against a trusted source (lichess analysis API, chess.com diagram, hand-verification).
5. Add the page number (next integer) and verified FEN to `chess_gold_set_v1.json` (or v2, v3, etc.).
6. Run `python3 -c "import sys, importlib.util; sys.path.insert(0, 'tests/integration'); import test_probe_with_gold_set; test_probe_with_gold_set.test_gold_set_is_loadable(); print('LOAD_OK')"` to confirm.

When extending past 50 pages, prefer bumping the schema version to v2 and writing a fresh `tests/gold/chess_gold_set_v2.json`, rather than mutating v1 (sprints use v1 as a stable baseline).

## Why this is a stub

Phase 6 of `phase-plan-v2.md` (weeks 21-32) is the **real** gold-set construction phase: 6-12 weeks of dataset assembly (W1), YOLOv8 fine-tune (W2), piece classifier (W3), PaddleOCR (W4), validation pipeline (W5), pipeline integration (W6), PDF parser isolation (W7), manual-review queue UI (W8). This stub sprint is a placeholder for Phase 6 work, not a substitute. Per §22.6: "Multi-week (estimated 4-6 weeks for real gold set; 1-2 days for stub)."

The stub is **deliberately smaller than statistically meaningful**: its only job is to demonstrate end-to-end closure of the gate-evaluation pipeline, so future sprints can iterate on the real gold set without re-proving the integration scaffolding.
