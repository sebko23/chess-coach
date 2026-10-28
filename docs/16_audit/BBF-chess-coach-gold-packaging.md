# BBF-chess-coach-gold-packaging — declare `chess_coach.gold` as the canonical installed package

**Date:** 2026-10-28
**Type:** packaging surface correction (package declaration + import migration + artifact gate)
**Authorized by:** the `chess_coach.gold` package-surface decision directive (2026-10-28) and
the selected-implementation directive of the same date (product decision: **Option A**).
**Base commit:** `e9eed1b193e02cbcc2dcef33c45afa14a30fa8cc`

## §1. The defect

`services/chess_coach/gold/` existed in the source tree but was **absent from both the wheel
and the sdist**. The package was not merely "not exposed under its canonical name" — it was
not shipped at all, and neither `chess_coach.gold` nor `services.chess_coach.gold` was
importable from an installed distribution.

The measured matrix at the base commit:

| Import form | Source tree | Editable install, outside checkout | Clean wheel, outside checkout |
|---|---|---|---|
| `chess_coach.gold` | ✅ (via the `services.` root only) | ❌ `ModuleNotFoundError` | ❌ `ModuleNotFoundError` |
| `services.chess_coach.gold` | ✅ | ❌ `ModuleNotFoundError: No module named 'services'` | ❌ same |
| the known caller `tests/unit/test_eval_delta.py` | ✅ passes | ❌ import error | ❌ **collection `ImportError`** |

### Why checkout-based pytest concealed it

The sole importer used the legacy path:

```
tests/unit/test_eval_delta.py:7:from services.chess_coach.gold.eval_delta import eval_deltas
```

`services/` has **no `__init__.py` at any level** (`services/`, `services/chess_coach/`,
`libs/chess_coach/`, `apps/cli/chess_coach/` are all PEP 420 implicit namespaces). The
`services.` path therefore resolved only because pytest prepends the repository root to
`sys.path` — the first ancestor directory without an `__init__.py`. CI installs the project
**editable** (`pip install -e '.[dev]'`), and the editable finder maps exactly the 20
declared `chess_coach.*` packages and **never** maps `services`. So the test passed in CI
while no installed user could import the package at all.

### Historical origin

The omission dates from the package's creation: commit `168e6942` ("feat(gold): BBF-63.3
eval_deltas helper using engine_orch.EnginePool") added `gold/__init__.py`,
`gold/eval_delta.py`, and the test — and **did not touch `pyproject.toml`**.
`gold/__init__.py` has been 0 bytes since creation. No later packaging BBF added it: FU-35's
packaging half (`BBF-FU-35-pyinstaller-collect-all`) explicitly recorded the discrepancy as
out of scope.

### The scope of the defect beyond gold

All 21 `services.chess_coach…` import sites in the repository were confined to **six test
files**. Production code had **zero** `services.` imports — every production module uses
the canonical `chess_coach.*` namespace, and the only `services.` mention outside tests was
a prose comment at `services/chess_coach/gateway/routes/pdf_ingest.py:34` that documents
*why* the absolute path was rejected in favour of a relative import (the Docker image's
`WORKDIR` is not the repo root).

## §2. The canonical namespace and the intentional compatibility break

- **`chess_coach.gold` is the canonical installed namespace.** It is the only namespace the
  project ships; the wheel's `top_level.txt` is `chess_coach` and every declared package is a
  `chess_coach.*` path.
- **`chess_coach.gold` is a supported *internal installed library*, not a public product
  API.** It has no HTTP route, no console entry point, and no documented workflow. It is
  importable and testable from an installed distribution. That is the whole contract.
- **`services.chess_coach.gold` is intentionally unsupported. No alias, no shim, no
  `services` package markers, no namespace-package fallback was added.**

### Why the break is safe, stated explicitly

The former path was **checkout-only and never part of an installed distribution**. It is
unreachable outside a checkout under *both* install modes, so no downstream user can depend
on it; its only user was one test file inside this repository. This BBF therefore breaks no
public API.

### Why no alias was added

The repository has already recorded this exact hazard. `BBF-FU-22-windows-contract-correction.md`
§4 documents that the tree is importable under two dotted paths which load as **two distinct
module objects with two distinct global namespaces**, and that "a test that patches the wrong
instance silently asserts nothing". Keeping a `services.chess_coach.gold` alias would
institutionalise that hazard for this package: the same file reachable under two identities,
with mutable module state that a test could patch in one identity while the application
holds the other.

