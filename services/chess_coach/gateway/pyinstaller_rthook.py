"""PyInstaller runtime hook for the chess-coach-gateway binary.

BBF-Phase8-1. Phase 8 minimum-viable installer, fifth iteration
(followed 4 prior CI failures on the same branch:
  1. path-doubling in Analysis() first arg -- fixed
  2. relative imports in __main__.py -- fixed
  3. 'No module named chess_coach.gateway' at runtime, attempt 1
     (collect_all + runtime hook) -- collect_all doesn't enumerate
     PEP 420 implicit namespace packages
  4. 'No module named chess_coach.gateway' at runtime, attempt 2
     -- this iteration: bundle the source tree verbatim via datas
     and add the parents to sys.path

PyInstaller's bootloader unpacks the bundled data into a temporary
directory at runtime and exposes it via sys._MEIPASS. The
chess_coach package is a PEP 420 implicit namespace package
(declared via pyproject.toml [tool.setuptools.package-dir] mappings;
there is no physical chess_coach/__init__.py).

Per the spec's datas= entries, the binary bundles two source-tree
directories verbatim:

  _MEIPASS/services/chess_coach/    <-- chess_coach.gateway,
                                       chess_coach.engine_orch,
                                       chess_coach.narration,
                                       chess_coach.kb, ...
  _MEIPASS/libs/chess_coach/        <-- chess_coach.storage,
                                       chess_coach.protocol_types,
                                       chess_coach.errors,
                                       chess_coach.datasets, ...

Both trees have a top-level directory named 'chess_coach' (the
namespace package prefix). When 'chess_coach' is in sys.path's
parents (i.e., either _MEIPASS/services or _MEIPASS/libs is in
sys.path), Python's import machinery resolves 'import chess_coach.X'
by walking sys.path looking for a 'chess_coach' subdirectory.

This hook adds _MEIPASS/services and _MEIPASS/libs to sys.path so
that 'chess_coach' (the namespace package name) is reachable from
both roots. The order matters slightly: services/ comes first
because most of the runtime code (gateway, routes, engine_orch)
lives there, but both paths satisfy the same import (Python's
import system caches by name, so once chess_coach.gateway is
loaded from services/, future imports of chess_coach.storage from
the same package name resolve to the same module).

The hook runs BEFORE the bundled __main__.py is executed, which is
the standard PyInstaller contract for runtime hooks (see
https://pyinstaller.org/en/stable/hooks.html#hook-script).

Future structural fix (logged as FU-ChessCoach-NamespacePackage-
Explicit in OPEN-FOLLOWUPS): adding a physical chess_coach/__init__.py
would let us drop the tree-level datas entries in favor of PyInstaller's
collect_all() primitive, which enumerates regular packages correctly.
That change touches pyproject.toml + the package directory structure +
every import in the codebase and needs its own ADR-level consideration.
"""

import os
import sys


def _prepend_if_dir(path: str) -> None:
    """Add path to sys.path (prepend) if it's a directory and not already there."""
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


# Add the two parents of the bundled chess_coach namespace package
# trees so 'import chess_coach.*' resolves at runtime. PyInstaller's
# bootloader has already extracted the datas entries by the time this
# hook runs.
_prepend_if_dir(os.path.join(sys._MEIPASS, "services"))  # type: ignore[attr-defined]  # noqa: F821
_prepend_if_dir(os.path.join(sys._MEIPASS, "libs"))  # type: ignore[attr-defined]  # noqa: F821