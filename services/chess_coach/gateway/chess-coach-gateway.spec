# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for the chess-coach-gateway sidecar binary.
#
# BBF-Phase8-1 (PyInstaller spec). Phase 8 minimum-viable installer,
# first BBF. See docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md
# for the full scoping brief.
#
# Build:    pyinstaller services/chess_coach/gateway/chess-coach-gateway.spec
# Entry:    chess_coach.gateway.__main__:main (per pyproject.toml:68)
# Target:   dist/chess-coach-gateway  (single-file --onefile binary)
# Platform: Linux x86_64 (the smoke-test platform; Windows artifact
#          will be produced separately on a Windows runner or via
#          Wine; the spec is platform-portable — same source, different
#          binary output).
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
#   - Data files: 9 .sql migration files at
#     libs/chess_coach/storage/migrations/ are loaded via
#     importlib.resources.files() in storage/migrate.py:70. The
#     pyproject.toml:119-120 setuptools.package-data declaration
#     already declares this; PyInstaller needs the matching
#     --add-data / datas entry to bundle them.
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
#   - Spawns the binary as a subprocess with --host 127.0.0.1
#     --port 18080 (configurable via env) and a writable CHESS_COACH_DATA_DIR
#   - Polls /v1/system/health until 200 (with timeout)
#   - Asserts response shape (status: ok) and tears down the process
#
# Verification on origin/main@4c30a7b7 (the SHA at the time of this BBF):
#   - origin/main HEAD: 4c30a7b7feb4a2c3cf77ebd8c058092f5e3b5511
#   - PR #100..#104 (rebrand + ADR-0007..0009): all merged
#   - apps/desktop/src-tauri/tauri.conf.json: identity fields rebranded
#   - apps/desktop/src-tauri/tauri.conf.json: externalBin NOT yet
#     declared (deferred to BBF-Tauri-sidecar; this BBF does NOT
#     touch tauri.conf.json)

import os
from pathlib import Path

# Repo root: this spec file is at services/chess_coach/gateway/.
# Repo root is the grandparent-of-parent directory.
SPEC_DIR = Path(SPECPATH).resolve()  # type: ignore[name-defined]  # noqa: F821
REPO_ROOT = SPEC_DIR.parents[2]  # services/chess_coach/gateway -> repo root

# Path to the runtime hook (the file that runs at binary startup,
# before __main__.py's imports are resolved). Created in this same
# directory; the spec passes it via the runtime_hooks= argument to
# Analysis() so PyInstaller bundles it into the binary and executes
# it at startup.
PYI_RTHOOK_PATH = str(SPEC_DIR / "pyinstaller_rthook.py")

block_cipher = None


a = Analysis(
    ['__main__.py'],
    pathex=[str(SPEC_DIR), str(REPO_ROOT)],
    binaries=[],
    datas=[
        # chess_coach is a PEP 420 implicit namespace package
        # (declared via [tool.setuptools.package-dir] in pyproject.toml;
        # no physical chess_coach/__init__.py). PyInstaller's
        # collect_all() does not enumerate implicit namespace packages,
        # so we cannot rely on its enumeration. Instead, bundle the
        # source-tree directories of the namespace package verbatim
        # via datas=; the runtime hook then adds _MEIPASS/services and
        # _MEIPASS/libs to sys.path so the implicit-namespace
        # resolution works at binary startup. Future Phase 8 BBFs may
        # add a chess_coach/__init__.py to make the namespace package
        # explicit (the structural fix documented as FU-ChessCoach-
        # NamespacePackage-Explicit in OPEN-FOLLOWUPS), which would let
        # us drop these tree-level datas entries in favor of
        # collect_all.
        (
            str(REPO_ROOT / 'services/chess_coach/'),
            'services/chess_coach',
        ),
        (
            str(REPO_ROOT / 'libs/chess_coach/'),
            'libs/chess_coach',
        ),
        # The 9 SQL migration files at libs/chess_coach/storage/migrations/
        # are loaded at runtime via importlib.resources.files()
        # (storage/migrate.py:70). setuptools.package-data in
        # pyproject.toml:119-120 declares them; PyInstaller needs
        # this --add-data to bundle them into the binary's data dir.
        (
            str(REPO_ROOT / 'libs/chess_coach/storage/migrations/*.sql'),
            'chess_coach/storage/migrations',
        ),
    ],
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
        # modules (backfill_analyses.py:33, blunder_routes.py:4,
        # eval_graph.py:20, game_routes.py:4, lichess_import.py:18,
        # narration.py:15, pdf_ingest.py:27, pgn_import.py:32,
        # players.py:4, profile.py:7). PyInstaller's static analysis
        # normally catches these because they're unguarded top-level
        # imports -- but aiosqlite is a known PyInstaller pain point
        # because it depends on the system sqlite3 shared library and
        # a Python C-extension, both of which PyInstaller's hook
        # system can mis-detect on some platforms. Adding it
        # defensively costs nothing and preempts the next iteration's
        # likely 'ModuleNotFoundError: aiosqlite' failure.
        'aiosqlite',
    ],
    hookspath=[],
    hooksconfig={},
    # The runtime hook runs at binary startup, BEFORE __main__.py's
    # imports are resolved. It adjusts sys.path to expose the
    # synthesized chess_coach namespace package so that
    # `import chess_coach.gateway.app` works in the binary.
    # See pyinstaller_rthook.py for the mechanism.
    runtime_hooks=[PYI_RTHOOK_PATH],
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