Adding a `services` package marker would also make `services` a permanent installed
top-level namespace — a generic directory name — in a distribution whose entire convention
is that the installed namespace is `chess_coach`.

## §3. The exact package mapping

Two lines in `pyproject.toml`, mirroring the existing `chess_coach.gateway` mapping pattern
exactly (no second packaging mechanism was invented):

```toml
[tool.setuptools]
packages = [
    ...
    "chess_coach.gold",  # BBF-chess-coach-gold-packaging: canonical installed namespace
    ...
]

[tool.setuptools.package-dir]
"chess_coach.gold" = "services/chess_coach/gold"  # BBF-chess-coach-gold-packaging
```

**Package-data:** none is required. The gold package has exactly one module and no data
files; the existing `[tool.setuptools.package-data]` entry covers only
`chess_coach.storage.migrations` and is unchanged.

**Unrelated `services` packages cannot leak.** `packages` is an explicit allow-list and the
mapping is per-package, exactly like `chess_coach.gateway` → `services/chess_coach/gateway`.
The artifact gate asserts this directly (see §5).

**Not changed:** dependencies, entry points, the build backend, `uv.lock`, the PyInstaller
spec, and the `[project.scripts]` table. This is a package-surface correction, not a
dependency change.

## §4. Import migration

Every `services.chess_coach…` import in the six affected test files was replaced with its
canonical `chess_coach.*` equivalent — 30 import sites across 6 files:

| File | Sites migrated | Canonical target |
|---|---|---|
| `tests/integration/test_pdf_import.py` | 3 | `chess_coach.gateway.routes.pdf_ingest` |
| `tests/unit/test_eval_delta.py` | 1 | `chess_coach.gold.eval_delta` |
| `tests/unit/test_pdf_ingest_route.py` | 8 | `chess_coach.gateway.routes.pdf_ingest` / `.routes` |
| `tests/unit/test_pdf_ingest_security.py` | 11 | `chess_coach.gateway.routes.pdf_ingest`, `chess_coach.pdf_ocr.subprocess_runner` |
| `tests/unit/test_polyglot_writer.py` | 1 | `chess_coach.repertoire.polyglot_writer` |
| `tests/unit/test_subprocess_runner.py` | 6 | `chess_coach.pdf_ocr.subprocess_runner` |

**Zero `services.` import statements remain in any `.py` in the repository.** The migration
changed no test semantics: no test was weakened, skipped, xfailed, or deleted.

Seven prose mentions of the old dotted path remain, in **documentation strings and metadata
literals** rather than imports:

- `scripts/curate_archetype_gold_auto.py:8,10,323,370` — docstring prose and the
  `metric_methodology` provenance string written into the generated corpus JSON.
- `services/chess_coach/gateway/routes/pdf_ingest.py:34` — a comment that explains why the
  absolute `services.` import was rejected in favour of a relative import.
- `tests/gold/archetypes_with_analyses_fixtures.py:5` — docstring prose.

That script's own imports are already canonical (`from chess_coach.profile import …`,
`from chess_coach.profile.archetypes import …`). These mentions are **provenance strings
describing the historical source path**, not import statements, and changing them would
rewrite recorded corpus provenance — out of scope for this BBF and not required by the
"zero remaining `services.chess_coach` imports" acceptance criterion, which is about imports.

## §5. Independent artifact validation

`scripts/dev/verify_gold_package_artifacts.py` is a **new, separate gate** — not a
checkout-based test. It:

1. Builds a **wheel and an sdist** from the committed source tree in an isolated venv.
2. **Inspects each archive independently**: the wheel must contain
   `chess_coach/gold/__init__.py` and `chess_coach/gold/eval_delta.py` and must contain
   **no `services/` tree** and no `services` top-level directory; the sdist must contain the
   same gold sources under its declared source path.
3. **Installs and validates each artifact separately** — the wheel's success does not
   satisfy the sdist's check, and vice versa.
4. Runs every probe from a **temporary directory outside the repository**, with the checkout
   and every editable path removed from `PYTHONPATH`, and with `PYTHONHOME`/`PYTHONSTARTUP`
   unset. The probe asserts that no checkout path and no editable finder are present on
   `sys.path`, so a checkout import **cannot** satisfy it.
5. Proves `import chess_coach.gold.eval_delta` succeeds from the installed artifact and that
   `eval_deltas` is callable.
6. Proves `services.chess_coach.gold` and `services.chess_coach.gold.eval_delta` are
   **absent** and raise `ModuleNotFoundError` (the no-alias contract).
