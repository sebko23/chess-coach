# BBF-FU-11 — Polyglot persistent-book support (β) design decision

**Status:** OPEN. Brief awaiting leaf review and squash-merge to `main` before any code is written.
**Author:** Hermes session 2026-10-12 (post-P2d, option-α from the FYI on FU-7).
**Parent:** FU-11 in `OPEN-FOLLOWUPS.md` line 776; writer artifact at `services/chess_coach/repertoire/polyglot_writer.py` (SHA `91009f08…`, FU-11 alpha-precursor per the FYI on FU-7 line 420).
**Brief scope:** "FU-11 design decision — answer the three undecided questions the ledger flags, propose a concrete product surface, sequence the implementation BBFs, defer the rest."

This is a **decision-only BBF** (per the v0.7.103 strategic-decision-bbf-pattern). The diff is `*.md` only. No code is shipped by this BBF. The implementation BBFs that follow reference this brief on `main`.

---

## 0. The decision at hand

FU-11 (per the ledger line 776-828) is the **β** half of the Polyglot opening-book work: server-managed persistent book state, the Phase 2 trigger point, explicitly out of α scope. The ledger enumerates five properties that put β outside the FU-7 α scope (line 802-808), and one boundary statement that makes the scope crisp (line 813): **α is per-call, stateless, no side-effects; β is anything that persists, indexes, or remembers**.

The ledger line 791-794 also names three questions that are **explicitly undecided** for β:

> β: server-managed persistent book state. Uploading a `.bin` once, **naming it (player-scoped? repertoire-scoped? user-scoped?)**, querying it across calls, possibly indexing it for fast lookup, **possibly combining multiple books for a single player**. This is the Phase 2 trigger point — a real product surface, not a continuation of α.

And line 810 lists additional open questions that the β surface has to answer:

> If α's `polyglot_book_path` field starts growing into a "set this for the session" or "remember this path for this player" semantic, that's β scope-creep into α. The boundary: α is **per-call, stateless, no side-effects**; β is anything that persists, indexes, or remembers.

This brief proposes:

> **Decision (FU-11 β, this brief):** A **per-player, single-active-book** model served by **three endpoints** (`PUT` to set, `GET` to retrieve metadata, `DELETE` to clear), persisted under `data_dir/books/<player>.bin`, using a **write-permission extension** to the existing single-bearer-token auth model. Multiple books per player and library-level discovery are explicitly deferred to a v1.x follow-up.

Three plausible alternative shapes are catalogued in §2 with their tradeoffs. The reasoning that picks the recommendation is in §0.1. The sequencing (which BBF lands the route, which BBF lands the auth extension, which BBF lands the FU-11 entry ledger update) is in §3.

### 0.1 Why this decision (one paragraph)

The simplest shape that satisfies "per-call stateless" → "anything that persists" boundary is **one book per player, persisted on disk, surfaced by an opt-in read from the existing α route**. The writer is already done (FU-11 alpha-precursor, `91009f08…`, 6/6 tests, byte-round-trip verified). The α route already has a `polyglot_book_path` field that callers supply; the natural β extension is "if no path is supplied and the player has a stored book, the server uses the stored one." That is **one** new write endpoint, **one** new read endpoint (or a metadata-only one), **zero** changes to the α route's signature, and **zero** new auth surface beyond a write-permission token. Library / multi-book / user-scoped shapes are real features, but each is its own surface, its own auth consideration, its own design decision — folding any of them into v1.0 doubles the scope of a release-cut that is already at ~75%.

---

## 1. Current state (live, this session)

### 1.1 What the ledger says

