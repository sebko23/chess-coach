# FU-5 — additive `pv_moves_san` field on the narration route

**Author:** Hermes session 2026-08-06 (post-FU4-stand-up-codegen-pipeline; opened by Sebastian+Claude relay 2026-08-06).
**Branch:** starting from `main@d6a9e1e` (squash of PR #80, FU-4 codegen pipeline).
**Brief scope:** Add a human-display SAN translation of `pv_moves` as an additive `pv_moves_san` field on `/v1/narration/explain`. UCI stays authoritative on the wire (per `specs/v1.0/chess-coach-protocol-v1.md:42`); SAN is purely for the frontend's "Best Line" / "Engine line" rendering.

---

## 0. The problem at hand

`OPEN-FOLLOWUPS.md:78-79` flagged that the narration route's response carries UCI in `pv_moves` (e.g. `["e2e4", "e7e5", "g1f3"]`) but the frontend's "Best Line" card and SuggestionList's "Engine line" box render those UCI strings to humans verbatim. The frontend engine-line display reads `e2e4 e7e5 g1f3` instead of `e4 e5 Nf3`.

The protocol spec mandates UCI on the wire and explicitly permits SAN as a non-authoritative additional field. The doc-fix BBF (#79, `docs/16_audit/doc-fix-pv-moves-uci-schema.md`) three days ago corrected the same family of stale claims; this BBF closes the actual UX gap that fix was about.

## 1. Pre-implementation investigation (per directive)

Per Sebastian+Claude directive 2026-08-06: "Investigate first ... confirm the `python-chess` `Board(fen).san(move_uci)` approach actually works for a multi-move PV sequence — specifically, verify each successive SAN move needs the board state *after* the prior move is applied, not the starting FEN."

| Check | Finding |
|---|---|
| SAN is position-dependent | Verified empirically against `chess==1.11.2`. Naive `Board(fen).san(uci)` per-move emits broken SAN for any move where context (which side, file disambiguation) depends on earlier moves. Italian-game 4-ply PV `["e2e4","e7e5","g1f3","b8c6","f1c4"]`: naive emits `e4 exe5 Nf3 Nxc6 Bc4` (broken — `exe5` is not SAN, `Nxc6` is wrong disambiguation); replay emits `e4 e5 Nf3 Nc6 Bc4` (correct). |
| UCI→SAN handles all 7 move types the PV can contain | Verified live against `python-chess`: pawn (`e2e4` → `e4`), knight (`g1f3` → `Nf3`), castling kingside (`e1g1` → `O-O`), castling queenside (`e1c1` → `O-O-O`), promotion (`e7e8q` → `e8=Q`), en passant (`f5e6` → `fxe6`), capture with disambiguation (`b8c6` → `Nc6`). |
| Single-move `_uci_to_san` already exists at `services/chess_coach/gateway/routes/repertoire_recommendations.py:72` | Different call pattern (one move per gap position, not a PV sequence); correct to leave it alone. Replay-on-board required for the multi-move narration PV; per-call fresh-board pattern at repertoire_recommendations stays correct for one-move conversions. |
| Error paths | `Board(fen)` raises `ValueError` on bad FEN. `Move.from_uci(u)` raises `chess.InvalidMoveError` on off-board squares. `board.san(move)` raises `ValueError` on legal-shape-but-position-illegal moves. None of these should propagate to the route handler — UCI fallback is correct behavior because UCI is the authoritative wire format. |
| Protocol-spec authority | Verified verbatim: `specs/v1.0/chess-coach-protocol-v1.md:42` reads "Move notation is **UCI** (`e2e4`, `g1f3`, `e7e8q`) on the wire. SAN may be returned as an additional field for human display but is never authoritative." Same citation used three days ago in BBF #79 doc-fix. |
| Frontend surface | Verified: `apps/desktop/src/components/panels/coach/CoachPanel.tsx:225-237` renders `result.pv_moves` in the "Best Line" card via the `PVLine` component; line 279 passes the same `pv_moves` as `pvMoves=` prop to `SuggestionList`. `SuggestionList.tsx:84-87` renders `pvMoves.slice(0, 8).join(" ")` as the "Engine line" box. Out of scope per directive: `EvalGraph.tsx`'s `point.best_move` (separate `/v1/games/{game_id}/eval-graph` endpoint) and blunder-list `b.move_san`/`b.best_move` (separate data sources). |
| LLM prompt path | Verified: `services/chess_coach/narration/prompt.py:40` joins `pv.moves[:6]` as-is (raw UCI) into `format_analysis_for_prompt`. LLM has been reading UCI in its prompt with no reported issue. Per directive, leave untouched — touching it would be unvalidated scope-creep. |
| Codegen pipeline | Verified: `scripts/codegen/gen-api.mjs` regenerates `apps/desktop/src/services/coach/api.ts` from `.openapi.json`. New `pv_moves_san` field on `NarrationResponse` will appear in the regenerated `api.ts` automatically. CI job `frontend-types-codegen` (added by PR #80) gates this with a `--check` diff. |

## 2. The design

### Backend

1. **`services/chess_coach/narration/pipeline.py`** — add `_pv_to_san(fen, uci_moves)` pure-function helper. Build `chess.Board(fen)` once, replay each UCI in order, collect `board.san(move)` per move. On any error per move (bad UCI, illegal-in-position, promotion suffix missing), fall back to the UCI string for that move and log a warning; never raise. Returns `list[str]` aligned 1:1 with the input.

2. **`_format_pv_fields(result)`** — extend to return `(pv_moves_uci, pv_moves_san, score_display)`. UCI list unchanged (already sliced to 6 plies); SAN list is the same 6 plies converted via `_pv_to_san`. This is the single call site all three narration paths converge on (engine-backed `pipeline.explain()`, synthetic `explain_simple()`, template fallback).

3. **`NarrationOutput` dataclass** — add `pv_moves_san: list[str]` field alongside existing `pv_moves: list[str]`.

4. **`libs/chess_coach/protocol_types/narration.py`** — add `pv_moves_san: list[str]` field to `NarrationResponse`, marked as `description=... "human-display only; UCI in `pv_moves` is authoritative per protocol §1.2"`. `NarrationRouteResponse` (which subclasses `NarrationResponse` in the route file) inherits the new field automatically.

5. **`services/chess_coach/gateway/routes/narration.py`** — populate `pv_moves_san` alongside `pv_moves` in both the engine-backed branch (line 186) and the synthetic `explain_simple()` branch (line 277). Also populate it in the engine-backed LLM-unavailable and bad-request fallbacks (which currently emit empty `pv_moves: []`) — an empty UCI list translates to an empty SAN list, no special handling needed.

### Frontend

6. **`apps/desktop/src/state/atoms/coach.ts`** — add `pv_moves_san?: string[]` to `NarrationResult` interface. Optional field, so older cached responses (without the field) still parse cleanly.

7. **`apps/desktop/src/components/panels/coach/CoachPanel.tsx`** — change the "Best Line" card (line 233, `moves={result.pv_moves}`) to use `result.pv_moves_san ?? result.pv_moves`. Same for the `pvMoves=` prop on line 279. Fallback chain preserves behavior against older backends or stale cached responses.

8. **`apps/desktop/src/components/panels/coach/SuggestionList.tsx`** — no signature change needed; receives the already-resolved list via the `pvMoves` prop. The fallback resolution happens at the call site in `CoachPanel.tsx`.

9. **`apps/desktop/src/services/coach/api.ts`** — regenerated via `pnpm gen:api`. CI `frontend-types-codegen` job verifies it's up-to-date.

### Tests

10. **`tests/unit/test_pv_to_san.py`** (new) — covers the 7 move types (pawn, knight, castling kingside, castling queenside, promotion, en passant, capture-with-disambiguation), plus multi-move replay (the Italian 4-ply line as the canonical case), plus error paths (bad FEN, malformed UCI, position-illegal move → UCI fallback, no raise). Also covers the `_format_pv_fields` extension (returns 3-tuple now; UCI list unchanged).

11. **`tests/integration/test_narration_pv_moves_san.py`** (new) — boots the gateway in-process via the existing fixture pattern (see `tests/integration/test_narration_engine_pool.py` for the established shape). Asserts the response carries both `pv_moves` (UCI, unchanged) and `pv_moves_san` (SAN, length-aligned). Engine-backed and synthetic paths both checked.

## 3. What ships

Backend: 4 files changed (pipeline.py, narration.py protocol_types, narration.py route, plus pipeline test fixture if needed).
Frontend: 3 files changed (atoms/coach.ts, CoachPanel.tsx, SuggestionList.tsx) + 1 regenerated (api.ts).
Tests: 2 new test files.

Estimated diff: ~200 lines backend + ~30 lines frontend + ~250 lines tests + regenerated api.ts.

## 4. Verification (planned)

- `ast.parse` and `ruff check` clean on every touched file.
- Unit: `tests/unit/test_pv_to_san.py` — all move-type cases + replay + error paths green.
- Integration: `tests/integration/test_narration_pv_moves_san.py` — engine-backed and synthetic paths both green.
- Pre-existing integration tests must stay green: `tests/integration/test_narration_engine_pool.py:172` still asserts `body["pv_moves"] == ["e2e4", "e7e5", "g1f3"]` (UCI unchanged).
- Codegen: `pnpm gen:api` regenerates `api.ts`; `pnpm gen:api:check` confirms parity. The diff in `api.ts` should be purely additive (new `pv_moves_san?: string[]` field on the route-response type).

## 5. Out of scope (separately logged if needed)

- EvalGraph.tsx `best_move` rendering — different endpoint (`/v1/games/{game_id}/eval-graph`), separate work item.
- Blunder-list rendering — `b.move_san` and `b.best_move` come from `/v1/blunders/by-fen`; not in directive's frontend scope.
- LLM prompt — `format_analysis_for_prompt` keeps raw UCI per directive (no evidence LLM needs SAN; touching would be unvalidated scope-creep).
- `_template_fallback` — renders the human-facing fallback text (`f"The best continuation is {moves_str}."`); per directive "unless it's rendering the same list for a human — check, but don't change the LLM-facing path." The template fallback uses `_format_pv_fields` which I'm extending — its output will now include SAN. Acceptable because the template fallback is human-facing, not LLM-facing.
- `repertoire_recommendations._uci_to_san` — single-move helper with different call pattern; correct as-is.

## 6. Authorization trail

Sebastian+Claude directive 2026-08-06 (FU-5 explicit reopen): "**Surface needing SAN: response `pv_moves` display only, via a new field — not the LLM prompt.** ... **Option B, not A** — additive `pv_moves_san` field, `pv_moves` stays UCI. ... **Both test levels** ... One addition to scope, or this doesn't actually fix the thing that motivated it: update the frontend's 'Best Line' rendering (`CoachPanel.tsx`, `SuggestionList.tsx`) to display `pv_moves_san` instead of `pv_moves`, with a fallback to `pv_moves` if the new field is ever absent."

Confirmations 2026-08-06: (1) "The frontend scope is exactly `CoachPanel.tsx` (the Best Line card and the `pvMoves=` prop passed to `SuggestionList`) and `SuggestionList.tsx` (the Engine line box) — nothing else." (2) "`EvalGraph.tsx`'s `point.best_move` rendering is out of scope for this BBF, since it comes from the separate `/v1/games/{game_id}/eval-graph` endpoint, not `/v1/narration/explain`, and changing it would require its own separate schema change."

Standard conditions unchanged: pre-verify any leaf-review finding, real pytest output, CI baseline-signature check, explicit full-sentence confirmation before any squash-merge.

**End of brief.**