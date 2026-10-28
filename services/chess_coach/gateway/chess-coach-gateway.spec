# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for the chess-coach-gateway sidecar binary.
#
# BBF-Phase8-1 (PyInstaller spec). Phase 8 minimum-viable installer,
# first BBF. See docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md
# for the full scoping brief.
#
# BBF-FU-35-pyi-cleanup (2026-10-27): collect the physical `chess_coach`
# package instead of bundling the source tree and patching sys.path at
# runtime. See docs/16_audit/BBF-FU-35-pyinstaller-collect-all.md.
#
# Build:    pyinstaller services/chess_coach/gateway/chess-coach-gateway.spec
# Entry:    chess_coach.gateway.__main__:main (the canonical entry point —
#           the same target as the `chess-coach-gateway` console script in
#           pyproject.toml's [project.scripts]).
# Target:   dist/chess-coach-gateway  (single-file --onefile binary)
# Platform: Linux x86_64 (the smoke-test platform; Windows artifact
#          will be produced separately on a Windows runner or via
#          Wine; the spec is platform-portable — same source, different
#          binary output).
#
# Package layout (FU-35): `chess_coach` is an EXPLICIT package — the repo
# root carries a physical `chess_coach/__init__.py` marker (added by
# BBF-FU-35-explicit-namespace, PR #161). Its subpackages are regular
# packages spread across three source roots, wired by
# `[tool.setuptools.package-dir]` in pyproject.toml:
#
#   chess_coach/            -> repo root (the __init__.py marker)
#   chess_coach.*           -> libs/chess_coach/*, services/chess_coach/*,
#                              apps/cli/chess_coach/*
#
# Collection: `collect_all("chess_coach")` CANNOT enumerate this layout on
# its own. PyInstaller resolves `chess_coach` through the install's import
# finder, and the setuptools editable finder exposes the root marker package
# while hiding the per-subpackage source directories from the finder — so a
# bare `collect_all("chess_coach")` returns 0 datas, 0 binaries, and 0 hidden
# imports. Collecting each declared SUBPACKAGE individually does work: each
# one resolves to its real source directory and lands in the bundle under the
# correct `chess_coach/<name>` target. (Measured: 104 datas across 22
# targets, 27 hidden imports.)
#
# The previous approach bundled the `services/chess_coach/` and
# `libs/chess_coach/` SOURCE TREES verbatim via `datas=`, then had a runtime
# hook (`pyinstaller_rthook.py`) prepend `_MEIPASS/services` and `_MEIPASS/libs`
# to `sys.path` so the implicit-namespace resolution worked at startup. That
# workaround is retired: it bundled `__pycache__/` and `.pyc` artifacts, swept
# in any future file added to those directories, and made the "services before
# libs" sys.path ordering load-bearing. The runtime hook file has been
# deleted; this spec collects the package instead of synthesizing it.
#
# Pre-implementation investigation (commit body of the BBF PR documents
# each finding; this header is the executable summary):
#
#   - Hidden imports: "chess" (python-chess) is the only confirmed
#     hidden import — lazy-imported at top level inside
#     try/except ImportError blocks in narration/validator.py,
#     datasets/l2_gold.py, datasets/narrative_gold.py, and
#     protocol_types/narration.py; plus one function-local lazy
#     import in narration/pipeline.py:_pv_to_san. PyInstaller's
#     static analysis often misses these. Adding "chess" to
#     hiddenimports catches them all in one shot.
#
#   - Data files: the 9 .sql migration files at
#     libs/chess_coach/storage/migrations/ are loaded via
#     importlib.resources.files() in storage/migrate.py. The
#     pyproject.toml setuptools.package-data declaration already
#     declares them; collect_all("chess_coach.storage.migrations")
#     bundles them into the binary's data dir.
#
#   - FU-4 win: sentence_transformers / torch are LAZY-IMPORTED
#     inside kb/embedder.py:_get_model() — never at module load.
#     PyInstaller's analysis won't follow the lazy import. The
#     excludes list keeps the binary small (~600MB torch
#     dependency not bundled). KB functionality (POST /v1/kb/similar,
#     POST /v1/kb/index) is therefore unavailable in this binary;
#     the smoke test does NOT exercise the KB path. This is
#     intentional and consistent with FU-4's design.
#
#   - Known limitation: /v1/profiles/explain reads a methodology
#     markdown file from a hardcoded relative path (parent[3] / docs
#     / 15_methodology / profile-metrics-v1.md). In the PyInstaller
#     bundle, that path resolves to nothing. The endpoint will
#     return an error message "Methodology doc not found" until
#     bundled or path-rewritten. Not exercised by the smoke test.
#
#   - Engine binaries: Stockfish + Maia paths are agent-Zero-specific
#     absolute paths with PATH fallback. On the smoke-test ubuntu-latest
#     runner, neither path exists; Stockfish falls back to 'stockfish'
#     (PATH lookup). The smoke-test runner does NOT install Stockfish
#     via apt; the engine_pool will start with 1 Stockfish slot whose
#     path is 'stockfish' but the engine binary is not present — the
#     route guards on engine availability and the binary should still
#     start / serve /v1/system/health regardless. This matches the
#     existing 'gateway-boot (clean install)' CI job which exercises
#     the gateway without engine binaries.
#
# Smoke test: tests/integration/test_pyinstaller_binary.py
#   - Builds the binary via PyInstaller CLI in CI
#   - Spawns the binary as a subprocess with a writable CHESS_COACH_DATA_DIR
#   - Polls /v1/system/health until 200 (with timeout)
#   - Asserts response shape (status: ok) and tears down the process
#   - Asserts the frozen artifact resolves `chess_coach` from the COLLECTED
#     package (not the source tree) — see the test's frozen-artifact checks.

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Repo root: this spec file is at services/chess_coach/gateway/.
# Repo root is the grandparent-of-parent directory.
SPEC_DIR = Path(SPECPATH).resolve()  # type: ignore[name-defined]  # noqa: F821
REPO_ROOT = SPEC_DIR.parents[2]  # services/chess_coach/gateway -> repo root