- **FU-7 (α)** resolved 2026-08-08 via PR #84 (commit `7180433`). On `main` for several sessions. The α surface is the in-memory per-call `polyglot_book_path` query field on `POST /v1/repertoire/{player}/recommendations` (route file `services/chess_coach/gateway/routes/repertoire_recommendations.py:216-224`).
- **FU-11 (β)** OPEN, deferred to Phase 2 trigger. The ledger's own boundary statement: "α is per-call, stateless, no side-effects; β is anything that persists, indexes, or remembers." (line 813)
- **FYI on FU-7** (line 420, this session): writer artifact at `services/chess_coach/repertoire/polyglot_writer.py` (SHA `91009f08…`, untracked) is preserved as FU-11 alpha-precursor, per Sebastian's option-(α) decision. The FYI instructs the next session: "stage the writer as the first sub-piece of the FU-11 BBF (not duplicate, not re-implement, not discard)."
- **The five properties that make β out of α scope** (per ledger line 802-808): persistence, new protocol surface, auth-model change, possible indexing, long-running state with backup/cleanup.

### 1.2 What the code says (live, this session)

| Surface | Location | Relevant property |
|---|---|---|
| α route | `services/chess_coach/gateway/routes/repertoire_recommendations.py:203-398` | Already reads `polyglot_book_path` from the query string. No state, no write endpoint, no storage touch. |
| α helper | `services/chess_coach/gateway/routes/repertoire_recommendations.py:150-200` | `_book_moves_for_fen()` is the natural extraction point for a `BookIndex` abstraction per the ledger line 825-828. |
| Auth | `services/chess_coach/gateway/auth.py:46-49` | Single-bearer-token via `require_bearer` dep. `_active_token` is global, set from `backend_token` env var or auto-generated. No read vs write distinction. |
| Settings | `services/chess_coach/gateway/config.py:62-93` | `data_dir` is the natural root for `data_dir/books/`. `backups_dir` already exists at `data_dir/backups/` (line 83-84) — same lifecycle pattern. |
| Routes | `services/chess_coach/gateway/routes/__init__.py:21-22` | `repertoire_router` and `repertoire_recommendations_router` both registered. New β router plugs into the same `repertoire` tag. |
| App | `services/chess_coach/gateway/app.py:356, 359` | Both `repertoire_router` and `repertoire_recommendations_router` are already wired. |
| Tests | `tests/integration/test_repertoire_recommendations_polyglot.py` | 8 α integration tests (hand-roll Polyglot `.bin` via `struct.pack` in `tmp_path`). The β route's tests can extend the same `_make_app_with_engine()` / `_make_aiosqlite_patch()` / `_active_token_lifecycle()` fixture pattern. |

### 1.3 What the writer says (live, this session)

`services/chess_coach/repertoire/polyglot_writer.py` (SHA `91009f08…`):

- `BookEntry` dataclass: `fen: str`, `uci_move: str`, `weight: int = 100`, `learn: int = 0`.
- `write_polyglot_book(entries, path) -> int`: writes a flat array of 16-byte entries sorted by zobrist hash. No magic header. Empty book = 0 bytes. **6/6 unit tests passing, byte-round-trip verified (the load-bearing assertion is `find_all()` returns the entries we wrote).**
- The writer validates: illegal move (FEN+UCI mismatch) → `ValueError("Move ... is not legal from FEN ...")`, weight out of range → `ValueError("Weight ... out of range")`.
- The writer does **NOT** validate: path location (sandboxing, traversal), file size, number of entries. Those are the route layer's responsibility.
- Reused by the α integration test's hand-rolled `_make_polyglot_bin()` (per `test_repertoire_recommendations_polyglot.py:42-62`) — same struct layout, same bit encoding, same zobrist sort. The α test could be refactored to call `write_polyglot_book` instead of hand-rolling, but that's a separate cleanup BBF, not in scope for FU-11.

### 1.4 What the tests say (live, this session)

- `pytest tests/unit/test_polyglot_writer.py` → **6/6 passing in 0.20s**.
- `pytest tests/unit` (broader) → **74 failed, 408 passed, 3 skipped**. Baseline matches the handoff; no regression from the writer work.
- `ruff check services/chess_coach/repertoire/polyglot_writer.py tests/unit/test_polyglot_writer.py` → **All checks passed**.

