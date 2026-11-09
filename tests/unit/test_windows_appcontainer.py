"""Unit tests for the Windows AppContainer identity and handle policy.

**BBF-FU-20-windows-appcontainer-network-isolation.**

These tests are pure policy checks: they run on every platform and assert
the *contract* the AppContainer backend implements -- the product-owned
package identity, the zero-capability rule, the inherited-handle
allowlist, the fail-closed decisions, and the error taxonomy.

The behavioural proof (that a real AppContainer token really is denied
the network, and that the allowlist really excludes a live inherited
socket) lives in ``tests/windows/test_windows_appcontainer_enforcement.py``
and runs on a real Windows host.

No test here mocks a Win32 API to *create* the property being asserted;
they assert the decisions the production code makes.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from chess_coach.pdf_ocr import subprocess_runner as sr
from chess_coach.pdf_ocr import windows_appcontainer as wa

# ---------------------------------------------------------------------------
# The product-owned package identity
# ---------------------------------------------------------------------------


def test_product_sid_is_an_application_package_sid():
    """The constant is an S-1-15-2 SID with seven product subauthorities."""
    subs = wa.validate_product_sid()
    assert len(subs) == 7
    assert subs == wa.PRODUCT_PACKAGE_SUBAUTHORITIES
    assert wa.PRODUCT_PACKAGE_SID.startswith("S-1-15-2-")


def test_product_sid_is_decimal_not_hex():
    """AppContainer package subauthorities are decimal.

    A hex-formatted variant is rejected by ``ConvertStringSidToSidW`` with
    ``ERROR_INVALID_SID`` (1337), so this is a real failure mode and not a
    cosmetic one.
    """
    parts = wa.PRODUCT_PACKAGE_SID.split("-")
    assert len(parts) == 11
    for part in parts[4:]:
        assert part.isdigit(), f"{part!r} is not a decimal subauthority"
        assert 0 <= int(part) <= 0xFFFFFFFF


def test_product_sid_is_derived_from_the_package_name():
    """The documented SHA-256 derivation reproduces the constant.

    The derivation is the SHA-256 of the package name, taken as the first
    28 bytes (seven big-endian 32-bit groups) and rendered in decimal.
    """
    import hashlib
    import struct

    digest = hashlib.sha256(wa.PRODUCT_PACKAGE_NAME.encode("utf-8")).digest()
    words = struct.unpack(">7I", digest[:28])
    expected = "S-1-15-2-" + "-".join(str(w) for w in words)
    assert expected == wa.PRODUCT_PACKAGE_SID


def test_product_sid_is_not_a_borrowed_store_identity():
    """The product SID must not be one of the host's pre-existing mappings.

    The feasibility phase had to borrow a Store package SID because the
    OS would not create a new profile. Production must own its identity,
    so the constant must not collide with an installed package.
    """
    mapping_key = (
        r"HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows"
        r"\CurrentVersion\AppContainer\Mappings"
    )
    import subprocess

    try:
        proc = subprocess.run(
            ["reg", "query", mapping_key],
            capture_output=True, text=True, errors="replace", timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("reg.exe is unavailable on this host")
    if proc.returncode != 0:
        pytest.skip("the AppContainer mappings key is unavailable on this host")
    borrowed = {
        line.strip()
        for line in (proc.stdout or "").splitlines()
        if line.strip().startswith("S-1-15-2-")
    }
    assert wa.PRODUCT_PACKAGE_SID not in borrowed


@pytest.mark.parametrize(
    "bad",
    [
        "S-1-5-21-1-2-3-1001",              # not an application-package SID
        "S-1-15-3-1",                        # a capability SID
        "S-1-15-2-1-2-3",                    # too few subauthorities
        "S-1-15-2-1-2-3-4-5-6-7-8-9-10-11",   # too many subauthorities
        "S-1-15-2-1-2-3-4-5-6-7-notanumber",  # non-numeric
    ],
)
def test_validate_product_sid_rejects_malformed_sids(bad):
    """A malformed SID is a setup error, never a silent fallback."""
    with pytest.raises(wa.AppContainerSetupError):
        wa.validate_product_sid(bad)


# ---------------------------------------------------------------------------
# Capability selection
# ---------------------------------------------------------------------------


def test_production_capability_set_is_empty():
    """The parser must never hold any network capability."""
    caps = wa.select_capabilities()
    assert caps.sids == ()
    assert not caps.is_network_capable


def test_capability_set_rejects_the_internet_client_capability():
    """``internetClient`` can never be granted to the parser."""
    with pytest.raises(wa.AppContainerSetupError):
        wa.CapabilitySet(sids=(wa.INTERNET_CLIENT_CAPABILITY_SID,))


def test_capability_set_rejects_a_non_capability_sid():
    """Only SIDs under the capability authority are capabilities."""
    with pytest.raises(wa.AppContainerSetupError):
        wa.CapabilitySet(sids=("S-1-15-2-1307264423",))


def test_launch_plan_refuses_a_network_capable_set():
    """A network-capable plan is refused before any process is created."""
    caps = wa.CapabilitySet(sids=("S-1-15-3-3",))  # a non-internet capability
    with pytest.raises(wa.AppContainerSetupError):
        wa.build_launch_plan(capabilities=caps)


# ---------------------------------------------------------------------------
# The inherited-handle policy
# ---------------------------------------------------------------------------


def test_handle_policy_requires_inherit_handles_true():
    """``bInheritHandles=FALSE`` cannot carry an explicit allowlist.

    Measured: with a handle list and ``bInheritHandles=FALSE``,
    ``CreateProcessW`` fails with ``ERROR_INVALID_PARAMETER`` (87).
    """
    with pytest.raises(wa.AppContainerSetupError):
        wa.HandlePolicy(inherit_handles=False)


def test_handle_policy_permits_only_stdout_and_stderr():
    """The allowlist contains the standard handles and nothing else."""
    policy = wa.DEFAULT_HANDLE_POLICY
    permitted = policy.permitted_handles(stdout=100, stderr=200)
    assert permitted == [100, 200]
    # A socket handle value is never permitted.
    assert 300 not in permitted


def test_handle_policy_omits_absent_handles():
    """A handle that was not opened is not in the allowlist."""
    policy = wa.DEFAULT_HANDLE_POLICY
    assert policy.permitted_handles(stdout=None, stderr=200) == [200]
    assert policy.permitted_handles(stdout=100, stderr=None) == [100]
    assert policy.permitted_handles(stdout=None, stderr=None) == []


def test_handle_policy_is_never_the_empty_allowlist():
    """The empty allowlist was measured not to work and is not the policy.

    The production policy always names stdout and stderr, so the
    allowlist is never empty.
    """
    policy = wa.DEFAULT_HANDLE_POLICY
    assert policy.permitted_handles(stdout=1, stderr=2) != []


# ---------------------------------------------------------------------------
# Fail-closed decisions
# ---------------------------------------------------------------------------


def test_appcontainer_setup_error_is_distinct_from_unsupported():
    """A setup failure and an unsupported backend are different outcomes.

    The route maps them to 500 and 501 respectively, so they must not be
    the same class.
    """
    assert issubclass(wa.AppContainerSetupError, wa.AppContainerError)
    assert issubclass(wa.AppContainerUnsupportedError, wa.AppContainerError)
    assert not issubclass(wa.AppContainerSetupError, wa.AppContainerUnsupportedError)
    assert not issubclass(wa.AppContainerUnsupportedError, wa.AppContainerSetupError)


def test_verification_error_is_a_setup_error():
    """A token mismatch fails closed in the setup category."""
    assert issubclass(wa.AppContainerVerificationError, wa.AppContainerSetupError)


def test_assert_verified_raises_with_the_reasons():
    """A failed verification names every reason it failed."""
    verification = wa.TokenVerification(
        is_app_container=False,
        app_container_sid="S-1-15-2-1",
        capability_sids=("S-1-15-3-1",),
        group_sids=("S-1-15-3-1",),
        internet_client_present=True,
        errors=["not an app container", "wrong sid", "holds internetClient"],
    )
    with pytest.raises(wa.AppContainerVerificationError) as excinfo:
        wa.assert_verified(verification)
    details = excinfo.value.details
    assert len(details["errors"]) == 3
    assert details["internet_client_present"] is True


def test_assert_verified_accepts_a_clean_verification():
    """A clean verification passes."""
    wa.assert_verified(wa.TokenVerification(is_app_container=True))


# ---------------------------------------------------------------------------
# The Windows opt-in gate
# ---------------------------------------------------------------------------


def test_windows_refusal_is_preserved_when_the_flag_is_off(monkeypatch):
    """With the opt-in off, Windows PDF parsing is still refused.

    This is the retained 501 refusal. It must not be weakened by the
    existence of the AppContainer backend.
    """
    monkeypatch.delenv(sr.ENV_WINDOWS_APPCONTAINER, raising=False)
    monkeypatch.setattr(sr, "HOST_PLATFORM", "win32")
    assert sr.windows_appcontainer_is_enabled() is False
    assert sr._network_isolation_available() is False
    with pytest.raises(sr.NetworkIsolationUnsupportedError):
        sr.ensure_network_isolation_supported()


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_windows_opt_in_accepts_truthy_values(monkeypatch, value):
    """The opt-in flag accepts the usual truthy spellings."""
    monkeypatch.setattr(sr, "HOST_PLATFORM", "win32")
    monkeypatch.setenv(sr.ENV_WINDOWS_APPCONTAINER, value)
    assert sr.windows_appcontainer_is_enabled() is True
    assert sr._network_isolation_available() is True
    # The guard no longer refuses.
    sr.ensure_network_isolation_supported()


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  "])
def test_windows_opt_in_rejects_falsy_values(monkeypatch, value):
    """Anything that is not truthy leaves the refusal in place."""
    monkeypatch.setattr(sr, "HOST_PLATFORM", "win32")
    monkeypatch.setenv(sr.ENV_WINDOWS_APPCONTAINER, value)
    assert sr.windows_appcontainer_is_enabled() is False


def test_linux_isolation_is_unaffected_by_the_windows_flag(monkeypatch):
    """The Linux namespace boundary is always available."""
    monkeypatch.setattr(sr, "HOST_PLATFORM", "linux")
    monkeypatch.delenv(sr.ENV_WINDOWS_APPCONTAINER, raising=False)
    assert sr._network_isolation_available() is True
    assert "namespace" in sr.network_isolation_mechanism()
    sr.ensure_network_isolation_supported()


def test_the_opt_in_is_evaluated_at_call_time(monkeypatch):
    """The gate reads the environment on every call, not at import time."""
    monkeypatch.setattr(sr, "HOST_PLATFORM", "win32")
    monkeypatch.delenv(sr.ENV_WINDOWS_APPCONTAINER, raising=False)
    assert sr._network_isolation_available() is False
    monkeypatch.setenv(sr.ENV_WINDOWS_APPCONTAINER, "1")
    assert sr._network_isolation_available() is True


# ---------------------------------------------------------------------------
# The pdftoppm argument shape
# ---------------------------------------------------------------------------


def test_pdftoppm_reads_stdin_when_no_input_path_is_given():
    """The Linux path still reads the PDF from stdin."""
    args = sr._build_pdftoppm_args(200, 1, 0, Path("/tmp/page"))
    assert args[-2] == "-"
    assert args[-1] == str(Path("/tmp/page"))


def test_pdftoppm_takes_a_file_path_when_one_is_given():
    """The Windows AppContainer path passes the PDF by file path."""
    args = sr._build_pdftoppm_args(
        200, 1, 0, Path("/tmp/page"), input_path=Path("/tmp/input.pdf"),
    )
    assert args[-2] == str(Path("/tmp/input.pdf"))
    assert "-" not in args


def test_pdftoppm_argument_order_is_preserved():
    """The existing argument ordering is unchanged."""
    args = sr._build_pdftoppm_args(
        150, 2, 5, Path("/tmp/page"), input_path=Path("/tmp/in.pdf"),
    )
    assert args[0] == "pdftoppm"
    assert args[1:2] == ["-r"]
    assert args[2] == "150"
    assert args[3] == "-png"
    assert args[4:6] == ["-f", "2"]
    assert args[6:8] == ["-l", "5"]


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------


def test_staging_root_is_outside_the_user_profile():
    """A profile-resident parser is unlaunchable inside the container."""
    root = wa.staging_root()
    user_profile = os.environ.get("USERPROFILE", "")
    if user_profile:
        assert str(root).lower().startswith(user_profile.lower()) is False


def test_staging_root_can_be_overridden(monkeypatch, tmp_path):
    """CI can point the staging at a directory it controls."""
    monkeypatch.setenv(wa.ENV_STAGING_ROOT, str(tmp_path))
    assert wa.staging_root() == tmp_path
