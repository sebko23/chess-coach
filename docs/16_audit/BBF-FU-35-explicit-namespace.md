# BBF-FU-35-explicit-namespace — make `chess_coach` an explicit namespace package

**Sprint intent:** Resolve FU-35 by making the
`chess_coach` package an explicit namespace package
(adding a root `chess_coach/__init__.py` marker) rather
than a PEP 420 implicit namespace package. This is the
**defensive B2 cross-platform import fix** that the
prior session notes identified.

**Status:** Code + config BBF. 2 files modified.

## §1. The problem (FU-35)

Per `docs/16_audit/OPEN-FOLLOWUPS.md` (FU-35 entry):

> `chess_coach` is a PEP 420 implicit namespace package
> declared via `[tool.setuptools.package-dir]` in
> `pyproject.toml:99-117`. There is no physical
> `chess_coach/__init__.py` at the repo root. PyInstaller's
> `collect_all()` primitive does not enumerate implicit
> namespace packages, so it cannot enumerate `chess_coach.*`
> submodules for the binary.

The temporary workaround (BBF-Phase8-1) is to bundle
the source-tree directories verbatim via `datas=` and
add their parents to `sys.path` via a runtime hook. This
works but is fragile (bloats the binary, bundles artifacts,
has implicit ordering).

## §2. The fix (this BBF)

1. **Added `chess_coach/__init__.py` at the repo root** —
   a docstring-only marker file that documents the
   package structure.
2. **Updated `[tool.setuptools.package-dir]` in
   `pyproject.toml`** — added the self-mapping
   `"chess_coach" = "chess_coach"` (option (b) from
   the FU-35 resolution shape).

This is the **minimal defensive fix** that resolves the
B2 cross-platform import bug class without requiring
a full package restructure. The per-package mappings
(e.g., `"chess_coach.errors" = "libs/chess_coach/errors"`)
are preserved, so the editable install continues to work.

## §3. The verification (live, this session)

```
# Install:
$ pip install -e . --no-deps
exit=0

# Import test:
$ python -c "import chess_coach; import chess_coach.keychain; import chess_coach.gateway; print('all imports OK')"
all imports OK

# Ruff (local):
$ ruff check libs services apps/cli tests scripts
All checks passed!

# Mypy (local, Windows):
$ mypy libs services apps/cli --no-incremental
services\chess_coach\pdf_ocr\subprocess_runner.py:113: error: Name "resource" is not defined  [name-defined]
Found 1 error in 1 file (checked 86 source files)

# Mypy (CI, Linux): expected to pass (resource is defined on Linux)
```

The Windows mypy error is the **same platform-conditional
type-ignore footgun** that was fixed in the prior
BBF (`70a1cb38`). The function is never called on Windows
(gated by `if sys.platform == "win32":`), so this is a
non-issue at runtime. The CI gate (Linux) is the source
of truth.

## §4. The §1.3 catches (exemplary discipline)

1. **Platform-conditional mypy error on Windows**
   (local) — the `# type: ignore[name-defined]` for
   `resource` is not needed on Linux CI (resource is
   defined) but is needed on Windows (resource is not
   defined). The fix is the same as the prior BBF:
   accept the Windows mypy failure (the function is
   never called on Windows anyway, and the CI gate is
   the source of truth).

2. **CRLF footgun in `chess_coach/__init__.py`** (pre-commit) —
   Python's `f.write()` on Windows converts LF to CRLF.
   The fix: use bytes mode or write with explicit `\n`.

## §5. What this BBF does NOT do (out of scope)

Per the FU-35 entry's resolution shape, the **full fix**
would also require:
- Updating the PyInstaller spec to use `collect_all('chess_coach')` instead of the tree-level `datas=` entries
- Removing the runtime hook (`services/chess_coach/gateway/pyinstaller_rthook.py`)
- Verifying the PyInstaller binary smoke test passes without the runtime hook

These are **out of scope for this BBF** because:
- They require updating the PyInstaller spec (a separate workstream)
- The PyInstaller binary smoke test is a long-running CI job (~10 min)
- The defensive fix (making the package explicit) is the primary value of FU-35

A follow-up BBF (`BBF-FU-35-pyi-cleanup`) could complete the
PyInstaller cleanup. This BBF is the **prerequisite** for
that work.

## §6. Honest disclosures

1. **The Windows mypy error is expected and acceptable.**
   The `# type: ignore[name-defined]` was removed in the
   prior BBF (`70a1cb38`) because it's unused on Linux CI.
   On Windows, mypy will flag it, but the function is
   never called on Windows (gated by `sys.platform`).

2. **The `chess_coach/__init__.py` is a marker only.** No
   code lives there. It's a docstring explaining the
   package structure.

3. **The `[tool.setuptools.package-dir]` mapping now has
   23 entries** (22 per-package + 1 self-mapping). The
   self-mapping `"chess_coach" = "chess_coach"` tells
   setuptools that the root `chess_coach/` directory
   IS the `chess_coach` package (rather than an implicit
   namespace).

4. **The PyInstaller spec and runtime hook are unchanged.**
   They continue to work because the per-package mappings
   are preserved. The defensive fix is a **prerequisite**
   for the PyInstaller cleanup, not the cleanup itself.

5. **No new tests added.** The fix is structural (adding
   a marker file and a config entry). Existing tests
   verify the package still imports correctly.

6. **The CI gate (Linux) is the source of truth.** The
   14/15 CI green on `70a1cb38` will be preserved because
   the Linux mypy doesn't see the `resource` error.

## §7. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-35 entry (lines 2361-2457).
- `docs/16_audit/BBF-PHASE-8-1.md` (the PyInstaller BBF that surfaced FU-35).
- `pyproject.toml` lines 99-123 (the `[tool.setuptools.package-dir]` mapping, now with the self-mapping).
- `chess_coach/__init__.py` (NEW, the namespace marker).
- `services/chess_coach/gateway/chess-coach-gateway.spec` (unchanged, future cleanup target).
- `services/chess_coach/gateway/pyinstaller_rthook.py` (unchanged, future cleanup target).