---

## 2. The decision — three named options

The three open questions from the ledger map to three independent design dimensions. Each option picks one value per dimension. The options are catalogued in the order **simplest → most ambitious**. The recommendation in §0 picks the simplest per dimension.

### 2.1 The three design dimensions

| Dimension | Ledger question | Choices |
|---|---|---|
| **Ownership** | "naming it (player-scoped? repertoire-scoped? user-scoped?)" | (A) per-player (one book per `{player}`) (B) per-repertoire (one book per `{player}+{color}`) (C) per-user (one book per authenticated token, independent of player) (D) global (one default book, no scoping) |
| **Surface** | "upload endpoint? library endpoint? per-player default book? — none decided yet" | (A) upload (PUT) + metadata (GET) + clear (DELETE) only (B) full library (list, get, upload, delete) (C) per-player default (PUT/GET single slot) (D) full CRUD with versioning |
| **Auth** | "uploads need write-permission, not just read" | (A) write-permission token extension (separate read token, write token) (B) scope-based (`require_scope("books:write")`) (C) write-only require a fresh `require_bearer` dep with stricter env var (D) defer (rely on the network trust boundary, like the α route does) |

### 2.2 The three named options

| Option | Ownership | Surface | Auth | Complexity | Net-new endpoints | Net-new storage |
|---|---|---|---|---|---|---|
| **α-ext** (RECOMMENDED) | per-player | upload + metadata + clear (PUT / GET / DELETE on one slot) | scope-based (add `BOOKS_WRITE` scope to the existing bearer token) | ~1 BBF | 3 | `data_dir/books/<player>.bin` |
| **α+lib** | per-player | full library (list, get, upload, delete, combine) | scope-based | ~3 BBFs (library, combine, library-tests) | 5+ | `data_dir/books/<player>/<book-id>.bin` + index |
| **β-min** | per-repertoire | upload only (PUT) | defer to network trust boundary | ~1 BBF but limits future β | 1 | `data_dir/books/<player>-<color>.bin` |

The recommendation in §0 is **α-ext**. The two alternatives are documented for completeness; they are not recommended.

### 2.3 Why α-ext (the recommended option)

1. **Smallest surface that satisfies the FU-11 boundary statement.** "α is per-call, stateless, no side-effects; β is anything that persists, indexes, or remembers." A single per-player slot is the smallest "persists, remembers" surface that still passes as a real β feature. It is the Phase 2 trigger, not the Phase 2 product.
2. **Zero changes to the α route's signature.** The α route's `polyglot_book_path` query field is untouched. β can layer on top: "if no path is supplied and the player has a stored book, the server uses the stored one" is a 3-line change to `_analyze_row()` in `repertoire_recommendations.py:260` and is forward-compatible with the existing 8 α integration tests.
3. **Write-permission is a real, separate concern.** The current `require_bearer` dep (auth.py:46-49) treats all authed callers the same. The ledger line 805 explicitly calls out the auth-model change as a β property. A scope-based extension (option 2.1 auth-choice A) is the simplest shape that introduces write-permission without introducing user-identity. The token format change is additive: a token with no scope = read-only (current behavior); a token with `BOOKS_WRITE` = read+write.
4. **The writer is the natural starting point.** Stage `services/chess_coach/repertoire/polyglot_writer.py` (SHA `91009f08…`, 6/6 tests, byte-round-trip verified) as the first sub-piece of the FU-11 BBF. No re-implementation. No new spec.
5. **The data-dir convention is already in place.** `GatewaySettings.data_dir` (config.py:62-68) is the home of `sqlite/`, `runtime/`, `backups/`. Adding `books/<player>.bin` is a one-line addition to `config.py` and follows the existing pattern (e.g., `backups_dir` property at config.py:83-84).

### 2.4 Why NOT α+lib (full library, multi-book, combine)

