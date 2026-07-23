"""Static-import scanner for apps/desktop/src/.

Greps the frontend source for usage patterns of frontend-library APIs
(e.g. useForm from @mantine/form, UploadFile from @tauri-apps/plugin-dialog)
and verifies the corresponding npm package is declared in
apps/desktop/package.json.

Advisory by default: prints a WARNING summary and exits 0 if any packages
are missing. Future BBF can flip this to exit 1 once the codebase is known
clean. See CONTRIBUTING.md.

Usage:
    python3 scripts/dev/check_frontend_imports.py

Exit codes:
    0 - all usages match declared packages (current advisory behavior)
    1 - internal scanner error (e.g. package.json not found)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# The pattern table. Each pattern is matched as a bareword in TSX/TS code
# (e.g. "useForm" in `import { useForm }`). The expected packages are the
# npm packages that EXPORT that symbol.
PATTERN_TABLE: dict[str, list[str]] = {
    # Mantine form
    "useForm": ["@mantine/form"],
    "useFormContext": ["@mantine/form"],
    "Form": ["@mantine/form", "@mantine/core"],  # ambiguous: Form is in both
    "MantineProvider": ["@mantine/core"],
    "Notifications": ["@mantine/notifications"],
    "DatePicker": ["@mantine/dates"],
    "Calendar": ["@mantine/dates"],
    # Tauri
    "open": ["@tauri-apps/plugin-dialog"],
    "save": ["@tauri-apps/plugin-dialog"],
    "openUrl": ["@tauri-apps/plugin-opener"],
    "revealItemInDir": ["@tauri-apps/plugin-opener"],
    "fetch": ["@tauri-apps/plugin-http"],
    "http": ["@tauri-apps/plugin-http"],
    "Command": ["@tauri-apps/plugin-cli"],
    # Tiptap
    "useEditor": ["@tiptap/react"],
    "EditorContent": ["@tiptap/react"],
    "StarterKit": ["@tiptap/starter-kit"],
    "Link": ["@tiptap/extension-link"],
    "Placeholder": ["@tiptap/extension-placeholder"],
    "Underline": ["@tiptap/extension-underline"],
    # Other
    "Chessground": ["@lichess-org/chessground"],
}


@dataclass(frozen=True)
class Usage:
    pattern: str
    file: Path
    line: int


def find_usage_patterns(src_roots: list[Path]) -> list[Usage]:
    """Grep .tsx/.ts files for usage of patterns in PATTERN_TABLE.

    A "usage" is an identifier reference -- either an import, a JSX tag,
    or a function call. We approximate this with a regex that matches the
    bareword on a line. False positives are possible (e.g. a comment
    mentioning `useForm`) but the scanner is advisory so it's fine.
    """
    usages: list[Usage] = []
    pat_re = re.compile(r"\b(" + "|".join(re.escape(k) for k in PATTERN_TABLE) + r")\b")
    for src_root in src_roots:
        if not src_root.exists():
            continue
        for ts_file in src_root.rglob("*.tsx"):
            for n, line in enumerate(ts_file.read_text(encoding="utf-8").splitlines(), start=1):
                for m in pat_re.finditer(line):
                    usages.append(Usage(pattern=m.group(1), file=ts_file, line=n))
        for ts_file in src_root.rglob("*.ts"):
            # Skip .d.ts files (declaration files; patterns in those are abstract).
            if ts_file.name.endswith(".d.ts"):
                continue
            for n, line in enumerate(ts_file.read_text(encoding="utf-8").splitlines(), start=1):
                for m in pat_re.finditer(line):
                    usages.append(Usage(pattern=m.group(1), file=ts_file, line=n))
    return usages


def expected_packages_for_pattern(pattern: str) -> list[str]:
    """Return the list of npm packages that export this pattern."""
    return PATTERN_TABLE.get(pattern, [])


def scan_package_json(package_json_path: Path) -> set[str]:
    """Parse package.json and return the set of declared package names."""
    if not package_json_path.is_file():
        raise FileNotFoundError(f"package.json not found at {package_json_path}")
    data = json.loads(package_json_path.read_text(encoding="utf-8"))
    declared: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        declared.update(data.get(key, {}).keys())
    return declared


def check_imports(
    src_root: Path | None = None,
    package_json: Path | None = None,
    apps_root: Path | None = None,
) -> bool:
    """Run the full check.

    Args:
        src_root: where to grep for patterns. Default: <apps_root>/src
        package_json: package.json to verify against. Default: <apps_root>/package.json
        apps_root: root of the apps/desktop/ directory. Default: relative to repo.

    Returns True if all usages are covered; False otherwise.
    Prints a summary to stdout regardless.
    """
    if apps_root is None:
        apps_root = Path(__file__).resolve().parents[2] / "apps" / "desktop"
    if src_root is None:
        src_root = apps_root / "src"
    if package_json is None:
        package_json = apps_root / "package.json"

    usages = find_usage_patterns([src_root])
    declared = scan_package_json(package_json)
    missing: set[str] = set()
    used_packages: set[str] = set()
    for u in usages:
        for pkg in expected_packages_for_pattern(u.pattern):
            used_packages.add(pkg)
            if pkg not in declared:
                missing.add(pkg)
    if not missing:
        print(f"OK: all {len(usages)} pattern usages match declared packages "
              f"({len(used_packages)} distinct).")
        return True
    print(f"WARNING: {len(missing)} npm package(s) used in {src_root} "
          f"but NOT declared in {package_json}:")
    for pkg in sorted(missing):
        print(f"  - {pkg}")
    return False


if __name__ == "__main__":
    try:
        ok = check_imports()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0 if ok else 0)  # advisory mode: always exit 0 for now
