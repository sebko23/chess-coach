# BBF-FU-11c — α route opt-in to stored per-player book (Tier 3 of FU-11)

| | |
|---|---|
| **BBF id** | BBF-FU-11c |
| **Tier** | 3 of 3 (α opt-in) |
| **Parent decision brief** | `docs/16_audit/BBF-FU-11-polyglot-persistent-book-decision.md` (PR #124 → squash `c7219669`, the master FU-11 sequencing doc). |
| **Predecessors on main** | BBF-FU-11a (PR #125, `b1b7e931`): scope-based auth. BBF-FU-11b (PR #126, `0d45eedc`): book routes (PUT/GET/DELETE) + writer staging + auth hotfix. |
| **Estimated scope** | 1 changed file (the α route) + 1 new integration-test file. ~30-60 net lines. |
| **Risk profile** | Low — additive behavior, caller-supplied `polyglot_book_path` continues to take precedence, behavior on the no-bookcase is byte-identical to BBF-FU-11b's main. |

## 1. Scope

Today, the α (repertoire recommendations) route at
`services/chess_coach/gateway/routes/repertoire_recommendations.py:239`
takes `polyglot_book_path: str | None = Query(...)`. When the caller
doesn't supply it (line 381), the route returns engine-only items —
no book augment. When the caller supplies it (line 387), the route
augments with book entries from that path.

Per BBF-FU-11b (commit `0d45eedc`), the gateway now stores Polyglot
books at `<data_dir>/books/<player>.bin` via three new routes:
`PUT/GET/DELETE /v1/repertoire/{player}/book`. The store is reachable
via `_books_dir(request)` + `_book_path(books, resolved_player)` at
`services/chess_coach/gateway/routes/repertoire_book.py:214-230`.

**This BBF wires the α route to the store.** Concretely, when the
caller doesn't supply `polyglot_book_path`, the α route looks up the
player's stored book on disk and uses that path. If no book is stored,
the route stays on the engine-only baseline. The caller's explicit
`polyglot_book_path` continues to take precedence (back-compat for
FU-7 callers).

## 2. Behavior matrix

| Caller supplies `polyglot_book_path`? | Stored book exists for player? | Route uses |
|---|---|---|
| Yes | (doesn't matter) | caller's path (FU-7 behavior, unchanged) |
| No | Yes | stored book's path |
| No | No | engine-only (BBF-87.2 / BBF-FU-11b no-book behavior, unchanged) |

## 3. Implementation recipe

### 3.1 Resolve the stored book path inside the α route

In `repertoire_recommendations.py`, after `resolved = DEFAULT_PLAYER
if player == "default" else player` (line 290), and **before** the
`if not polyglot_book_path:` branch (line 381), add:

```python
# BBF-FU-11c: when the caller didn't supply polyglot_book_path,
# look up the stored book for the resolved player. If a stored
# book exists at <books_dir>/<player>.bin, use that path. The
# caller's explicit polyglot_book_path (above) still takes
# precedence; we only substitute when it's None.
if polyglot_book_path is None:
    # Note: request.app.state.gateway.settings (NOT
    # gateway_settings) — verified against
    # repertoire_book.py:_books_dir which is the canonical caller.
    settings = request.app.state.gateway.settings  # see §3.2
    books_dir = settings.books_dir
    stored_path = books_dir / f"{resolved}.bin"
    if stored_path.is_file():
        polyglot_book_path = str(stored_path)
        logger.info(
            "recommendations: using stored book for player=%s path=%s",
            resolved, stored_path,
        )
    else:
        logger.debug(
            "recommendations: no stored book for player=%s; engine-only",
            resolved,
        )
```

The `is_file()` check (NOT `isdir()`) is the same defensive pattern
as the existing `os.path.isdir()` pre-check at line 210. The
`polyglot_book_path` variable is then passed to
`_book_moves_for_fen` at line 387 unchanged.

### 3.2 Expose `GatewaySettings` on `request.app.state`

The α route currently doesn't take `request: Request` (it takes
`pool: EnginePool = Depends(_pool)` and `db_path: str = Depends(_db_path)`
instead). To get to `books_dir`, we need either:

**Option A (recommended):** Add `request: Request` to the route signature
and read `request.app.state.gateway_settings.books_dir`. The other
routes (`repertoire_book.py:214` uses the same pattern via `_books_dir`)
already do this. Confirm that `gateway.app.state.gateway_settings` is
populated at startup (it is — `_books_dir` resolves the same way).

**Option B (fallback if A is intrusive):** Add a `Depends(_books_dir)`
that mirrors `repertoire_book.py:214-224`. Two dependencies → one new
`_books_dir` dep imported from the book route, no `Request` parameter
on the α route. Slight duplication but stays within the existing
dependency-injection idiom.

I'll go with **Option A** in the implementation unless leaf review
pushes back. The `Request` parameter is non-intrusive (FastAPI
auto-injects it; no body-model generation).

### 3.3 Pre-check `isdir()` stays

The `_book_moves_for_fen` function (line 168-208) already does the
`os.path.isdir(book_path)` pre-check that the FU-32 fix added
(per the FU-32 `polyglot_book_path` `os.path.isdir()` pre-check
PR #112 commit). The stored-book path we substitute in §3.1
will be checked by the same pre-check — no new defense needed.

### 3.4 Log line shape

The existing log lines in the route are `logger.warning(...)` on
failures and ad-hoc `logger.info(...)` in the book route. Match the
book route's shape: `logger.info("recommendations: ... path=%s", ...)`
on the resolve, `logger.debug(...)` on the no-stored-book case.

## 4. Tests

New integration test file
`tests/integration/test_repertoire_recommendations_stored_book.py`:

1. **`test_alpha_uses_stored_book_when_caller_omits_path`** — write a
   book for player "ebassti" via the PUT route, call the α route
   without `polyglot_book_path`, assert that the response includes
   `source="book"` (or `"both"`) items for at least one FEN. Mirror
   the `_make_app_with_*` helper from
   `tests/integration/test_repertoire_book.py`.
2. **`test_alpha_falls_back_to_engine_only_when_no_stored_book`** —
   call the α route without `polyglot_book_path` for a player with no
   stored book, assert response is engine-only (`source="engine"`
   items, no `book_weight`).
4. **`test_alpha_caller_supplied_path_overrides_stored_book`** —
   write a stored book for player "ebas_stored", call the α route
   with `polyglot_book_path` pointing at a *different* `.bin`
   file in `tmp_path`, assert the response matches the different
   file (the caller's path wins). This is the back-compat
   regression test.
5. **`test_alpha_default_player_resolves_to_ebassti_for_stored_book`**
   — write a book at `<data_dir>/books/ebassti.bin`, call the α
   route with `player="default"` and no `polyglot_book_path`, assert
   the stored book is used. Verifies the §3.1 `DEFAULT_PLAYER`
   resolution.
7. **`test_alpha_stored_book_absent_is_silent_no_warning_logged`** —
   assert no WARNING-level log line is emitted when no book is
   stored (the §3.4 path emits DEBUG only). Use
   `caplog.set_level(logging.DEBUG)`.

(The old FU-7 polyglot regression suite in
`tests/integration/test_repertoire_recommendations_polyglot.py` —
the 8 tests verified in BBF-FU-11b's body — continues to pass.
No edits to that file.)

## 5. Risks and disclosures

- **Back-compat:** The caller's `polyglot_book_path` continues to
  take precedence (Section 2, row 1). Any existing FU-7 caller is
  unaffected.
- **Behavior change on the no-stored-book path:** None. The
  `polyglot_book_path is None` branch with no stored book still
  returns engine-only items (Section 2, row 3). Byte-identical
  to BBF-FU-11b's main behavior.
- **Auth scope:** No new scope required. The α route already uses
  `require_bearer` (read-only) — looking up a stored book on disk
  inside the route handler is a read, not a write. (The PUT route
  is the only `BOOKS_WRITE`-gated surface and stays that way.)
- **Concurrency:** A book being written mid-read is racy in the
  same way as FU-7 already is (caller-supplied path could point at
  a half-written file). Polyglot `.bin` is sorted; a partial read
  returns entries from the bisect-key range that landed. The FU-32
  `os.path.isdir()` pre-check doesn't fix this and we don't claim
  to either. Future FU-11+ work.
- **Player resolution parity:** The α route uses inline
  `DEFAULT_PLAYER if player == "default" else player` (line 251);
  the book route uses `_resolve_player()` (line 190-208) which
  mirrors the same logic but **also** validates path-safety
  (rejects `.` and `/` in `player`). §3.1 inherits the α route's
  inline resolution — the inline form is already validated by the
  α route's other code paths; adding `_resolve_player()` here is
  a tidy-up I'll mention in the PR body but is NOT required for
  this BBF (the existing α route's other paths don't go through
  `_resolve_player()` either).

## 6. Honesty disclosures

- This brief was written in the BBF-FU-11c-recover session
  (2026-10-13). The prior session had a brief that was lost
  on `git reset --hard origin/main` per the MEMORY note
  "Squash-merge step 11 footgun (v0.7.125 candidate)." This is
  the recovered version; the structure follows the
  BBF-FU-11b commit body's "Tier 3" description verbatim.
- §3.2 (Request injection vs Depends) is a small architectural
  call I'm pre-justifying for the leaf reviewer.
- §5's "path-safety parity" disclosure is the kind of
  "already-a-design-choice" call I don't expect to change in
  review; if it does, this BBF moves from ~30-60 net lines
  to ~50-80 net lines.

## 7. Verification gate (per §1.3 cross-ref check)

The leaf review will mechanically verify, via `grep -n` +
`sha256sum`:

- [ ] `repertoire_recommendations.py:239` — the Query param
      exists as written.
- [ ] `repertoire_recommendations.py:270` — DEFAULT_PLAYER
      resolution exists.
- [ ] `repertoire_recommendations.py:381` — `if not
      polyglot_book_path:` exists at the cited line.
- [ ] `repertoire_recommendations.py:387` — `_book_moves_for_fen`
      call exists.
- [ ] `repertoire_book.py:214-230` — `_books_dir()` and
      `_book_path()` definitions match.
- [ ] `repertoire_book.py:190-208` — `_resolve_player()` exists.
- [ ] `GatewaySettings.books_dir` is populated (verify via
      `pytest tests/integration/test_repertoire_book.py` passing).
      Property at `services/chess_coach/gateway/config.py:87`,
      sibling to `backups_dir` at `config.py:83`.
- [ ] `repertoire_book.py:_books_dir` reads
      `request.app.state.gateway.settings` (NOT
      `request.app.state.gateway_settings`). The §3.2 example must
      use the same attribute path.
- [ ] Note: `services/chess_coach/gateway/routes/repertoire_book.py:_resolve_player`
      docstring cites `services/chess_coach/gateway/routes/repertoire_recommendations.py:270`
      for the α-side `DEFAULT_PLAYER` resolution — matches the live
      tree after BBF-FU-11.0's doc-drift patch + this patch's
      docstring fix at `services/chess_coach/gateway/routes/repertoire_book.py:194`.
- [ ] BBF-FU-11b's 64/64 test count (11+6+9+30+8) still passes.

## 9. Cross-refs

- BBF-FU-11 decision brief: `docs/16_audit/BBF-FU-11-polyglot-persistent-book-decision.md` (PR #124 → squash `c7219669`).
- BBF-FU-11a scope-based auth: PR #125, commit `b1b7e931`.
- BBF-FU-11b book routes + writer integration + auth hotfix: PR #126, commit `0d45eedc` (current main HEAD).
- FU-7 polyglot_book_path additive: PR #84 (the α feature on additive).
- FU-32 `os.path.isdir()` pre-check: PR #112 (the safety fix this BBF inherits).
- Polyglot format pitfalls: `references/polyglot-format-pitfalls.md` (the writer's `find_all` round-trip discipline).

## 10. Contact

Brief authored by Hermes. Implementation will land as PR
`bbf-fu-11c` (queued for `go BBF-FU-11c` after leaf review).