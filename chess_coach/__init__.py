"""Explicit namespace package marker for `chess_coach`.

Per FU-35 (see `docs/16_audit/OPEN-FOLLOWUPS.md`), the `chess_coach`
package was previously a PEP 420 implicit namespace package. This
`__init__.py` makes it an explicit namespace package, which:

1. Enables PyInstaller's `collect_all("chess_coach")` to enumerate
   submodules (implicit namespace packages are not enumerable).
2. Makes the package layout more robust to the B2 cross-platform
   import bug class (explicit `__init__.py` prevents silent
   breakage when setuptools or other tools assume a regular
   package layout).
3. Documents the package structure for new contributors.

The actual submodules live under `libs/chess_coach/` and
`services/chess_coach/` per the `[tool.setuptools.package-dir]`
mapping in `pyproject.toml`. This file is a marker only; no
code lives here.
"""
