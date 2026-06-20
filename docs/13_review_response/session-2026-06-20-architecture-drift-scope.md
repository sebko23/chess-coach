# Architecture Doc — Drift Scope Report (Read-First, C)

**Session date**: 2026-06-20 09:03 UTC
**Author**: Agent 0 (profile: agent0)
**Source doc**: `docs/01_architecture/system-architecture.md` (427 lines)
**Doc's last update**: 2026-06-13, commit `9766aee` (`docs: add implementation reality sections...`)
**Doc's previous reality-snapshot**: commit `7c41b02` (2026-06-13)
**Current HEAD**: `4feef86` (2026-06-19, `chore(cleanup): remove stale LibreOffice ODS files and lock files`)
**Scope**: read-first pass. **No edits applied to `system-architecture.md` in this session.** Edits proposed below await user approval.

---

## 1. What was read

| Section | Lines | Topic |
|---|---|---|
| Header + §1 Vision | 1–20 | Project overview |
| §2 Architectural style | 22–37 | Hybrid desktop + microservices |
| §3 Component model | 39–73 | ASCII diagram (Tauri → Gateway → Agents → Bus) |
| §4 Frontend architecture | 75–95 | Tauri 2 + React 19 + Mantine 8 + Vite 8 |
| §5 Backend architecture | 97–135 | 16-service Docker compose inventory |
| §6 Deployment topology | 137–164 | Dev (Docker) + End-user (sidecar) |
| §7 IPC + contracts | 166–194 | REST / WS / Bus, P1–P5 patterns |
| §8 Engine orchestration | 196–220 | UCI pool diagram |
| §9 PDF/OCR/vision pipeline | 222–260 | P5 Saga, YOLOv8 + PaddleOCR |
| §10 OpenRouter / LLM orchestration | 262–284 | LLM Router diagram |
| §11 Persistent memory tier | 286–300 | Episodic / Semantic / Procedural |
| §12 Observability | 302–316 | Logs / Metrics / Tracing / Debug panel |
| §13 Performance posture | 318–340 | Budgets + cache layers |
| §14 Security posture | 342–358 | Loopback-only gateway + §6 compliance |
| §15 License posture | 360–378 | en-croissant GPL fork, Apache backend |
| §16 Risk-aware choices | (in §16) | Architectural decisions vs risk register |
| §17 Out of scope for Phase 1 | (in §17) | Cloud multi-user, voice, mobile, multiplayer |
| §18 Open decisions | 380–391 | **7 items, 2 now resolvable** |
| §19 Cross-references | 393–411 | Doc index table |
| Implementation Reality (post-§19) | 413–427 | **Snapshot dated 2026-06-13** |

---

## 2. Drift since 2026-06-13 (commit `9766aee` → commit `4feef86`)

Source: `git log --oneline 9766aee..4feef86` — 39 commits over 6 days.

### 2.1 Implementation Reality section (§post-19) — HIGH DRIFT, needs refresh

The snapshot table dated 2026-06-13 (lines 419–425) needs every row touched:

| Vision column (existing) | What changed since 2026-06-13 | Status |
|---|---|---|
| Redis Streams message bus | No change. Still deferred; `asyncio.gather()` in monolith. | Keep row; no edit. |
| 14 specialized agents as separate services | `route_guard` decorator applied to 7 previously-unprotected routes (`f24bd8b`, ADR-0002). Module boundary hardening, not extraction. | Update wording: "monolith with `route_guard` cross-cutting (ADR-0002); 7 unprotected routes now guarded." |
| WebSocket streaming | No change. Still REST-only. | Keep row. |
| Backend port `0.0.0.0:18080` | No change. Descriptor-file discovery unchanged. | Keep row. |
| Qdrant vector DB | **Substantive change**: `memory_kb/` module is no longer stubbed. TF-IDF position-similarity pipeline + in-memory Qdrant store landed (`789b0cd`). Standalone Qdrant server still not deployed — TF-IDF fallback wrapped behind a Qdrant-shaped façade. | Update row materially. |

**"What is built and working" paragraph (line 425) needs new bullets**:

| New built-and-working item | Commit | Citation |
|---|---|---|
| Maia-1500 engine integrated via lc0 (`extra_args` UCI support) | `5c05764` | Multi-engine pool expansion |
| `engines.json` pre-populated with Stockfish 18 + Maia-1500 | `b7bc0b0` | `cfd6603` (root-cause doc: appDataDir copy) |
| chessvision.ai integration for PDF diagram extraction (replaces OCR stub) | `6635ffa` | Phase-6 collapse from 12 weeks → 2 hrs |
| route_guard decorator on 7 routes (ADR-0002) | `f24bd8b` | Cross-cutting observability |
| 5 new integration test suites, 56/56 → 57/57 passing | `8e789e6` + later fixes | Total now 57/57 across bisect (`75d3af0`–`4feef86`) |
| `pv_moves` + `score_display` in `/v1/narration/explain` response | `b1c5bf8` | Matches CoachesPage live-data need |
| `grounded` field now accurately reflects LLM vs template | `1c171be` + `bf03eee` | 7 narration bugs resolved |
| `activePlayerAtom` shared across Repertoire + TrainingQueue pages | `9b590f4` | Jotai cross-panel state |
| Practice deck source architecture documented | `781bcb8` | `SESSION-HANDOVER-PRACTICE-DECK-SOURCE.md` |
| Storage migrations: 7 missing migrations for ad-hoc tables restored | `d363f7e` | `SESSION-HANDOVER-STORAGE-MIGRATIONS-MISSING.md` |
| Deep project audit (2026-06-14) | `94b89cd` | `docs/16_audit/project-audit-2026-06-14.md` |
| Memory-disable durability: 4th cross-session boundary check | `75d3af0` | Holding across 2 boundaries verified |


### 2.2 §9 PDF/OCR/vision pipeline — MEDIUM DRIFT

Pipeline still describes YOLOv8 + PaddleOCR but `6635ffa` introduced **chessvision.ai API** as the primary diagram extractor. Current state: API-first with the local YOLOv8 path retained as offline fallback.

Proposed update: add a one-line note — "Production path uses chessvision.ai API since 2026-06-14 (150 diagrams extracted at audit time per `project-audit-2026-06-14.md`); local CNN retained for offline fallback." Keep the PaddleOCR text-extraction step (still relevant for move sequences and annotations).

### 2.3 §18 Open decisions — TWO items now resolvable

| # | Original item (line 380–391) | Resolution evidence | Proposed action |
|---|---|---|---|
| 0 | **BLOCKER** GPL license boundary | `LICENSING.md` (73 lines), `ADR-0004-license-posture.md`, `legal-protocol-assessment-received.md` (counsel verdict 2026-05-18, R1+R2 applied, P1+P2+P3 committed, protocol v1.0.0 stable). | **Remove item 0 entirely**; replace with one line: "**0. (RESOLVED 2026-05-18)** License posture per ADR-0004 — see `LICENSING.md`." |
| 3 | Backend service license (Apache-2.0 vs MIT vs proprietary) | `LICENSING.md` table: `services/`, `libs/`, `apps/cli/` → **Apache-2.0**. | **Remove item 3 entirely**; one-line closure note. |
| 1 | Default sidecar vs Docker for end-user | Still open. PyInstaller sidecar planned per architecture doc. | Keep open. |
| 2 | Embedding model default (bge-small vs OpenAI text-embedding-3-small) | Still open. TF-IDF fallback in use pending decision. | Keep open, **add urgency note** (TF-IDF bandwidth ceiling approaching as position-concept KB grows). |
| 4 | Telemetry posture (opt-in: yes/no/never; default no) | Still open. | Keep open. |
| 5 | OCR primary (PaddleOCR vs Tesseract) | **Effectively moot**: chessvision.ai is now primary (`6635ffa`). PaddleOCR/Tesseract are offline fallback only. | Update wording: "OCR stack **deferred** — chessvision.ai API primary; offline stack unranked." |
| 6 | Repertoire UI density (tree vs grid) | Still open. | Keep open. |
| 7 | Phase-6 FEN-accuracy target | Still open. Audit reported `150 diagrams extracted via chessvision.ai`; accuracy number not in audit. | Keep open, **add urgency note** (Phase 6 needs the target before MB-3). |

Net effect: §18 goes from 7 items to 5 (or 4 if OCR item is collapsed into the §9 wording change). §18 header should change from "Open decisions (carried to gate-0 review)" to "Open decisions (carried to next gate review)" since gate-0 is past.

### 2.4 §15 License posture — DOCSTRING UPDATE NEEDED

The section text references the boundary under GPL-3.0-only §5 but does not cite the counsel opinion or `LICENSING.md`. Since `LICENSING.md` is now the **authoritative** license document per its own header, the §15 paragraph should:

- Add a one-line reference: "Authoritative source: `LICENSING.md` (published 2026-05-18, ADR-0004)."
- Drop the now-stale "to be authored at Phase 1 implementation start" sentence.

### 2.5 §13 Performance posture — NUMBERS MAY NEED REFRESH

The audit (`docs/16_audit/project-audit-2026-06-14.md`) reported zero data-quality issues across 25,948 positions and 551 games. The "SQLite WAL with 88K rows" in the Implementation Reality section should probably be re-checked against current row counts. **Low priority — verify before editing.**

---

## 3. Items NOT in scope for this update

