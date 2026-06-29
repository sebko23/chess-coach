# Session Handover — 2026-06-28

## HEAD
`0b2908b` on `master`

## Tests
55/55 passing (no new tests this session — infrastructure work only)

## Phase 3 — COMPLETE
All KB/Qdrant work is done and verified end-to-end:
- Qdrant 1.18.2 binary at `/usr/local/bin/qdrant`
- Config-based storage at `data/qdrant/storage/`, telemetry disabled
- 5,000 positions indexed, `kb/similar` returning correct semantic results
- Four source fixes committed (`c1cb79a` through `0b2908b`)

## Known follow-ups (next session, in priority order)
1. `_ensure_collection` idempotency (`kb/store.py`): always wipes Qdrant collection on
   gateway start → 7-8 min re-embedding every time. Fix: skip delete/recreate if
   `points_count > 0` and `dim` matches.
2. `start_gateway.sh`: `pip install --force-reinstall` runs before idempotency check —
   wasteful on no-op restarts.
3. Phase 2 gaps: multi-engine comparison view, cloud-eval cache, Leela adapter.
4. Phase 4: tilt index (6th metric), methodology docs.
5. Phase 5: Option B reconstruction (needs investigation).
6. Phase 6: OCR library investigation before committing to YOLOv8.
7. Phase 7: Chess.com sync + research agent.
8. Phase 8: Packaging.

## Runtime state at session end
- Qdrant: PID 1165, port 6333, 5000 points persisted
- Gateway: PID 1891, port 18080, kb_ready=true

## Standing rules (unchanged)
- No commit without explicit authorization after seeing clean output
- No environment modification without authorization
- All `.py` edits use explicit-anchor str.replace with pre/post assertions
- Never `git add -A` — explicit file paths only
- Gateway starts via `/a0/start_gateway.sh`
- Agent Zero fabrication is a known recurring risk

## ⚠️ Unauthorized AZ memory import — detected at session close

At 23:35 UTC, Agent Zero auto-imported 10 framework knowledge docs into the project
FAISS index without user authorization. Evidence in `.a0proj/memory/knowledge_import.json`:
- source: "agent0"
- entries_imported: 21 (was 11, now 21; docs: 1361 → 1371)
- note in the file itself: "Triggered by automatic agent initialization, not by user request"

The `.bak` file at `index.pkl.clean-recovery.bak` (20:44 UTC) covers only `index.pkl`,
not `index.faiss` or `embedding.json`. Rollback without all four files risks FAISS desync.
Decision: accept the import (content is benign AZ framework docs), update baseline.

**New expected baseline for next session checklist: docs=1371, AZ docs=21**

Investigation needed next session:
- How did this import trigger with both `memory_save.py.disabled` and
  `document_response_affordance.py.disabled` in place?
- Is there a third plugin or initialization hook that bypasses the `.disabled` guards?