- **Triples the scope** (5+ endpoints, an index, a combine algorithm, library tests) for a feature that the ledger explicitly says is "the Phase 2 trigger point" — i.e., a foothold, not a product.
- **The combine algorithm is its own design decision.** Multiple books per player requires a "what happens if book A and book B both have e2e4 with different weights" rule. The FU-7 blending (iv) rule (per-move union, no arbitration) is the α answer; the β combine rule is a different answer that the ledger has not specified.
- **Indexing requirement is real.** The ledger line 808 explicitly notes "β wants fast multi-player lookup, which may need a different storage choice." Building a SQLite index on top of the books is a real BBF. Defer.

### 2.5 Why NOT β-min (per-repertoire, no auth, upload-only)

- **Per-repertoire is a more aggressive scope** than per-player. The existing α route is per-player (`POST /v1/repertoire/{player}/recommendations`, query param `color=white|black`). A per-repertoire β would split `{player}` into `{player}-white` and `{player}-black` storage, which means the natural "set my default for this player" UX is two writes, not one. Wrong shape.
- **No auth is a non-starter.** The ledger line 805 explicitly flags the auth-model change as a β property. Deferring it (option 2.1 auth-choice D) means a malicious caller who can reach the gateway can overwrite any player's book. v1.0 is a Linux dev platform (Framing β, per §6.7), but "dev platform" is not "no auth at all" — the α route is auth-required and the β write endpoint must be at least as strict.

### 2.6 What α-ext does NOT include (explicitly out of scope, deferred to v1.x)

- **Multi-book per player.** A player can have at most one stored book. The PUT endpoint overwrites.
- **Library listing / discovery.** No "list my books" endpoint. The single slot is the entire surface.
- **Combine across books.** Not applicable — there is only one book per player.
- **Indexing.** File-backed mmap is the read path, same as α's per-call mmap. No SQLite index.
- **Backup / cleanup automation.** The data-dir convention handles this at the OS level; no per-book rotation.
- **User-identity model.** The bearer token is single-identity (current). Multi-user is a separate surface.

---

## 3. Sequencing — implementation BBFs that follow this brief

The recommended path is three BBFs in sequence, each one a squash-merge-per-BBF commit with its own branch + PR + leaf review + CI green + `go <id>` cycle.

### 3.1 BBF-FU-11a — Auth scope extension (smallest, ships first)

**Scope:** Add the scope-based auth dep. The current `require_bearer` dep is augmented with a new `require_bearer_with_scope(scope: str)` that checks for a `BOOKS_WRITE` claim in the token (or, in the absence of any scope, treats the token as read-only). The token format is extended: a token with the form `devtoken123:BOOKS_WRITE` has write scope; a plain `devtoken123` has read-only.

**Files:**
- `services/chess_coach/gateway/auth.py` — add `require_bearer_with_scope` dep. Extend `_check_bearer` to parse `:SCOPE` suffix. Update the `_active_token` global to track per-token scopes.
- `tests/unit/test_auth_scope.py` (NEW) — unit tests for the scope parsing, including edge cases: empty scope, multiple scopes, malformed `:`, scope with whitespace, scope-only token (no leading secret).
- `tests/integration/test_repertoire_recommendations_polyglot.py` — extend the `_active_token_lifecycle` autouse fixture to set a read-only token, then add one new test for the write-scope token path (verifies a route with `Depends(require_bearer_with_scope("BOOKS_WRITE"))` rejects a read-only token with 401 and accepts a write-scope token with 200/whatever).

**Acceptance:**
- All existing tests pass unchanged.
- New unit tests pass.
- The α route is unchanged in behavior (it uses `require_bearer`, which is now read-only-equivalent — callers who need write access to a future β endpoint must opt in to `BOOKS_WRITE`).
- The ledger entry for FU-11 is updated to note "scope-based auth model is now in place; the write endpoint can land."

**Risk:** Low. The change is additive: existing tokens continue to work. The only behavior change is that the new dep is the only path to write access, which is exactly what the ledger requested.

