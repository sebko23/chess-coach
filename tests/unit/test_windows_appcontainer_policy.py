"""Platform-independent unit tests for the AppContainer policy module.

**BBF-FU-20-windows-appcontainer-network-isolation.**

These exercise the parts of :mod:`chess_coach.pdf_ocr.windows_appcontainer`
that do NOT touch Win32: the SID-shape validators, the capability
selection, the handle policy, the launch-plan construction, and the
platform gate. They run on every platform, which is what keeps the
Windows-only module from dragging the cross-platform coverage floor down.

The Win32 behaviour (the token reads, the launch, the registry
registration) is proven by the real-Windows suite in
``tests/windows/test_windows_appcontainer_enforcement.py``.
"""
from __future__ import annotations

import sys

import pytest

from chess_coach.pdf_ocr import windows_appcontainer as wa

# ---------------------------------------------------------------------------
# The platform gate
# ---------------------------------------------------------------------------


def test_the_backend_is_windows_only():
    """The AppContainer backend is a Windows mechanism."""
    assert wa.APPCONTAINER_SUPPORTED is (sys.platform == "win32")


def test_the_platform_gate_raises_off_windows(monkeypatch):
    """Off Windows the gate raises rather than pretending to work."""
    monkeypatch.setattr(wa, "APPCONTAINER_SUPPORTED", False)
    with pytest.raises(wa.AppContainerUnsupportedError):
        wa._require_windows()


# ---------------------------------------------------------------------------
# SID-shape validation
# ---------------------------------------------------------------------------


def test_the_product_sid_has_the_documented_shape():
    """The constant is an S-1-15-2 SID with seven product subauthorities."""
    subs = wa.validate_product_sid()
    assert len(subs) == 7
    assert subs == wa.PRODUCT_PACKAGE_SUBAUTHORITIES
    assert wa.PRODUCT_PACKAGE_SID == (
        "S-1-15-2-1307264423-3961844790-1637159078-741858669-3028905837-"
        "1642583832-2140039969"
    )


def test_the_product_sid_is_the_documented_sha256_derivation():
    """The derivation reproduces the constant exactly."""
    import hashlib
    import struct

    digest = hashlib.sha256(wa.PRODUCT_PACKAGE_NAME.encode("utf-8")).digest()
    words = struct.unpack(">7I", digest[:28])
    assert "S-1-15-2-" + "-".join(str(w) for w in words) == wa.PRODUCT_PACKAGE_SID


@pytest.mark.parametrize(
    "bad",
    [
        "S-1-5-21-1-2-3-1001",
        "S-1-15-3-1",
        "S-1-15-2-1-2-3",
        "S-1-15-2-1-2-3-4-5-6-7-8-9-10-11",
        "S-1-15-2-1-2-3-4-5-6-7-notanumber",
        "S-1-15-3-1-2-3-4-5-6-7-8-9",
    ],
)
def test_a_malformed_product_sid_is_a_setup_error(bad):
    """A malformed SID never falls back to another identity."""
    with pytest.raises(wa.AppContainerSetupError):
        wa.validate_product_sid(bad)


def test_validate_application_package_sid_accepts_any_application_package():
    """The looser validator accepts any S-1-15-2 SID."""
    wa.validate_application_package_sid(
        "S-1-15-2-1111111111-2222222222-3333333333-4444444444-"
        "5555555555-6666666666-7777777777"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "S-1-5-21-1-2-3-1001",
        "S-1-15-3-1",
        "S-1-15-2-1-2-3-notanumber",
    ],
)
def test_validate_application_package_sid_rejects_other_authorities(bad):
    """A non-application-package SID is rejected."""
    with pytest.raises(wa.AppContainerSetupError):
        wa.validate_application_package_sid(bad)


def test_sid_to_string_of_a_null_pointer_is_none():
    """A null SID renders as None rather than raising."""
    assert wa.sid_to_string(None) is None
    assert wa.sid_to_string(0) is None


# ---------------------------------------------------------------------------
# Capability selection
# ---------------------------------------------------------------------------


def test_the_production_capability_set_is_empty():
    """The parser must never hold a network capability."""
    caps = wa.select_capabilities()
    assert caps.sids == ()
    assert not caps.is_network_capable


def test_a_capability_set_with_a_non_capability_sid_is_refused():
    """Only SIDs under the capability authority are capabilities."""
    with pytest.raises(wa.AppContainerSetupError):
        wa.CapabilitySet(sids=("S-1-15-2-1307264423",))


def test_the_internet_client_capability_can_never_be_granted():
    """`internetClient` is refused at construction time."""
    with pytest.raises(wa.AppContainerSetupError):
        wa.CapabilitySet(sids=(wa.INTERNET_CLIENT_CAPABILITY_SID,))


def test_the_capability_authority_prefix_is_the_documented_one():
    """The capability authority is S-1-15-3."""
    assert wa.CAPABILITY_AUTHORITY_PREFIX == "S-1-15-3-"
    assert wa.INTERNET_CLIENT_CAPABILITY_SID == "S-1-15-3-1"


# ---------------------------------------------------------------------------
# The handle policy
# ---------------------------------------------------------------------------


def test_the_production_policy_uses_inherit_handles_true():
    """The production launch shape requires bInheritHandles=TRUE."""
    assert wa.DEFAULT_HANDLE_POLICY.inherit_handles is True
    assert wa.DEFAULT_HANDLE_POLICY.use_explicit_allowlist is True