# The canonical entry point's physical file. PyInstaller's Analysis() takes
# FILE NAMES only — the "module:function" form is not supported (verified
# against PyInstaller 6.22.3: "ERROR: script '<...>:main' not found"). The
# file below IS the canonical entry point's module
# (`chess_coach.gateway.__main__`), and it is the same module the
# `chess-coach-gateway` console script in pyproject.toml targets. There is no
# parallel entry point and no source-tree path manipulation.
ENTRY_SCRIPT = str(SPEC_DIR / "__main__.py")

# The three source roots that hold the `chess_coach.*` subpackages. They go on
# `pathex` so PyInstaller's static analysis can resolve `import chess_coach.X`
# at build time (the root marker alone does not make the subpackages
# importable). This is ANALYSIS-TIME resolution only — it does not affect the
# frozen binary's runtime import path, which uses the collected package.
PACKAGE_ROOTS = [
    str(REPO_ROOT / "libs"),
    str(REPO_ROOT / "services"),
    str(REPO_ROOT / "apps" / "cli"),
]

# Every `chess_coach` subpackage declared in pyproject.toml's
# [tool.setuptools.packages]. Collected one by one because the split-package
# layout defeats a bare collect_all("chess_coach") (see the header).
CHESS_COACH_SUBPACKAGES = [
    "chess_coach.errors",
    "chess_coach.storage",
    "chess_coach.storage.migrations",
    "chess_coach.protocol_types",
    "chess_coach.uci",
    "chess_coach.testkit",
    "chess_coach.datasets",
    "chess_coach.gateway",
    "chess_coach.gateway.routes",
    "chess_coach.engine_orch",
    "chess_coach.analysis",
    "chess_coach.narration",
    "chess_coach.llm_router",
    "chess_coach.kb",
    "chess_coach.pdf_ocr",
    "chess_coach.profile",
    "chess_coach.debug",
    "chess_coach.jobs",
    "chess_coach.repertoire",
    "chess_coach.keychain",
    "chess_coach.log_redaction",
    "chess_coach.cli",
]

