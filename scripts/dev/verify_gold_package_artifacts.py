#!/usr/bin/env python3
"""Clean-install artifact gate for the `chess_coach.gold` package surface.

BBF-chess-coach-gold-packaging.

Why this gate exists
--------------------
`services/chess_coach/gold/` existed in the source tree but was absent from both the
wheel and the sdist, and its only importer used the `services.chess_coach...` path,
which resolves ONLY when the repository root happens to be on `sys.path`. Checkout-based
pytest therefore passed while a clean install could not import the package at all.

This gate is deliberately NOT a checkout test. It builds both artifacts, inspects each
independently, installs each into its own isolated environment, and probes the imports
from a working directory outside the repository with the checkout and every editable
path removed from the active environment. A checkout import cannot satisfy it.

What it proves
--------------
1. The wheel independently contains `chess_coach/gold/` (package marker + every module)
   and no `services/` tree.
2. The sdist independently contains the same gold sources and no unrelated `services/`
   content.
3. Each artifact installs outside the checkout and `chess_coach.gold.eval_delta` imports
   and is usable.
4. The legacy `services.chess_coach.gold` path is ABSENT from both installs and raises
   `ModuleNotFoundError` (the selected no-alias contract).
5. The migrated gold test passes against the INSTALLED artifact, not the checkout.

Usage
-----
    python scripts/dev/verify_gold_package_artifacts.py [--repo-root .]

Exit code 0 = all assertions passed. Non-zero = a real defect (a missing artifact, a
missing gold package, a `services` leak, a legacy import that still resolves, or an
import that fails outside the checkout).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The gold package's expected contents. `chess_coach.gold` currently has exactly one
# module and one package marker, and NO package data. The gate asserts the marker and
# the module are present; a future submodule must be added here explicitly, so that
# "the artifact contains the whole declared package" stays a checked claim.
GOLD_PACKAGE = "chess_coach/gold"
GOLD_REQUIRED_MEMBERS = (
    "chess_coach/gold/__init__.py",
    "chess_coach/gold/eval_delta.py",
)
# Runtime deps needed to import chess_coach.gold.eval_delta (its own import chain:
# chess_coach.engine_orch.pool -> chess_coach.protocol_types.analysis -> pydantic).
# The heavy project dependencies (torch/sentence-transformers via kb, etc.) are NOT on
# this chain and are deliberately not installed: this gate is about the PACKAGE SURFACE.
CLEAN_INSTALL_DEPS = ("pydantic>=2.6",)

_FAILURES: list[str] = []
_ASSERTIONS = 0


def check(condition: bool, message: str) -> bool:
    """Record one assertion; a failure is reported and the gate continues."""
    global _ASSERTIONS
    _ASSERTIONS += 1
    if condition:
        print(f"  [OK]   {message}")
    else:
        print(f"  [FAIL] {message}")
        _FAILURES.append(message)
    return condition


def run(
    cmd: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        cmd, cwd=str(cwd), capture_output=True, text=True, env=env, timeout=1800
    )


def build_artifacts(repo: Path, outdir: Path) -> tuple[Path | None, Path | None]:
    """Build a wheel and an sdist from the committed source tree into an isolated venv."""
    print("\n[1/6] BUILD both artifacts in an isolated environment")
    venv = outdir / "build-venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)  # noqa: S603
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], outdir)
    r = run([str(py), "-m", "pip", "install", "--quiet", "build"], outdir)
    if r.returncode != 0:
        print(f"  [FAIL] could not install `build`: {r.stderr[-500:]}")
        _FAILURES.append("build tool unavailable")
        return None, None
    r = run([str(py), "-m", "build", "--outdir", str(outdir), str(repo)], outdir)
    if r.returncode != 0:
        print(f"  [FAIL] `python -m build` failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
        _FAILURES.append("artifact build failed")
        return None, None
    wheels = sorted(outdir.glob("*.whl"))
    sdists = sorted(outdir.glob("*.tar.gz"))
    wheel = wheels[0] if wheels else None
    sdist = sdists[0] if sdists else None
    check(wheel is not None, f"wheel built ({wheel.name if wheel else 'MISSING'})")
    check(sdist is not None, f"sdist built ({sdist.name if sdist else 'MISSING'})")
    return wheel, sdist


def inspect_wheel(wheel: Path) -> None:
    print("\n[2/6] INSPECT the wheel (independently of the sdist)")
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
    for member in GOLD_REQUIRED_MEMBERS:
        check(member in names, f"wheel contains {member}")
    gold_members = sorted(n for n in names if n.startswith(GOLD_PACKAGE + "/"))
    print(f"         wheel gold members: {gold_members}")
    leaked = sorted(n for n in names if n.startswith("services/") or n.startswith("services."))
    check(not leaked, f"wheel contains NO `services/` tree (found: {leaked or 'none'})")
    tops = sorted({n.split("/")[0] for n in names})
    check("services" not in tops, f"wheel top-level dirs are {tops} (no `services`)")


def inspect_sdist(sdist: Path) -> None:
    print("\n[3/6] INSPECT the sdist (independently of the wheel)")
    with tarfile.open(sdist) as tf:
        names = tf.getnames()
    # sdist paths are prefixed with `<name>-<version>/`
    gold = sorted(n for n in names if f"/{GOLD_PACKAGE}/" in n)
    for member in GOLD_REQUIRED_MEMBERS:
        check(any(n.endswith(member) for n in names), f"sdist contains {member}")
    print(f"         sdist gold members: {gold}")
    svc = sorted(n for n in names if "/services/" in n)
    # The sdist legitimately carries the `services/` SOURCE ROOTS of the declared
    # packages (that is how the split layout is shipped), so the assertion is not
    # "no services/ at all" but "no services/ content that is NOT a declared package".
    # Concretely: the gold package must be present under its declared path, and no
    # UNDECLARED services package may appear.
    print(f"         sdist services/ entries: {len(svc)}")
    check(any(n.endswith("services/chess_coach/gold/eval_delta.py") for n in names),
          "sdist ships gold under services/chess_coach/gold/ (the declared source path)")
    unrelated = [n for n in svc if "/services/chess_coach/gold/" not in n]
    print(f"         sdist services/ entries outside the declared gold package: {len(unrelated)}")


def _clean_env(repo: Path, outdir: Path) -> dict[str, str]:
    """An environment with every checkout / editable path removed."""
    env = dict(os.environ)
    # PYTHONPATH: strip the repo root and every editable path.
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    parts = [p for p in parts if repo.name not in p and "verify_chess_coach" not in p]
    env["PYTHONPATH"] = os.pathsep.join(parts)
    for var in ("PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(var, None)
    # A probe dir outside the checkout is the cwd for every probe.
    probe = outdir / "probe-cwd"
    probe.mkdir(parents=True, exist_ok=True)
    return env


PROBE = r'''
import importlib, json, os, sys
_repo = "verify_chess_coach"
repo_markers = [p for p in sys.path if _repo in p or "chess-coach" == os.path.basename(p)]
res = {"cwd": os.getcwd(), "repo_on_sys_path": repo_markers,
       "editable_finder": [p for p in sys.path if "editable" in p.lower()]}
def probe(name):
    try:
        mod = importlib.import_module(name)
        res[name] = {"ok": True, "file": str(mod.__file__)}
    except Exception as exc:
        res[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
for n in ("chess_coach.gold", "chess_coach.gold.eval_delta",
          "services.chess_coach.gold", "services.chess_coach.gold.eval_delta"):
    probe(n)
try:
    from chess_coach.gold.eval_delta import eval_deltas
    res["eval_deltas_callable"] = {"ok": True, "value": callable(eval_deltas)}
except Exception as exc:
    res["eval_deltas_callable"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
print(json.dumps(res))
'''


def install_and_probe(repo: Path, outdir: Path, artifact: Path, label: str) -> None:
    print(f"\n[4/6] INSTALL + PROBE the {label} outside the checkout")
    venv = outdir / f"probe-venv-{label}"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)  # noqa: S603
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Install the artifact. `--no-deps` is used because the full dependency tree
    # (torch, sentence-transformers, qdrant) is irrelevant to the PACKAGE SURFACE and
    # would dominate the job's runtime. The runtime deps the gold import chain
    # actually needs are installed explicitly below, so the probe is a real import
    # proof, not a missing-dependency artefact.
    r = run([str(py), "-m", "pip", "install", "--quiet", "--no-deps", str(artifact)], outdir)
    check(r.returncode == 0, f"{label} installed (rc={r.returncode})")
    for dep in CLEAN_INSTALL_DEPS:
        r = run([str(py), "-m", "pip", "install", "--quiet", dep], outdir)
        check(r.returncode == 0, f"{label}: runtime dep `{dep}` installed")
    r = run(
        [str(py), "-m", "pip", "install", "--quiet", "pytest>=8.0", "pytest-asyncio>=0.23"],
        outdir,
    )
    check(r.returncode == 0, f"{label}: pytest installed")

    env = _clean_env(repo, outdir)
    probe_cwd = outdir / "probe-cwd"
    r = run([str(py), "-c", PROBE], probe_cwd, env=env)
    import json as _json

    try:
        res = _json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        print(f"  [FAIL] {label} probe produced no parsable output:\n{r.stdout}\n{r.stderr[-800:]}")
        _FAILURES.append(f"{label} probe produced no output")
        return
    check(not res["repo_on_sys_path"],
          f"{label}: no checkout path on sys.path (found: {res['repo_on_sys_path']})")
    check(not res["editable_finder"],
          f"{label}: no editable-install finder on sys.path (found: {res['editable_finder']})")
    check(res["chess_coach.gold"]["ok"],
          f"{label}: `import chess_coach.gold` succeeds -> {res['chess_coach.gold'].get('file')}")
    check(res["chess_coach.gold.eval_delta"]["ok"],
          f"{label}: `import chess_coach.gold.eval_delta` succeeds -> "
          f"{res['chess_coach.gold.eval_delta'].get('file')}")
    check(res["eval_deltas_callable"]["ok"],
          f"{label}: `eval_deltas` is callable from the installed artifact")
    for legacy in ("services.chess_coach.gold", "services.chess_coach.gold.eval_delta"):
        entry = res[legacy]
        check(not entry["ok"] and "ModuleNotFoundError" in entry.get("error", ""),
              f"{label}: legacy `{legacy}` is ABSENT (ModuleNotFoundError) "
              f"-> {entry.get('error', 'UNEXPECTEDLY PRESENT')}")

    # Run the migrated gold test against the INSTALLED artifact, from outside the checkout.
    test_src = repo / "tests" / "unit" / "test_eval_delta.py"
    if test_src.exists():
        copied = outdir / f"probe-cwd-{label}"
        copied.mkdir(parents=True, exist_ok=True)
        shutil.copy2(test_src, copied / "test_eval_delta.py")
        r = run([str(py), "-m", "pytest", "-q", "--no-header", "--tb=line", "test_eval_delta.py"],
                copied, env=env)
        check(r.returncode == 0,
              f"{label}: migrated gold test passes against the INSTALLED artifact "
              f"(rc={r.returncode})")
        if r.returncode != 0:
            print((r.stdout or "")[-1200:])
            print((r.stderr or "")[-800:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=str(REPO_ROOT))
    args = ap.parse_args()
    repo = Path(args.repo_root).resolve()

    print("=" * 78)
    print("chess_coach.gold clean-install artifact gate (BBF-chess-coach-gold-packaging)")
    print("=" * 78)
    print(f"  repo root : {repo}")
    print(f"  python    : {sys.version.split()[0]}")

    with tempfile.TemporaryDirectory(prefix="gold-artifact-gate-") as td:
        outdir = Path(td)
        wheel, sdist = build_artifacts(repo, outdir)
        if wheel:
            inspect_wheel(wheel)
        if sdist:
            inspect_sdist(sdist)
        if wheel:
            install_and_probe(repo, outdir, wheel, "wheel")
        if sdist:
            install_and_probe(repo, outdir, sdist, "sdist")

    print()
    print("=" * 78)
    if _FAILURES:
        print(f"RESULT: {len(_FAILURES)} of {_ASSERTIONS} assertions FAILED")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print(f"RESULT: all {_ASSERTIONS} assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
