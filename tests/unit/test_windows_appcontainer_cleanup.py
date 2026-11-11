"""Cleanup tests for the Windows AppContainer owned state.

**BBF-FU-20-windows-appcontainer-network-isolation.**

The application creates three pieces of state on a Windows host: the
AppContainer mapping, the parser staging tree, and the package moniker
folder. The cleanup routine must remove exactly those and **nothing
else** — in particular it must never delete a pre-existing mapping,
staging tree, or package folder that belongs to another identity or
another installation.

These tests run on every platform: the filesystem half is platform
independent, and the registry half is exercised on Windows.
"""
from __future__ import annotations

import os
import sys

import pytest

from chess_coach.pdf_ocr import windows_appcontainer as wa

# Registry path helpers, built without escape sequences.
REG = wa._APP_CONTAINER_MAPPINGS_REG
BS = chr(92)


@pytest.fixture
def product_profile():
    """The product AppContainer profile, registered and ready."""
    if not wa.profile_is_registered():
        wa.register_profile()
    package = wa.package_folder_path()
    for sub in ("AC", os.path.join("AC", "Temp"), "LocalCache"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    return wa.PRODUCT_PACKAGE_SID



# ---------------------------------------------------------------------------
# The staging tree
# ---------------------------------------------------------------------------


# The FILESYSTEM half of the cleanup (the staging tree and the package
# folder) is platform independent and is tested everywhere.  The REGISTRY
# half exists only on Windows, so those tests are gated.


def test_cleanup_removes_an_owned_staging_tree(tmp_path):
    """A staging tree carrying the ownership marker is removed."""
    poppler = tmp_path / "poppler"
    poppler.mkdir()
    (poppler / "pdftoppm.exe").write_bytes(b"stub")
    (poppler / ".chesscoach-staging").write_text("owned", encoding="utf-8")

    report = wa.cleanup_owned_state(staging=tmp_path)
    assert report.ok, report.errors
    assert not poppler.exists()
    assert any("staging:" in entry for entry in report.removed)


def test_cleanup_preserves_a_staging_tree_it_does_not_own(tmp_path):
    """A staging tree WITHOUT the ownership marker is preserved.

    This is the "another installation" case: the directory is in the
    right place but the application did not create it.
    """
    poppler = tmp_path / "poppler"
    poppler.mkdir()
    (poppler / "someone-elses.exe").write_bytes(b"not ours")

    report = wa.cleanup_owned_state(staging=tmp_path)
    assert report.ok, report.errors
    assert poppler.exists(), "a staging tree the application does not own was deleted"
    assert (poppler / "someone-elses.exe").exists()
    assert any("not owned" in entry for entry in report.preserved)


def test_cleanup_is_idempotent(tmp_path):
    """Running the cleanup twice removes nothing the second time."""
    poppler = tmp_path / "poppler"
    poppler.mkdir()
    (poppler / ".chesscoach-staging").write_text("owned", encoding="utf-8")

    first = wa.cleanup_owned_state(staging=tmp_path)
    assert first.ok, first.errors
    second = wa.cleanup_owned_state(staging=tmp_path)
    assert second.ok, second.errors
    assert not second.removed
    assert any("absent" in entry for entry in second.preserved)


def test_cleanup_reports_an_absent_staging_tree_as_preserved(tmp_path):
    """Nothing to remove is not an error."""
    report = wa.cleanup_owned_state(staging=tmp_path)
    assert report.ok, report.errors
    assert not report.removed


# ---------------------------------------------------------------------------
# The AppContainer mapping
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="the mapping key is Windows-only")
def test_cleanup_removes_the_product_mapping(product_profile):  # noqa: F811
    """The product mapping is removed when it is ours."""
    wa.invalidate_registration_cache()
    assert wa.profile_is_registered()
    report = wa.cleanup_owned_state()
    assert report.ok, report.errors
    assert not wa.profile_is_registered()
    assert any("appcontainer-mapping" in entry for entry in report.removed)


@pytest.mark.skipif(sys.platform != "win32", reason="the mapping key is Windows-only")
def test_cleanup_preserves_a_mapping_with_a_foreign_moniker():
    """A mapping under the product SID with a DIFFERENT moniker is preserved.

    This is the ownership boundary: the key matches, but the content says
    the mapping belongs to another installation.
    """
    foreign_sid = (
        "S-1-15-2-1111111111-2222222222-3333333333-4444444444-"
        "5555555555-6666666666-7777777777"
    )
    foreign_moniker = "SomeOtherApp_8wekyb3d8bbwe"
    if wa.profile_is_registered(foreign_sid):
        pytest.skip("a foreign mapping already exists on this host")
    # Register the control directly: register_profile() validates the
    # PRODUCT sid's shape, and this control deliberately uses a different
    # identity.
    for step in (
        ["add", REG + BS + foreign_sid],
        ["add", REG + BS + foreign_sid, "/v",
         "Moniker", "/t", "REG_SZ", "/d", foreign_moniker],
        ["add", REG + BS + foreign_sid + BS + "Capabilities"],
        ["add", REG + BS + foreign_sid + BS + "Children"],
    ):
        wa._run_reg(step)
    # The control mapping was created directly with reg.exe, so the
    # registration cache must be invalidated before it is consulted.
    wa.invalidate_registration_cache(foreign_sid)
    try:
        assert wa.profile_is_registered(foreign_sid)
        # The cleanup is asked to remove the PRODUCT state only. The
        # foreign mapping is keyed by a different SID, so it must survive.
        wa.cleanup_owned_state()
        assert wa.profile_is_registered(foreign_sid), (
            "the cleanup removed another identity's mapping"
        )
        # And when the cleanup IS pointed at the foreign identity but is
        # told to expect the PRODUCT moniker, the moniker mismatch
        # preserves it.
        wa.invalidate_registration_cache(foreign_sid)
        report = wa.cleanup_owned_state(
            sid_string=foreign_sid, moniker=wa.PRODUCT_PACKAGE_MONIKER,
        )
        assert report.ok, report.errors
        assert wa.profile_is_registered(foreign_sid), (
            "a mapping with a foreign moniker was removed"
        )
        assert any("moniker" in e for e in report.preserved)
    finally:
        wa._run_reg(["delete", REG + BS + foreign_sid, "/f"])


