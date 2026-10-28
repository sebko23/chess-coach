# BBF-FU-35-pyinstaller-collect-all — collect the physical `chess_coach` package in the PyInstaller build

**Sprint intent:** Retire the PyInstaller packaging workaround. The frozen gateway binary
must carry the collected physical `chess_coach` package instead of the source tree plus a
runtime hook that patched `sys.path`.

**Base:** `main @ 4af7e7e2e6bc7ae10fc0d47d1bfd17fac34fbe8a`.

This is the `BBF-FU-35-pyi-cleanup` follow-up named in FU-35's ledger entry: the
PyInstaller spec update, the runtime-hook removal, and the binary smoke test without the
hook. FU-35's structural fix (PR #161, `99a355df`) landed earlier; this BBF completes it.

---

## §1. What was actually wrong

FU-35's entry described the pre-#161 state accurately, but by the time this BBF started,
two of its claims were already stale:

1. *"There is no physical `chess_coach/__init__.py` at the repo root."* — **False since PR
   #161.** `chess_coach/__init__.py` exists at the repo root (850 bytes, a documented
   namespace marker). The PyInstaller spec's `datas=` comment still asserted the opposite
   and said `collect_all()` *"does not enumerate implicit namespace packages."* Both claims
   were wrong about the current tree.

2. *"PyInstaller's `collect_all()` does not enumerate implicit namespace packages, so it
   cannot enumerate `chess_coach.*` submodules."* — **The premise no longer applies.** Every
   `chess_coach` subpackage is a REGULAR package (each has its own `__init__.py`); only the
   root marker was ever implicit, and it is now explicit.

But the *conclusion* was still half-true, for a different reason. `collect_all("chess_coach")`
still fails — not because of namespace semantics, but because of how the package is SPLIT
across three source roots:

| root | subpackages |
|---|---|
| `chess_coach/` (repo root) | the `__init__.py` marker only |
| `libs/chess_coach/*` | `errors`, `storage`, `storage.migrations`, `protocol_types`, `uci`, `testkit`, `datasets` |
| `services/chess_coach/*` | `gateway`, `gateway.routes`, `engine_orch`, `analysis`, `narration`, `llm_router`, `kb`, `pdf_ocr`, `profile`, `debug`, `jobs`, `repertoire`, `keychain`, `log_redaction` |
| `apps/cli/chess_coach/*` | `cli` |

`[tool.setuptools.package-dir]` in `pyproject.toml` maps each `chess_coach.X` to its own
source directory, so `chess_coach` is one logical package spread over three trees.

---

## §2. Measured: `collect_all` behaves differently under editable vs non-editable installs

PyInstaller resolves a package through the *install's* import finder, and the two install
modes expose the split package differently. Measured with PyInstaller 6.22.3 on
Python 3.11.18, Linux x86_64:

| install mode | `collect_all("chess_coach")` result |
|---|---|
| `pip install -e .` (the CI job's mode) | **0 datas, 0 binaries, 0 hidden imports** — the setuptools editable finder exposes the root marker package and hides the per-subpackage source directories from the finder |
| `pip install .` (non-editable) | **94 datas, 27 hidden imports, all 21 subpackages** — the physical package tree is visible |

The editable-install warning is explicit:
`collect_data_files - skipping data collection for module 'chess_coach' as it is not a package.`

Collecting each declared subpackage **individually** works under BOTH modes, because each
subpackage resolves to its real source directory:

| mode | per-subpackage collection |
|---|---|
| editable | 104 datas across 22 `chess_coach/...` targets, 27 hidden imports |
| non-editable | same shape; the root `collect_all` also works |

**The spec therefore collects per-subpackage**, which is correct in the CI job (editable) and
does not depend on the install mode. The root marker `__init__.py` is added as an explicit
`datas` entry, because `collect_all` on the root returns nothing under an editable install
and the marker must be in the bundle for the frozen binary to have a physical
`chess_coach` package at all.

---

## §3. The canonical entry point

The canonical entry point is `chess_coach.gateway.__main__:main` — the same target as the
`chess-coach-gateway` console script in `pyproject.toml`'s `[project.scripts]`.

PyInstaller's `Analysis()` accepts **file names only**; the `module:function` form is not
supported. Verified against PyInstaller 6.22.3: passing `"chess_coach.gateway.__main__:main"`
as the script argument fails with `ERROR: script 'chess_coach.gateway.__main__:main' not found`.
The spec therefore points `Analysis()` at the canonical entry point's own physical file,
`services/chess_coach/gateway/__main__.py` — which IS that module. There is **no parallel
entry point** and **no source-tree path manipulation** in the entry point itself.

The three package roots are added to `pathex` so PyInstaller's *analysis-time* static
analysis can resolve `import chess_coach.X`. That is a build-time concern only; the frozen
binary's runtime import path comes from the collected package (proven in §5).

---

## §4. Runtime hook removed

`services/chess_coach/gateway/pyinstaller_rthook.py` (74 lines) is **deleted**. It is not
renamed, not retained as a fallback, and not replaced with a source-tree monkeypatch. The
spec's `runtime_hooks=[]`.

The hook existed to prepend `_MEIPASS/services` and `_MEIPASS/libs` to `sys.path` so the
implicit namespace package resolved at startup. It is unnecessary once the package is
collected, and it carried the three fragilities FU-35's entry named: it bundled
`__pycache__/` and `.pyc` artifacts, it swept in any future file added to those directories,
and it made the "services before libs" `sys.path` ordering load-bearing.

---

## §5. Frozen-artifact proof

Platform: Linux x86_64 (kernel 6.18.54.1-microsoft-standard-WSL2), Python 3.11.18,
PyInstaller 6.22.3. Build command (the CI job's):

```
pyinstaller --clean --noconfirm \
  --distpath /tmp/out --workpath /tmp/work \
  services/chess_coach/gateway/chess-coach-gateway.spec
```

Build exit code 0. Artifact: 58,378,392-byte ELF.

A second binary was built with the identical collection logic but a probe entry script, to
observe the frozen binary's own import resolution. It reported:

```
chess_coach.__file__ : /tmp/_MEI0000097bJRMmbs/chess_coach/__init__.py
chess_coach.__path__ : ['/tmp/_MEI0000097bJRMmbs/chess_coach']
chess_coach.gateway  : /tmp/_MEI0000097bJRMmbs/chess_coach/gateway/__init__.py
chess_coach.storage  : /tmp/_MEI0000097bJRMmbs/chess_coach/storage/__init__.py
sys.path             : /tmp/_MEI.../base_library.zip
                       /tmp/_MEI.../python3.11/lib-dynload
                       /tmp/_MEI...
                       /tmp/_MEI.../setuptools/_vendor
```

So the frozen executable imports the **collected physical package** under its `_MEI` root.
No checkout path appears in the frozen `sys.path`, and no `_MEI.../services` or
`_MEI.../libs` entry exists (the retired hook's injection). The physical root marker
`chess_coach/__init__.py` is present in the bundle.

The built binary also served `GET /v1/system/health` with HTTP 200 and body
`{"status": "degraded", "components": [...]}` — `degraded` because the narration grounding
corpus is empty, which is the pre-existing expected state for this smoke (the corpus is not
bundled); the `gateway` and `storage` components both report `ok`.

---

## §6. Bundle-content comparison: pre-BBF spec vs this BBF's spec

Both specs were built against the same corpus and their `Analysis-00.toc` datas manifests
compared. The TOC's datas element holds `(target, source, 'DATA')` triples; the **target** is
the path a file occupies inside the bundle, so only the target side describes bundle
contents.

| bundle target | pre-BBF | this BBF |
|---|---|---|
| starts `services/chess_coach` | **266** | **0** |
| starts `libs/chess_coach` | **94** | **0** |
| starts `chess_coach/` | 18 | **188** |
| contains `__pycache__` | **170** | **0** |
| ends `.pyc` | **170** | **0** |
| is `chess_coach/__init__.py` | 0 | **2** |
| `pyinstaller_rthook` anywhere in the TOC | **7** | **0** |
| total DATA entries | 483 | 293 |

The pre-BBF build carried the checkout's `__pycache__` and `.pyc` files (170 each) and
placed the source trees inside the bundle; this BBF's build carries the collected package
and neither build artifact.

### Size reduction: approximately 0.6%

| | bytes |
|---|---|
| pre-BBF binary | 58,713,632 |
| this BBF's binary | 58,378,664 |
| **delta** | **−334,968 (−0.6%)** |

**Reported honestly as a secondary result.** FU-35's entry predicted the binary size
"drops (no source-tree inclusion, just the modules actually imported)". The direction is
right but the magnitude is small: the artifact is dominated by third-party dependencies
(~58 MB of fastapi/uvicorn/pydantic/numpy/PIL/openai), so removing the source tree saves
only ~335 KB. The real wins are correctness and hygiene, not size — the bundle no longer
carries the checkout's `__pycache__`, no longer sweeps in future files added to those
directories, and no longer depends on a load-bearing `sys.path` ordering.

---

## §7. The regression test

`tests/integration/test_pyinstaller_binary.py` gains
`test_pyinstaller_binary_uses_collected_package`, which inspects the build's own
`Analysis-00.toc` manifest and fails if:

1. the physical `chess_coach/__init__.py` marker is absent from the bundle;
2. a collected subpackage (`chess_coach/gateway`, `chess_coach/storage`) is missing;
3. the bundle carries a source tree (`services/chess_coach` or `libs/chess_coach` targets);
4. the bundle carries `__pycache__` or `.pyc` artifacts;
5. the retired runtime hook is still bundled.

The assertions were derived from the §6 comparison rather than guessed, and the test was
run against both builds to confirm it discriminates: it **passes** against this BBF's build
and **fails** against the pre-BBF source-tree build.

---

## §8. Out of scope (deliberately)

- **The `chess_coach.gold` packaging discrepancy.** `services/chess_coach/gold/` exists on
  disk but is absent from `pyproject.toml`'s `[tool.setuptools.packages]` and
  `[tool.setuptools.package-dir]`. Nothing imports it as `chess_coach.gold` (the only
  importer, `tests/unit/test_eval_delta.py`, uses
  `from services.chess_coach.gold.eval_delta import eval_deltas`), so the gateway does not
  need it and the binary is unaffected. Adding it would change the package's install
  surface, which is a packaging decision beyond this BBF.
- **`pyproject.toml`** — unchanged. The `package-dir` mapping and the `packages` list are
  already correct for the gateway.
- **CI workflow files** — unchanged. The existing `pyinstaller-binary-smoke` job already
  builds the binary and runs this test file; the new test runs under that job.
- **The `/v1/profiles/explain` methodology-doc limitation** and the **FU-4 torch exclusion** —
  unchanged, pre-existing, and out of scope.

---

## §9. Cross-references

- FU-35 — the ledger entry this BBF closes; its `PARTIALLY RESOLVED` status and the
  `BBF-FU-35-pyi-cleanup` pointer.
- PR #161 (`99a355df`) — the structural fix that added the root marker and the
  `package-dir` self-mapping.
- `docs/16_audit/BBF-FU-35-explicit-namespace.md` — the structural-fix brief.
- `docs/16_audit/BBF-PHASE-8-1.md` — the original spec BBF, including the four CI failures
  that produced the runtime hook.
- `docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md` §3.1 — the known
  PyInstaller/namespace-layout complication.