7. Runs the migrated gold test against the **installed artifact**, not the checkout.

**Dependency condition, stated explicitly.** The artifacts are installed with `--no-deps`
and the runtime deps the gold import chain actually needs (`pydantic`) are installed
explicitly. The full project dependency tree (torch, sentence-transformers, qdrant-client)
is **not** installed: it is irrelevant to the package surface and would dominate the job's
runtime. The import chain under test — `chess_coach.gold.eval_delta` →
`chess_coach.engine_orch.pool` → `chess_coach.protocol_types.analysis` → `pydantic` — is
fully satisfied, so the probe is a real import proof and not a missing-dependency artefact.
This is a **package-surface** gate, not a dependency-resolution proof.

### Negative control

The gate was run against the **pre-BBF package declaration** (the base tree at
`e9eed1b1`, with the two `pyproject.toml` lines absent) and **fails for the real reason**:
`chess_coach.gold` is absent from the installed artifact and the migrated caller cannot
import it. The failure is an explicit assertion failure inside the gate — not a missing
selector, not a harness import error, not a pytest exit 5.

## §6. CI gate

A new **separate job** in `.github/workflows/smoke.yml` runs the artifact gate. It is kept
apart from the ordinary checkout-based unit tests precisely so that a checkout import cannot
make it pass. The job:

- builds both artifacts in isolated environments,
- inspects each independently,
- installs and validates each separately, outside the checkout,
- runs the migrated gold test against each installed artifact.

The job **fails** if either artifact omits gold, leaks unrelated `services` content, permits
the legacy import, or cannot import and exercise `chess_coach.gold.eval_delta` outside the
checkout.

**Preserved:** every existing CI job and the existing platform scope (`ubuntu-latest`).
No new OS matrix was added.

## §7. PyInstaller exclusion — unchanged

Gold is **not** part of the frozen runtime contract, and this BBF does not change that:

- `services/chess_coach/gateway/chess-coach-gateway.spec` is **not modified**. Its
  `CHESS_COACH_SUBPACKAGES` list (which drives `collect_all`) does not contain
  `chess_coach.gold`, and `grep -c 'chess_coach.gold'` against the spec returns **0**.
- The frozen bundle is driven by that explicit list, so adding a `pyproject.toml`
  declaration does **not** add gold to the binary. **Frozen-artifact impact: zero.**
- No gateway route imports the gold package: `services/chess_coach/gateway/routes/eval_verifier.py`
  re-implements the verifier inline against `chess_coach.datasets.l2_gold` and never touches
  `chess_coach.gold`.
- The existing PyInstaller binary regression test
  (`tests/integration/test_pyinstaller_binary.py`) remains green and unmodified.

## §8. FU-35 clarification

FU-35's `## Resolved` record carries a dated clarification (see the ledger). It states that
the gold package was absent from **both** the wheel and the sdist, and that the sole
checkout-only importer was **not** clean-install safe — a fact the prior "Out of scope
(deliberately)" paragraph did not record, because it only observed that "nothing imports it
as `chess_coach.gold`" and that the gateway and binary were unaffected. Both statements were
true; the clarification adds the measured packaging facts and records that this BBF
establishes the canonical installed surface with a clean-install CI gate.

**Not changed:** FU-35's status; the protected FU-22 (`1820-1918`), FU-35 (`2479-2582`), and
FU-38 (`2782-2919`) pointer values; any unrelated FU text; any other pointer.

## §9. What this BBF does not do

- No legacy `services.chess_coach.gold` alias, shim, or `services` package markers.
- `chess_coach.gold` is **not** classified as a public product API.
- Gold is **not** added to PyInstaller or the frozen runtime contract.
- No dependency added or removed; `uv.lock` untouched; no entry point changed; no build
  backend change.
- No test weakened, skipped, xfailed, or deleted.
- No FU status changed; no protected pointer edited; no unrelated finding rewritten.

---

## §10. Verification index

| Requirement | Where |
|---|---|
| Exact package mapping | §3, and the `pyproject.toml` diff (2 lines) |
| Import migration, zero remaining `services.` imports | §4 |
| Independent wheel + sdist contents and clean-install results | §5, and the gate's own output |
| Legacy namespace absent | §5 (probe assertion in both installs) |
| Checkout leakage prevented | §5 (probe asserts no checkout/editable path on `sys.path`) |
| Pre-BBF negative control | §5 |
| CI gate | §6 |
| PyInstaller exclusion | §7 |
| FU-35 clarification | §8 |
