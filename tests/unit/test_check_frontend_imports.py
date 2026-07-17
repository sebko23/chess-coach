"""Tests for BBF-67 static-import scanner.

The scanner reads apps/desktop/src/ for usage patterns and verifies
the corresponding npm package is declared in apps/desktop/package.json.
"""
import json
import textwrap
from pathlib import Path
import pytest

from scripts.dev.check_frontend_imports import (
    find_usage_patterns,
    expected_packages_for_pattern,
    scan_package_json,
    check_imports,
)


def test_find_usage_patterns_detects_useform(tmp_path):
    """The scanner should find `useForm` usages in TSX files."""
    src = tmp_path / "src"
    src.mkdir()
    f = src / "AddEngine.tsx"
    f.write_text('import { useForm } from "@mantine/form";\n')
    usages = find_usage_patterns([src])
    assert any(u.pattern == "useForm" and u.file.name == "AddEngine.tsx"
               for u in usages)


def test_expected_packages_for_useform():
    """The useForm pattern -> @mantine/form mapping."""
    pkgs = expected_packages_for_pattern("useForm")
    assert "@mantine/form" in pkgs


def test_scan_package_json_parses_declared_deps(tmp_path):
    """scan_package_json returns a set of declared package names."""
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({
        "name": "test",
        "dependencies": {"@mantine/form": "^8.0.0"},
        "devDependencies": {"typescript": "^5.0.0"},
    }))
    declared = scan_package_json(pkg)
    assert "@mantine/form" in declared
    assert "typescript" in declared
    assert "@mantine/core" not in declared


def test_check_imports_warns_when_package_missing(tmp_path, capsys):
    """When useForm is used but @mantine/form is NOT in package.json,
    check_imports prints a WARNING and returns False."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "AddEngine.tsx").write_text(
        'import { useForm } from "@mantine/form";\n'
    )
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({
        "name": "test",
        "dependencies": {"react": "^18.0.0"},  # @mantine/form missing
    }))
    ok = check_imports(src_root=src, package_json=pkg)
    captured = capsys.readouterr()
    assert not ok
    assert "@mantine/form" in captured.out or "WARNING" in captured.out