# Collect the physical package: data files (the .sql migrations and any other
# package data) plus the submodules of each declared subpackage.
_C_DATAS, _C_BINARIES, _C_HIDDEN = [], [], []
for _pkg in CHESS_COACH_SUBPACKAGES:
    _d, _b, _h = collect_all(_pkg)
    _C_DATAS += _d
    _C_BINARIES += _b
    _C_HIDDEN += _h

# The root marker package itself: its __init__.py must be in the bundle so the
# frozen binary has a physical `chess_coach` package (the smoke test asserts
# this). collect_all on the root returns nothing under an editable install, so
# the marker file is added as an explicit data entry.
_C_DATAS.append(
    (
        str(REPO_ROOT / "chess_coach" / "__init__.py"),
        "chess_coach",
    ),
)


_TP = [
    m
    for pkg in [
        'fastapi', 'starlette', 'uvicorn', 'pydantic', 'pydantic_settings',
        'anyio', 'aiosqlite', 'httpx', 'httpcore', 'h11',
        'dotenv', 'multipart', 'aiohttp', 'openai',
        'qdrant_client', 'pdf2image', 'numpy',
        'chess',
    ]
    for m in collect_submodules(pkg)
]

block_cipher = None


a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[str(REPO_ROOT), *PACKAGE_ROOTS],
    binaries=_C_BINARIES,
    datas=_C_DATAS,
    hiddenimports=[
        # python-chess (the 'chess' module) is lazily imported at
        # top level inside try/except ImportError in 4 sites:
        # narration/validator.py:8-12,
        # datasets/l2_gold.py:172-185,
        # datasets/narrative_gold.py:183-195,
        # protocol_types/narration.py:5-8.
        # Plus one function-local lazy import in
        # narration/pipeline.py:_pv_to_san. PyInstaller's static
        # analysis often misses these guarded top-level imports.
        # One entry covers all five call sites.
        'chess',
        # aiosqlite is imported at top level in 10 gateway route
        # modules. PyInstaller's static analysis normally catches these
        # because they're unguarded top-level imports -- but aiosqlite
        # is a known PyInstaller pain point because it depends on the
        # system sqlite3 shared library and a Python C-extension, both of
        # which PyInstaller's hook system can mis-detect on some
        # platforms. Adding it defensively costs nothing and preempts
        # the next iteration's likely 'ModuleNotFoundError: aiosqlite'
        # failure.
        'aiosqlite',
        # The third-party packages that chess_coach.gateway imports at the
        # top of app.py (fastapi, uvicorn) need to be added to
        # hiddenimports so PyInstaller's static analysis includes them in
        # the PYZ and the runtime can resolve them via the frozen-module
        # finder. Without these entries, app.py's
        # `from fastapi import FastAPI, ...` fails at runtime with
        # `ModuleNotFoundError: No module named 'fastapi'`.
        #
        # Per Sebastian's 2026-09-05 directive: "Don't add everything
        # speculatively -- add what the error names, let CI run, add the
        # next thing if it fails again." So this iteration adds only the
        # five packages the prior CI log + the app.py import line +
        # uvicorn's known module decomposition imply:
        'fastapi',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
    ] + _TP + _C_HIDDEN,
    hookspath=[],
    hooksconfig={},
    # No runtime hooks. The retired `pyinstaller_rthook.py` used to prepend
    # _MEIPASS/services and _MEIPASS/libs to sys.path so the implicit
    # namespace package resolved at startup. The package is now COLLECTED,
    # so the frozen binary imports it from the collected package tree and
    # needs no sys.path surgery.
    runtime_hooks=[],
    excludes=[
        # FU-4 architectural decision: sentence_transformers / torch
        # are LAZY-IMPORTED inside kb/embedder.py:_get_model(). They
        # are NEVER imported at gateway startup. Excluding them keeps
        # the binary size manageable (~600MB torch dependency not
        # bundled). The KB route (/v1/kb/similar, /v1/kb/index) is
        # therefore unavailable in this binary; the smoke test does
        # NOT exercise the KB path. If a future BBF wants KB in the
        # sidecar, drop this exclude and add a hiddenimport entry.
        'torch',
        'sentence_transformers',
        'transformers',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='chess-coach-gateway',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