- §1 Vision, §2 Style, §3 Component model, §6 Deployment, §7 IPC — vision-level, no drift.
- §4 Frontend — en-croissant fork structure unchanged; no drift.
- §5 Backend — service inventory table is forward-looking (16 services planned); doesn't claim current state, so no drift.
- §8 Engine pipeline — already describes multi-engine; now actually populated, but section text is still accurate.
- §10 LLM Router, §11 Memory tier, §12 Observability, §14 Security — target architecture, no drift.
- §16 Risk-aware, §17 Out of scope — unchanged.
- §19 Cross-references — still correct (no doc renames).

---

## 4. Proposed edit plan (for next session, awaits approval)

| Step | Edit | Lines affected | Risk |
|---|---|---|---|
| 1 | Update §18 item 0 to RESOLVED closure line | 380–382 (item 0 paragraph) | Low (deletion) |
| 2 | Update §18 item 3 to RESOLVED closure line | 387–388 | Low (deletion) |
| 3 | Renumber §18 items, update §18 header | 380–391 | Low (cosmetic) |
| 4 | Replace Implementation Reality table (lines 419–425) with refreshed 2026-06-20 snapshot | 413–427 | Medium (factual content) |
| 5 | Add 2026-06-20 entries to "What is built and working" (line 425) | 425 | Medium |
| 6 | Update §9 OCR paragraph to add chessvision.ai note | ~240 | Low (one-line addition) |
| 7 | Update §15 to cite `LICENSING.md` as authoritative | ~376 | Low |
| 8 | Re-verify SQLite WAL row count and update "88K rows" in Implementation Reality | 425 | Low (factual refresh) |

**Total**: ~8 line-ranges, ~5 material edits, ~3 cosmetic. Estimated 30–45 min of careful editing, plus 10 min validation.

---

## 5. Recommendation

**Do not apply edits to `system-architecture.md` in this session.** Reasoning:

1. **User instruction was "read-first"** — explicit per session-start-blocked.md §5.2 item C and current chat direction.
2. **Scope is bounded but non-trivial** — 5 material edits touch factual claims that need to be cited correctly per the table in §2.1.
3. **Cross-doc consistency**: §15 license change, §18 closure of items 0+3, and §9 OCR wording should be **edited in the same commit** to keep the doc self-consistent.
4. **Verification prerequisite**: SQLite WAL row count should be checked before step 8 to avoid an edit-then-fix cycle.

**Recommended next action**: when this session continues, ask for approval on the edit plan in §4, then execute steps 1–7 in a single commit with a clear message. SQLite row count (step 8) can run before commit or be deferred to a follow-up.

---

## 6. Side observations (out of C scope but noted)

- The untracked file `Chess Coach _ Progress _ Problems Report _2026-06-20_session-start-blocked.md` (181 lines, root) is the artifact of a prior chat where `code_execution_tool` was timing out at 15 s. That failure mode did **not** recur in this chat — small commands returned output cleanly. The artifact is stale evidence but not actively harmful. **No action recommended**; flag for user awareness.
- The 4 modified `.a0proj/memory/index.*` files and `.a0proj/plugins/_model_config/config.json` are framework-managed (FAISS index refresh + `openrouter → anthropic` utility-model switch), unchanged since prior session per user confirmation. **No commit action.**
- Item B (EnginesPage) and item D (Tauri build sub-item) remain **deferred** because cargo is absent in this container (`which cargo` → NOT FOUND, `rustup` NOT FOUND, `~/.cargo/bin/` empty). The session-start-blocked.md §3.1 named the same 15s-timeout pattern as a possible symptom of the same environment issue, but in this chat small commands succeeded; the timeout hit on a 140-line heredoc write. **Workaround used**: chunked heredoc writes (≤ ~30 lines each) via `>>` append — all completed in 12–16 s. **Recommendation for future sessions**: avoid single-heredoc writes > ~80 lines; chunk into ≤ ~30-line appends.
- **Memory note worth saving**: the 15s wrapper timeout is **payload-size-sensitive**, not binary broken. Small commands work; large heredocs time out.

---

## 7. Artifact pointers

| Artifact | Location |
|---|---|
| This report | `/a0/usr/projects/chess_coach/docs/13_review_response/session-2026-06-20-architecture-drift-scope.md` |
| Source doc (unchanged) | `/a0/usr/projects/chess_coach/docs/01_architecture/system-architecture.md` |
| Authoritative license doc | `/a0/usr/projects/chess_coach/LICENSING.md` |
| License posture ADR | `/a0/usr/projects/chess_coach/docs/14_adrs/ADR-0004-license-posture.md` |
| Counsel verdict | `/a0/usr/projects/chess_coach/docs/13_review_response/legal-protocol-assessment-received.md` |
| Project audit (2026-06-14) | `/a0/usr/projects/chess_coach/docs/16_audit/project-audit-2026-06-14.md` |
| Session-start-blocked artifact (stale) | `/a0/usr/projects/chess_coach/Chess Coach _ Progress _ Problems Report _2026-06-20_session-start-blocked.md` |