**Tool budget:** ~25 tool calls. The brief-vs-code divergence check (BBF-FU-11a vs. the live auth.py) takes ~3 calls; the implementation is ~15; tests + verification ~7.

### 3.2 BBF-FU-11b — β route + writer integration (the load-bearing BBF)

**Scope:** Add three endpoints. Stage the writer as the first sub-piece.

**Files:**
- `services/chess_coach/repertoire/__init__.py` (NEW, empty) — the package init for the new `repertoire/` sub-tree. (The writer is already there from the FYI alpha-precursor; the package just needs an `__init__.py` to be importable.)
- `services/chess_coach/gateway/routes/repertoire_book.py` (NEW) — three endpoints:
  - `PUT /v1/repertoire/{player}/book` — body is a list of `BookEntry` JSON objects. Writes to `data_dir/books/<player>.bin` via `write_polyglot_book()`. Returns `{"player": "...", "size_bytes": N, "entry_count": M}`.
  - `GET /v1/repertoire/{player}/book` — returns the metadata (size, mtime, entry count) WITHOUT returning the binary content. Body is empty. Returns `{"player": "...", "size_bytes": N, "entry_count": M, "last_modified": "ISO-8601"}`.
  - `DELETE /v1/repertoire/{player}/book` — removes `data_dir/books/<player>.bin`. Returns `{"player": "...", "deleted": true}`. Idempotent (already-gone = `{"player": "...", "deleted": false, "reason": "no book stored"}`).
- `services/chess_coach/gateway/routes/__init__.py` — add `from .repertoire_book import router as repertoire_book_router` (line 21-22 vicinity).
- `services/chess_coach/gateway/app.py` — add `app.include_router(repertoire_book_router)` near the existing `app.include_router(repertoire_recommendations_router)` (line 359).
- `services/chess_coach/gateway/config.py` — add a `books_dir` property at the same level as `backups_dir` (line 83-84).
- `tests/integration/test_repertoire_book.py` (NEW) — 8-10 tests covering: PUT then GET then DELETE, PUT overwrites, GET on no-book returns 404, DELETE on no-book is idempotent, write-scope token required (401 on read-only), player-name normalization (the α route does `"ebassti" if player == "default" else player` — same convention), the writer's `ValueError` on illegal move becomes a 400, the writer's `ValueError` on weight out of range becomes a 400, large books (10k entries) round-trip correctly.

**Acceptance:**
- The three endpoints are wired in both layers (routes `__init__.py` AND `app.py` per the chess-coach route-pattern skill).
- The writer is staged as the first sub-piece (no re-implementation, no duplication, per the FYI on FU-7).
- The α route continues to work unchanged. No regression in the 8 existing α integration tests.
- All new tests pass; ruff clean; gateway-boot CI green.

**Risk:** Medium. The two-layer route-registration pattern is a known footgun (per the chess-coach-bbf-sprint skill). The player-name normalization must match the α route's convention. The PUT body schema is new (Pydantic model for the entry list).

**Tool budget:** ~50 tool calls. The brief-vs-code divergence check (BBF-FU-11b vs. the live `repertoire_recommendations.py` and `app.py`) takes ~3-5; the route implementation ~25; tests ~15; the leaf-review-cycle with the integration test ~10.

### 3.3 BBF-FU-11c — α route opt-in to stored book (the smallest behavior change)

**Scope:** Add a single line to `_analyze_row()` in `repertoire_recommendations.py:260`: if `polyglot_book_path` is None and the player has a stored book, use the stored book's path. The stored-book lookup is a one-line helper that returns `data_dir/books/<player>.bin` if it exists, else None.

**Files:**
- `services/chess_coach/gateway/routes/repertoire_recommendations.py` — add a `_resolve_book_path(player, supplied_path)` helper, called at line 333 (the `if not polyglot_book_path:` branch).
- `tests/integration/test_repertoire_recommendations_polyglot.py` — add 2 tests: (a) `polyglot_book_path` not supplied + stored book exists → engine+book blending runs, source="book" appears; (b) `polyglot_book_path` not supplied + no stored book → engine-only path (existing behavior).