def test_the_allowlist_contains_only_stdout_and_stderr():
    """No other handle -- in particular no socket -- is ever permitted."""
    permitted = wa.DEFAULT_HANDLE_POLICY.permitted_handles(stdout=10, stderr=20)
    assert permitted == [10, 20]


def test_the_allowlist_omits_absent_handles():
    """A handle that was not opened is not in the allowlist."""
    policy = wa.DEFAULT_HANDLE_POLICY
    assert policy.permitted_handles(stdout=None, stderr=20) == [20]
    assert policy.permitted_handles(stdout=10, stderr=None) == [10]


def test_the_allowlist_is_never_empty_in_production():
    """The production policy always names both standard handles.

    An EMPTY allowlist is indistinguishable, to the attribute-list
    builder, from "no allowlist requested" -- and omitting the attribute
    while bInheritHandles stays TRUE lets every inheritable handle cross
    into the child.  The production policy must therefore never produce an
    empty allowlist, which is why the launch fails closed instead.
    """
    policy = wa.DEFAULT_HANDLE_POLICY
    assert policy.permitted_handles(stdout=1, stderr=2) != []


def test_a_policy_without_inherit_handles_is_refused():
    """bInheritHandles=FALSE cannot carry an explicit allowlist."""
    with pytest.raises(wa.AppContainerSetupError):
        wa.HandlePolicy(inherit_handles=False)


def test_the_bypass_shape_returns_no_handles():
    """The bypass shape (no allowlist) permits nothing, by design.

    It is used ONLY in the bypass-demonstration positive control, where
    the absence of the allowlist is the point.
    """
    bypass = wa.HandlePolicy(use_explicit_allowlist=False)
    assert bypass.permitted_handles(stdout=10, stderr=20) == []


# ---------------------------------------------------------------------------
# The launch plan
# ---------------------------------------------------------------------------


def test_the_launch_plan_uses_the_product_identity():
    """The plan carries the product SID and the zero-capability set."""
    if sys.platform != "win32":
        pytest.skip("the launch plan is a Windows mechanism")
    plan = wa.build_launch_plan()
    assert plan.package_sid == wa.PRODUCT_PACKAGE_SID
    assert plan.capabilities.sids == ()
    assert plan.handle_policy is wa.DEFAULT_HANDLE_POLICY


def test_the_launch_plan_refuses_a_network_capable_set():
    """A network-capable capability set is refused before any launch."""
    if sys.platform != "win32":
        pytest.skip("the launch plan is a Windows mechanism")
    caps = wa.CapabilitySet(sids=("S-1-15-3-3",))
    with pytest.raises(wa.AppContainerSetupError):
        wa.build_launch_plan(capabilities=caps)


def test_the_launch_plan_refuses_a_malformed_product_sid(monkeypatch):
    """A malformed product SID is refused.

    The constant is patched to a non-application-package SID.  The plan
    builder resolves the constant at CALL time, so the malformed value is
    what gets validated -- and it is refused.
    """
    monkeypatch.setattr(wa, "PRODUCT_PACKAGE_SID", "S-1-5-21-1-2-3-1001")
    with pytest.raises((wa.AppContainerSetupError, wa.AppContainerUnsupportedError)):
        wa.build_launch_plan()


def test_the_launch_plan_refuses_an_explicitly_malformed_sid():
    """An explicitly supplied malformed SID is refused."""
    with pytest.raises((wa.AppContainerSetupError, wa.AppContainerUnsupportedError)):
        wa.build_launch_plan(package_sid="S-1-5-21-1-2-3-1001")


# ---------------------------------------------------------------------------
# The cleanup report
# ---------------------------------------------------------------------------


def test_a_clean_cleanup_report_is_ok():
    """A report with no errors is OK."""
    assert wa.CleanupReport().ok
    assert not wa.CleanupReport(errors=("boom",)).ok


def test_the_cleanup_report_separates_removed_from_preserved():
    """The report distinguishes what was removed from what was kept."""
    report = wa.CleanupReport(
        removed=("a",), preserved=("b",), errors=(),
    )
    assert report.removed == ("a",)
    assert report.preserved == ("b",)
    assert report.ok


# ---------------------------------------------------------------------------
# The registration cache
# ---------------------------------------------------------------------------


def test_the_registration_cache_can_be_invalidated():
    """The cached registration check is forgettable."""
    wa._REGISTRATION_CACHE["S-1-15-2-test"] = True
    wa.invalidate_registration_cache("S-1-15-2-test")
    assert "S-1-15-2-test" not in wa._REGISTRATION_CACHE


def test_invalidating_the_whole_cache_clears_it():
    """Invalidating without a SID clears every entry."""
    wa._REGISTRATION_CACHE["S-1-15-2-a"] = True
    wa._REGISTRATION_CACHE["S-1-15-2-b"] = True
    wa.invalidate_registration_cache()
    assert not wa._REGISTRATION_CACHE


# ---------------------------------------------------------------------------
# The staging root
# ---------------------------------------------------------------------------


def test_the_staging_root_is_outside_the_user_profile():
    """A profile-resident parser is unlaunchable inside the container."""
    import os

    root = wa.staging_root()
    user_profile = os.environ.get("USERPROFILE", "")
    if user_profile:
        assert not str(root).lower().startswith(user_profile.lower())


def test_the_staging_root_honours_the_override(monkeypatch, tmp_path):
    """The staging root can be redirected (CI does this)."""
    monkeypatch.setenv(wa.ENV_STAGING_ROOT, str(tmp_path))
    assert wa.staging_root() == tmp_path
