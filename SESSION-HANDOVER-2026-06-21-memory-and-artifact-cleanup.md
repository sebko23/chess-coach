# SESSION HANDOVER — Memory & Artifact Cleanup (2026-06-21)

## Summary

Two auto-write failure modes polluted agent state and the project root:
`memory_save` saved false user-identity claims to the FAISS vector store,
and `document_response_affordance` wrote `.md`/`.docx` artifacts for every
assistant response. This session diagnosed, disabled, and cleaned both.

| Metric | Before | After |
|---|---:|---:|
| Memory PKL documents | 1371 | 1361 |
| `Agent Zero` documents (in `page_content`) | 21 | 11 |
| Stray artifacts in project root | 6+ | 0 |
| Active auto-write extensions | 2 | 0 |

Final state committed in `039c707`. Full rollback chain preserved on disk.

## Failure modes discovered

### 1. `memory_save` — false user-identity claims

The `_memory` plugin tool was auto-discovered from
`/a0/plugins/_memory/tools/` and invoked on every tool call. Each save
wrote to the FAISS vector store including fabricated claims: "John Doe",
"Agent Zero", dog "Max". No user-identity verification — it trusted
incoming text.

### 2. `document_response_affordance` — auto-artifact on every response

The `_office` plugin extension `_20_document_response_affordance.py`
hooked into `tool_execute_after` and fired after every `response` tool
call. On a positive decision from `decide_response_artifact(...)`, it
called `document_store.create_document(...)` to write a `.md`/`.docx`
file. Artifact names were derived from the response's first header.

## Verification protocol gap

The old baseline for memory audits used `grep` to count identity strings
("John", "Doe", "Max", "Agent Zero") against the flat dump of
`index.pkl`. This measured the wrong thing — it counted mentions, not
entries, and assumed the document store was a flat list of strings.

`index.pkl` is actually a 2-tuple `(docstore, faiss_map)` where
`docstore` is a `dict[str, LangChain Document]` with Pydantic-v2 nested
`__dict__`. To read `page_content` reliably, the auditor must:

1. **Load with a permissive stub unpickler** — default `pickle.load`
   fails on LangChain's Pydantic-v2 class signatures:

   ```python
   # Minimal illustration — see full _Stub/_PermissiveUnpickler in session scripts
   class _Stub:
       def __init__(self, *a, **kw): pass
   class _PermissiveUnpickler(pickle.Unpickler):
       def find_class(self, mod, name): return _Stub
   with open('index.pkl', 'rb') as f:
       docs, id_map = _PermissiveUnpickler(f).load()
   ```

2. **Walk with Pydantic-nested access** — `str(entry)`, `repr(entry)`,
   and top-level `vars(entry)` all return zero matches because
   Pydantic-v2 hides fields under `__dict__['__dict__']`:

   ```python
   pc = v.__dict__.get('__dict__', v.__dict__).get('page_content', '')
   ```

Future audits must use this access pattern. The grep-based baseline
was producing false-negative results (claiming "clean" when entries
were polluted) and was the reason this cleanup pass was needed at
all.

## Disable patterns

Both failure modes were stopped by the same surgical operation:
**rename the offending file `.py` → `.py.disabled`**.

Framework auto-discovery scans for `_NN_*.py` (extensions) and `*.py`
(tools) in the relevant plugin directories. Non-`.py` files are
skipped. The original code is preserved on disk and reversible with
`mv ... .py`.

| Disabled file | Path |
|---|---|
| `memory_save.py` | `/a0/plugins/_memory/tools/memory_save.py` |
| `_20_document_response_affordance.py` | `/a0/plugins/_office/extensions/python/tool_execute_after/` |

The explicit tool calls (`memory_save`, `document_artifact`) and all
other plugin features remain functional. Only the auto-trigger is
disabled.

### Alternatives considered and rejected

| Alternative | Verdict |
|---|---|
| Source-code early-return | Rejected — merge conflicts on plugin update |
| File deletion | Rejected — loses rollback option, obscures intent |
| Plugin-level disable in `plugin.yaml` | Rejected — too broad; the plugins themselves are valid |
| Runtime gate (`if DISABLED: return`) | Rejected — adds code we'd have to remember to remove |

The rename is reversible, scoped to the offender, and update-safe
within the constraints we control (this container image doesn't
auto-update).

## What was changed

### PKL cleanup (.a0proj/memory/index.pkl: 1371 → 1361 docs, -10)

**8 deletes** (false-claim / junk entries polluting recall):

| ID | Reason |
|---|---|
| `1WPhCTRX92` | Stub entry: `# Solution Agent Zero` literal |
| `4ixskfy6B0` | Rejected draft fragment |
| `AaSSjRZ8Cd` | False claim: terminal relay broken |
| `FyMvBBFmwi` | False claim: project state assessment |
| `HSSqURHkiv` | MAIA fix description (out-of-session claim) |
| `LmnxL9jEld` | Structured-note stub with identity claim |
| `SiEuM0Abk5` | False claim: terminal output relay broken |
| `TrKpgEdPAA` | Junk auto-modified-files note |