@pytest.mark.skipif(sys.platform != "win32", reason="the mapping key is Windows-only")
def test_cleanup_never_touches_another_identitys_mapping():
    """A pre-existing mapping for a different SID is never removed.

    The cleanup addresses exactly one SID. It never enumerates the
    mappings key, so a sibling installation's state is unreachable.
    """
    other_sids = [
        line.strip()
        for line in _mapping_sids()
        if line.strip() != wa.PRODUCT_PACKAGE_SID
    ]
    if not other_sids:
        pytest.skip("no pre-existing mapping to protect on this host")
    before = set(other_sids)
    wa.cleanup_owned_state()
    after = set(_mapping_sids()) & before
    assert after == before, "the cleanup removed another identity's mapping"


def _mapping_sids() -> list[str]:
    """The SIDs currently registered in the per-user mappings key."""

    rc, out, _ = wa._run_reg(["query", wa._APP_CONTAINER_MAPPINGS_REG])
    if rc != 0:
        return []
    return [
        line.strip()
        for line in out.splitlines()
        if line.strip().startswith("S-1-15-2-")
    ]


# ---------------------------------------------------------------------------
# The package folder
# ---------------------------------------------------------------------------


def test_cleanup_preserves_the_package_folder_when_requested(tmp_path, monkeypatch):
    """The package folder can be retained on request."""
    package = tmp_path / "Packages" / wa.PRODUCT_PACKAGE_MONIKER
    package.mkdir(parents=True)
    monkeypatch.setattr(wa, "package_folder_path", lambda moniker=None: package)
    report = wa.cleanup_owned_state(staging=tmp_path, remove_package_folder=False)
    assert report.ok, report.errors
    assert package.exists()
    assert any("retained by request" in entry for entry in report.preserved)


def test_cleanup_removes_the_package_folder(tmp_path, monkeypatch):
    """The package moniker folder is removed when it is ours."""
    package = tmp_path / "Packages" / wa.PRODUCT_PACKAGE_MONIKER
    package.mkdir(parents=True)
    (package / "AC").mkdir()
    monkeypatch.setattr(wa, "package_folder_path", lambda moniker=None: package)
    report = wa.cleanup_owned_state(staging=tmp_path)
    assert report.ok, report.errors
    assert not package.exists()
    assert any("package-folder" in entry for entry in report.removed)


def test_cleanup_only_removes_the_product_package_folder(tmp_path, monkeypatch):
    """A sibling package folder is never removed."""
    packages = tmp_path / "Packages"
    ours = packages / wa.PRODUCT_PACKAGE_MONIKER
    theirs = packages / "SomeOtherApp_8wekyb3d8bbwe"
    ours.mkdir(parents=True)
    theirs.mkdir(parents=True)
    monkeypatch.setattr(wa, "package_folder_path", lambda moniker=None: ours)
    report = wa.cleanup_owned_state(staging=tmp_path)
    assert report.ok, report.errors
    assert not ours.exists()
    assert theirs.exists(), "a sibling package folder was deleted"


# ---------------------------------------------------------------------------
# The staging marker
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="staging the parser is a Windows mechanism",
)
def test_staging_marks_the_directory_as_owned(tmp_path, monkeypatch):
    """A staged parser directory carries the ownership marker."""

    source = tmp_path / "source"
    source.mkdir()
    (source / ("pdftoppm.exe" if os.name == "nt" else "pdftoppm")).write_bytes(b"stub")
    target = tmp_path / "staged"
    staged = wa.stage_parser(source_dir=source, staging=target)
    assert staged.executable.exists()
    marker = target / ".chesscoach-staging"
    assert marker.exists(), "the staged directory carries no ownership marker"
    assert "Chess Coach" in marker.read_text(encoding="utf-8")


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="staging the parser is a Windows mechanism",
)
def test_staging_is_idempotent(tmp_path):
    """Staging twice reuses the already-staged tree."""

    source = tmp_path / "source"
    source.mkdir()
    (source / ("pdftoppm.exe" if os.name == "nt" else "pdftoppm")).write_bytes(b"stub")
    target = tmp_path / "staged"
    first = wa.stage_parser(source_dir=source, staging=target)
    second = wa.stage_parser(source_dir=source, staging=target)
    assert first.executable == second.executable
    assert first.executable.exists()


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="staging the parser is a Windows mechanism",
)
def test_staging_reports_a_missing_parser(tmp_path):
    """A missing parser is an unsupported-backend error, not a setup error.

    The distinction matters: "the tool is not installed" is a refusal
    (501), while "the tool is installed but could not be staged" is a
    setup failure (500).
    """
    with pytest.raises(wa.AppContainerUnsupportedError):
        wa.stage_parser(source_dir=tmp_path / "nothing-here", staging=tmp_path / "out")