**Acceptance:**
- The α route's signature is unchanged.
- The 8 existing α integration tests pass unchanged.
- The 2 new tests pass.
- CI green.

**Risk:** Low. The change is opt-in. A caller who supplies `polyglot_book_path` continues to use that path. A caller who does not supply a path gets the stored book if one exists, or the engine-only path if not. No caller is broken.

**Tool budget:** ~15 tool calls. The smallest BBF in the sequence; reviewable in 5 minutes.

### 3.4 The recommended sequencing

| Tier | BBF | Scope | Risk | Tool budget |
|---|---|---|---|---|
| 1 | **BBF-FU-11a** | Auth scope extension | Low | ~25 |
| 2 | **BBF-FU-11b** | β route + writer integration | Medium | ~50 |
| 3 | **BBF-FU-11c** | α route opt-in to stored book | Low | ~15 |

Each ships in its own branch → PR → leaf review → CI green → `go <id>` cycle, per the v0.7.13.1 stop-gate discipline. **The user names `go` between every BBF in the sequence**, not before the first one.

### 3.5 What this brief is NOT

This brief is not a recommendation-to-self. It is a commit on `main` (after squash-merge) that downstream BBFs reference. The squash-merge of this decision BBF is the trigger that enables BBF-FU-11a, BBF-FU-11b, BBF-FU-11c to start with the right scope. Until this brief is on `main`, the implementation BBFs are not in their right state.

---

## 4. Honest disclosures

### 4.1 What this brief is

A decision-only BBF that answers the three undecided questions the ledger explicitly names for FU-11 (ownership, surface, auth) and proposes three implementation BBFs in sequence.

### 4.2 What this brief is NOT

- **Not a code change.** The diff is `*.md` only. The `services/chess_coach/repertoire/polyglot_writer.py` writer (SHA `91009f08…`) is not staged, not committed, not modified. It remains untracked until BBF-FU-11b opens, at which point it is staged as the first sub-piece of that BBF (per the FYI on FU-7).
- **Not a recommendation-to-self.** The recommended shape (α-ext) is the one the writer and the α route are most naturally compatible with. The alternatives (α+lib, β-min) are documented in §2.4 and §2.5 with reasons they are not recommended.
- **Not a final product spec.** A "set my default for this player" UX is one of many possible shapes. The user's preferences are the next decision; this brief proposes the simplest shape that satisfies the FU-11 boundary statement and the v0.7.103 strategic-decision-bbf-pattern's "smallest surface that satisfies the boundary" principle.
- **Not a multi-BBF squashed into one.** The three implementation BBFs in §3 are three separate squash-merge-per-BBF commits with three separate leaf-review cycles. The brief is the decision; the implementation is three BBFs.

### 4.3 Stale numbers and assumptions in the prior handoffs

- **The 2026-10-11 handoff's "76 local-env test failures" baseline dropped to 74 after the FU-7 fix.** Confirmed live this session: `pytest tests/unit` returns `74 failed, 408 passed, 3 skipped`. No regression from the writer work; the 2-test delta is the count of α tests that were previously failing because of the magic-header bug, now passing because of the no-header fix.
- **The handoff's path claim** that P2c.1 modified `services/chess_coach/ingest/pdf_ingest.py` does not match the live `git status --short` output, which shows `M services/chess_coach/gateway/routes/pdf_ingest.py`. Either the handoff has a path typo or there is a parallel `pdf_ingest.py` in two locations. The handoff's SHA `4c91d495…` is from a different point in the file's history than the live working copy. Pre-existing documentation drift, out of scope for FU-11. Documented here for the next session's audit trail.
- **The writer SHA recorded in the FYI on FU-7** (`91009f08…`) was re-verified live this session. Same SHA, same 6/6 tests, same ruff-clean. The FYI's "re-hash before treating as authoritative" caveat is now permanently satisfied.