**2 migrations** to `docs/`, then deleted from PKL:

| ID | Destination |
|---|---|
| `tHiWSZgNu2` | `docs/13_review_response/session-2026-06-17-repo-hygiene.md` |
| `RKnTFTDRi0` | `docs/13_review_response/session-2026-06-18-false-claims-investigation.md` |

**1 trim** (`zL7Cp47eGu`): stale steps 4+5 removed, audit-trail
reference added as step 4. Metadata preserved exactly (id, area,
timestamp, consolidation_similarity unchanged).

### Disable mechanism applied

```
/a0/plugins/_memory/tools/memory_save.py.disabled
/a0/plugins/_office/extensions/python/tool_execute_after/_20_document_response_affordance.py.disabled
```

### `.gitignore` update

```
.a0proj/memory/*.bak
```

Scoped to rollback artifacts only; does not suppress intentional
`.bak` files elsewhere in the repo.

## Verification

### In-session disable test

A `response` tool call with a markdown-heavy payload (tables, numbered
lists, code blocks, decision matrix — the exact content shape that
previously triggered artifact creation) was issued after the rename.
`ls /a0/usr/projects/chess_coach/*.md` count remained at **15**.
Confirms framework re-imports the extension directory on each hook
fire, so the in-session rename takes effect without a restart.

### Baseline count check

New baseline: **11 "Agent Zero" documents** in `page_content`.
Breakdown:

- 6 framework KB entries (positions 1–9 in the original 1371-doc
  enumeration)
- 4 KEEP entries approved during triage (`nao5vmGLIl`, `CumzY0tGqM`,
  `kXRaOgxMFi`, `8M5dBEXJC8`)
- 1 trimmed entry (`zL7Cp47eGu`) — still contains "Agent Zero"
  in the Problem text

The Pydantic-nested access pattern (from § 3) was used to verify
the count — `str(entry)` returns zero matches for `Agent Zero`
because Pydantic-v2 hides fields under `__dict__['__dict__']`.

## Rollback procedure

If anything in this cleanup needs to be reverted, restore from the
preserved backup chain in `.a0proj/memory/`:

| Backup file | Bytes | State |
|---|---:|---|
| `index.pkl.20260621-210143.bak` | 722,447 | Pre-everything (1371 docs) |
| `index.pkl.20260621-212807.bak` | 709,884 | Post-Step-2 (1363 docs) |
| `index.pkl.20260621-214841.bak` | 709,884 | Post-Step-C (1361 docs) |

**To restore the pre-cleanup state**:

```bash
cp .a0proj/memory/index.pkl.20260621-210143.bak .a0proj/memory/index.pkl
touch .a0proj/memory/index.faiss.sha256   # force FAISS rebuild on first use
```

The `.disabled` plugin files are reversible with:

```bash
mv /a0/plugins/_memory/tools/memory_save.py.disabled \
   /a0/plugins/_memory/tools/memory_save.py
mv /a0/plugins/_office/extensions/python/tool_execute_after/_20_document_response_affordance.py.disabled \
   /a0/plugins/_office/extensions/python/tool_execute_after/_20_document_response_affordance.py
```

`.bak` files should be retained until commit `039c707` is verified
stable in production. Once verified, they can be deleted to reclaim
~2 MB.

## Long-term notes

### Plugin update risk

This container image does not auto-update, so the renamed
`.disabled` files are stable for now. If the `_memory` or `_office`
plugins are ever upgraded (e.g., via a base image rebuild), the
`.disabled` files would be removed or replaced and the auto-trigger
would be re-enabled.

If that risk materializes, the permanent fix is a user-space
override at `/a0/usr/extensions/python/<hook_point>/_NN_name.py`
(a no-op extension that takes priority in the merge order). Per
the `a0-development` skill, user-space extensions survive plugin
updates.

### Knowledge-base migration

Two substantive entries (`tHiWSZgNu2`, `RKnTFTDRi0`) were migrated
to `docs/13_review_response/` as part of this cleanup. Future sessions
should evaluate whether the remaining memory entries (especially the
4 KEEP entries — `nao5vmGLIl`, `CumzY0tGqM`, `kXRaOgxMFi`,
`8M5dBEXJC8`) would be better served as curated docs in `docs/`.

The recall surface benefits from a curated, named-file structure
over a flat FAISS index — agents can `cat` a specific doc without
relying on vector similarity to surface it.

## Commit reference

```
039c707 chore+docs(memory-hygiene): disable memory_save + document_response_affordance, clean PKL (1371→1361), 2 migrations + 1 trim, .gitignore for .bak
```

Full commit body (including per-file rationale, backup chain
metadata, and verification protocol) is preserved in the git
log — `git show 039c707` reproduces it. This handover doc and
the commit body together form the complete record of the
2026-06-21 cleanup pass.