### 4.4 Risks not addressed by this brief

- **The combine algorithm for multi-book is not designed** (it does not need to be — α-ext has one book per player).
- **The backup/lifecycle story for `data_dir/books/` is not designed** (the data-dir convention handles it at the OS level; no per-book rotation). If a future BBF needs per-book retention policies, that is its own decision.
- **The PyInstaller binary does not include `data_dir/books/` in the bundle.** The Phase 8 brief (BBF-PHASE-8-1) documents the binary scope as gateway + sqlite only. A future BBF that bundles the books directory is its own scope.
- **The CLI (`apps/cli/chess_coach/`) does not have a "manage my books" command.** Out of scope for v1.0; the v1.0 CLI scope is documented elsewhere.

### 4.5 The §0 thread-discipline items this brief inherits

From the FU-7 → FU-11 transition (per the FYI on FU-7 and the handoff's §0 section):

- (α) Auditor self-report vs ground truth — the prior "2 passed, 4 failed" claim was wrong; pytest couldn't import the test file because the active environment had no `chess` module. Resolved by switching to the project venv.
- (β) Auditor library-behavior assumption — the prior "library treats magic as part of first entry, sorted, fine" claim was wrong at the find level. Resolved by dropping the magic header.
- (γ) Auditor scope-conflation — the prior "FU-7 ~90% done" framing conflated α (resolved) with β (deferred). Resolved by this brief, which puts β on a real sequencing path.

Future audit-closure claims on FU-11 must verify the writer's SHA against the live file, the FYI's options against the actual ledger entry, and the three design dimensions against this brief.

---

## 5. Cross-references

### 5.1 In-repo

- **FU-7 (α)**: `docs/16_audit/OPEN-FOLLOWUPS.md` line 343 (entry), line 416-438 (FYI on FU-7, this session, FU-11 alpha-precursor decision), line 7183 (per-session handoff pointer). Resolved 2026-08-08 via PR #84, commit `7180433`.
- **FU-11 (β)**: `docs/16_audit/OPEN-FOLLOWUPS.md` line 776 (entry). OPEN, deferred to Phase 2 trigger. This brief is the decision.
- **Writer**: `services/chess_coach/repertoire/polyglot_writer.py` (SHA `91009f08…`, untracked). FU-11 alpha-precursor. 6/6 unit tests passing, byte-round-trip verified.
- **Writer tests**: `tests/unit/test_polyglot_writer.py` (SHA `e0ad619e…`, untracked). 6/6 tests, ruff clean.
- **α route**: `services/chess_coach/gateway/routes/repertoire_recommendations.py:203-398` (the PUT-equivalent query field is at line 216-224; the `_book_moves_for_fen` helper is at line 150-200).
- **α integration tests**: `tests/integration/test_repertoire_recommendations_polyglot.py` (8 tests, hand-rolled Polyglot `.bin` via `struct.pack` in `tmp_path`).
- **Auth**: `services/chess_coach/gateway/auth.py:46-49` (the `require_bearer` dep that BBF-FU-11a extends).
- **Settings**: `services/chess_coach/gateway/config.py:62-93` (the `data_dir` field that BBF-FU-11b extends with `books_dir`).
- **Routes registration**: `services/chess_coach/gateway/routes/__init__.py:21-22` (where BBF-FU-11b adds the new router import).
- **App registration**: `services/chess_coach/gateway/app.py:356, 359` (where BBF-FU-11b adds the new `app.include_router` call).
- **Phase 8 brief**: `docs/16_audit/BBF-PHASE-8-1.md` (precedent for tracking `docs/16_audit/BBF-*.md` briefs; PyInstaller binary scope; data-dir convention).
- **86.4 precedent**: `docs/16_audit/BBF-86.4-ruff-strategy-decision.md` (precedent for a decision-only BBF; same five-section structure; same squash-merge-per-BBF discipline).

### 5.2 In-skill

- `chess-coach-bbf-sprint` skill v0.7.121 (the meta-skill): per-BBF ship cycle, multi-BBF dependency-graph verification, squash-merge-per-BBF rhythm.
- `references/chess-coach-route-and-test-patterns.md` (the two-layer route-registration pattern: `routes/__init__.py` AND `app.py`).
- `references/decision-only-bbf-leaf-review.md` v0.7.102 (the leaf-review rubric for this brief).
- `references/strategic-decision-bbf-pattern.md` v0.7.103 (the precedent for shipping the decision BBF before the implementation BBFs it governs).
- `references/post-clarify-stop-gate.md` (the stop-gate between BBF-FU-11a, BBF-FU-11b, BBF-FU-11c — each requires an explicit `go <id>`).
- `references/leaf-review-claim-verification.md` v0.7.99 (the claim-verification rubric for the leaf reviewer of this brief).
- `references/brief-vs-code-divergence.md` v0.7.107 (the pre-implementation check that BBF-FU-11a, -11b, -11c must each run before opening their branches).

### 5.3 In-memory

- The standing convention: null `clarify` responses are treated as the named-directive-in-conversation (Sebastian hasn't picked an option).
- The standing convention: identity-sensitive state mutations (who-gets-attribution, committer names, contact emails) NEVER bundle into a general "go" — surface as a separate question.
- The standing convention: Option A = just-write, no commit. The writer was preserved as untracked working-tree state per this convention, and this brief is the first state-mutating action in the FU-11 sequence.

---

## 6. Pre-leaf-review checklist (for the next session's reviewer)

The reviewer must verify, per the v0.7.102 decision-only rubric:

1. **Numstat:** `git diff --numstat main..HEAD --shortstat` returns `1 file changed, ~250 insertions(+), 0 deletions(-)`. Match against this brief's stated scope.
2. **Sequencing consistency:** the Tier 1/2/3 table in §3.4 matches the §13.3 sequencing principles (smallest-first, lowest-risk-first, dependency-order). The auth extension is Tier 1 because BBF-FU-11b's `Depends(require_bearer_with_scope(...))` call would fail at import time if the auth dep doesn't exist. The α route opt-in is Tier 3 because it depends on the route being in place.
3. **Cross-references resolve:** every file:line cited in §5.1 must be `VERIFIED` by `read_file` against the live tree. Every SHA cited (`91009f08…`, `e0ad619e…`, `7180433`, `4c91d495…`) must be `VERIFIED` by `sha256sum` against the live file (or, for git SHAs, by `git log` against the cited branch).
4. **Option tradeoffs:** the three named options in §2.2 have non-empty cells in all columns. The α-ext recommendation is anchored in the §0.1 reasoning and the §2.3-2.5 alternatives.
5. **Out-of-scope explicit:** §2.6 names the features that α-ext does NOT include. None of them appears in the §3 BBF scopes.
6. **Convention self-application:** the brief self-applies the `docs/16_audit/BBF-*.md` tracked-brief convention (verified by `git ls-files docs/16_audit/BBF-*.md | grep FU-11`, expected: this file). The FYI on FU-7 line 420 is referenced as the parent handoff; verified by `grep -n "FYI 2026-10-12" docs/16_audit/OPEN-FOLLOWUPS.md`.
7. **No state-mutating claims:** the brief's diff is `*.md` only. No code file is staged. Verified by `git status --short` returning only `M docs/16_audit/OPEN-FOLLOWUPS.md` (prior turn) and `M docs/16_audit/BBF-FU-11-polyglot-persistent-book-decision.md` (this brief, if committed) plus the pre-existing `M` / `??` from the writer artifact and prior turns.

If any row returns `CONTRADICTED` or `INSUFFICIENT-EVIDENCE`, the brief is BLOCKERS. Per the v0.7.99 claim-verification discipline, the reviewer's verdict must cite file:line for each finding.
