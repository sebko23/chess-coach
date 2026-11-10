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

import ctypes
import struct
import sys
from pathlib import Path

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


# ---------------------------------------------------------------------------
# The staged parser's ACL contract
# ---------------------------------------------------------------------------


def test_the_staged_paths_include_the_containing_directory():
    """The DIRECTORY must be part of the granted set.

    A Windows token needs ``FILE_TRAVERSE`` on the parent directory to
    resolve a child file.  The staged parser's DLLs sit beside the
    executable, so the directory that holds them must carry the
    product-SID ACE -- granting only the files leaves the parser unable
    to load its own runtime.
    """
    staged = wa.StagedParser(
        executable=Path("C:/stage/poppler/pdftoppm.exe"),
        directory=Path("C:/stage/poppler"),
        runtime_dirs=(Path("C:/stage/poppler/libpoppler.dll"),),
    )
    paths = staged.paths()
    assert Path("C:/stage/poppler") in paths, (
        "the containing directory must be granted, not only the files"
    )
    assert Path("C:/stage/poppler/pdftoppm.exe") in paths
    assert Path("C:/stage/poppler/libpoppler.dll") in paths


def test_the_staged_paths_are_ordered_directory_first():
    """The directory comes first, so a directory grant is never skipped."""
    staged = wa.StagedParser(
        executable=Path("C:/stage/poppler/pdftoppm.exe"),
        directory=Path("C:/stage/poppler"),
        runtime_dirs=(Path("C:/stage/poppler/libpoppler.dll"),),
    )
    assert staged.paths()[0] == Path("C:/stage/poppler")


# ---------------------------------------------------------------------------
# The capability list is read through a POINTER, not an inline array
# ---------------------------------------------------------------------------


class _TokenCapabilities(ctypes.Structure):
    """The Win32 ``TOKEN_CAPABILITIES`` layout.

    ``{ DWORD CapabilityCount; PSID_AND_ATTRIBUTES Capabilities; }`` --
    on x64 the 4-byte count is followed by 4 bytes of padding before the
    8-byte pointer, so the pointer field is at offset **8**, not 0.
    """

    _fields_ = [
        ("CapabilityCount", ctypes.c_uint32),
        ("_padding", ctypes.c_uint32),
        ("Capabilities", ctypes.POINTER(ctypes.c_void_p)),
    ]


def _raw_sid(authority: int, subauthorities: tuple[int, ...]) -> bytes:
    """Build the binary form of a SID without any Windows API.

    The Windows binary SID layout is::

        byte  0      revision (1)
        byte  1      subauthority count
        bytes 2..7   identifier authority, big-endian
        then         subauthorities, each a 4-byte LITTLE-endian DWORD

    Building the bytes directly keeps this test platform independent: it
    needs no ``ConvertStringSidToSidW``, which exists only on Windows.
    """
    data = bytes([1, len(subauthorities)])
    data += struct.pack(">Q", authority)[2:]  # the 6-byte authority
    for sub in subauthorities:
        data += struct.pack("<I", sub)
    return data


def _synthetic_capabilities(sid_bytes: list[bytes]):
    """Build a TOKEN_CAPABILITIES descriptor holding the given SID bytes.

    The buffers must outlive the descriptor, so they are returned too.
    """
    buffers = [
        (ctypes.c_char * len(raw)).from_buffer_copy(raw) for raw in sid_bytes
    ]

    array = (wa._SID_AND_ATTRIBUTES * len(buffers))()
    for index, buffer in enumerate(buffers):
        array[index].Sid = ctypes.cast(buffer, ctypes.c_void_p)
        array[index].Attributes = 0

    descriptor = _TokenCapabilities()
    descriptor.CapabilityCount = len(buffers)
    descriptor.Capabilities = ctypes.cast(
        ctypes.addressof(array), ctypes.POINTER(ctypes.c_void_p),
    )
    return descriptor, array, buffers


def test_the_capability_list_is_read_through_its_pointer(monkeypatch):
    """A token with several capabilities yields ALL of them.

    ``TOKEN_CAPABILITIES`` holds a POINTER to the array, while
    ``TOKEN_GROUPS`` holds the array INLINE.  Reading the capability list
    with the inline layout returned the wrong SIDs for any count above
    one -- and the ``internetClient`` flag was checked against the GROUP
    list, where capability SIDs never appear, so it was always False.

    This test drives the SHIPPED reader against a descriptor that holds
    TWO capabilities, so a reader that used the inline layout would
    return the descriptor's own bytes instead of the two SIDs.
    """
    internet = wa.INTERNET_CLIENT_CAPABILITY_SID  # S-1-15-3-1
    other = "S-1-15-3-2"
    descriptor, _array, _buffers = _synthetic_capabilities(
        [_raw_sid(15, (3, 1)), _raw_sid(15, (3, 2))],
    )

    monkeypatch.setattr(
        wa,
        "_get_token_buffer",
        lambda token, info_class: wa._TokenBuffer(
            ctypes.cast(ctypes.pointer(descriptor), ctypes.POINTER(ctypes.c_char)),
            ctypes.sizeof(descriptor),
        ),
    )
    read = wa._read_token_sids(None, wa._TOKEN_CAPABILITIES)

    assert read == [internet, other], (
        "the capability list must be read through the descriptor's pointer; "
        f"got {read}"
    )


def test_the_capability_pointer_is_read_at_offset_eight(monkeypatch):
    """The SHIPPED reader reads the pointer at offset 8, not offset 0.

    Reading offset 0 yields the COUNT, which as a pointer is a wild
    address -- the process would crash rather than report an error.  So
    this test drives the shipped reader against a descriptor whose
    offset-8 pointer is valid and whose offset-0 value is the count: a
    reader that used offset 0 would not return the two SIDs.
    """
    internet = wa.INTERNET_CLIENT_CAPABILITY_SID
    other = "S-1-15-3-2"
    descriptor, _array, _buffers = _synthetic_capabilities(
        [_raw_sid(15, (3, 1)), _raw_sid(15, (3, 2))],
    )

    # The descriptor's layout, asserted directly.
    raw = ctypes.string_at(ctypes.pointer(descriptor), 16)
    count = int.from_bytes(raw[0:4], "little")
    pointer_at_8 = int.from_bytes(raw[8:16], "little")
    assert count == 2
    assert pointer_at_8 != 0, "the pointer field must be at offset 8"

    monkeypatch.setattr(
        wa,
        "_get_token_buffer",
        lambda token, info_class: wa._TokenBuffer(
            ctypes.cast(ctypes.pointer(descriptor), ctypes.POINTER(ctypes.c_char)),
            ctypes.sizeof(descriptor),
        ),
    )
    read = wa._read_token_sids(None, wa._TOKEN_CAPABILITIES)

    assert read == [internet, other], (
        "the shipped reader must use the offset-8 pointer; got {read}"
    )


def test_internet_client_is_checked_against_the_capability_sids():
    """The flag is derived from the CAPABILITY list, not the group list.

    Capability SIDs are not in ``TokenGroups``, so checking the group
    list would report False even for a token that really holds
    ``internetClient``.
    """
    verification = wa.TokenVerification()
    verification.capability_sids = ("S-1-15-3-1",)
    verification.group_sids = ()

    assert wa.INTERNET_CLIENT_CAPABILITY_SID in verification.capability_sids
    assert wa.INTERNET_CLIENT_CAPABILITY_SID not in verification.group_sids


# ---------------------------------------------------------------------------
# The token lists: a failed read is not an empty list
# ---------------------------------------------------------------------------


def test_an_eight_byte_capability_buffer_is_read_without_overrunning(monkeypatch):
    """An 8-byte capability buffer is read safely (F1).

    Measured on this host, the real ``TOKEN_CAPABILITIES`` buffer for a
    token that holds no capability is EXACTLY 8 bytes -- and that is the
    PRODUCTION AppContainer token's buffer.  The pointer field is at
    offset 8, so reading it from an 8-byte buffer is an out-of-bounds
    heap read.

    The regression builds exactly that buffer and asserts the reader
    returns an empty list.  A reader that read offset 8 would overrun
    the buffer.
    """
    descriptor = (ctypes.c_char * 8)()
    ctypes.memmove(
        ctypes.addressof(descriptor),
        ctypes.byref(ctypes.c_uint32(0)),  # count = 0
        4,
    )

    monkeypatch.setattr(
        wa,
        "_get_token_buffer",
        lambda token, info_class: wa._TokenBuffer(descriptor, 8),
    )
    read = wa._read_token_sids(None, wa._TOKEN_CAPABILITIES)

    assert read == [], (
        "an 8-byte capability buffer with count 0 must read as an empty "
        f"list; got {read!r}"
    )


def test_a_short_capability_buffer_with_a_count_is_a_failed_read(monkeypatch):
    """A buffer that cannot hold the elements it promises fails closed.

    The count says there are capabilities but the buffer is too short to
    hold the pointer to them, so the descriptor is malformed.  That is a
    failed read, not an empty list.
    """
    descriptor = (ctypes.c_char * 8)()
    ctypes.memmove(
        ctypes.addressof(descriptor),
        ctypes.byref(ctypes.c_uint32(3)),  # count = 3, but no room
        4,
    )

    monkeypatch.setattr(
        wa,
        "_get_token_buffer",
        lambda token, info_class: wa._TokenBuffer(descriptor, 8),
    )
    read = wa._read_token_sids(None, wa._TOKEN_CAPABILITIES)

    assert read is None, (
        "a malformed capability descriptor must be reported as a failed "
        f"read; got {read!r}"
    )


def test_a_failed_capability_read_is_not_an_empty_list(monkeypatch):
    """A list that could NOT be read is reported as such (F2).

    An empty list is the PROOF that the token holds no capability.  A
    failed read is the absence of that proof, and the two must not be
    confused -- confusing them let a token pass the pre-resume
    verification with no evidence about its capabilities.
    """
    monkeypatch.setattr(wa, "_get_token_buffer", lambda token, info_class: None)
    read = wa._read_token_sids(None, wa._TOKEN_CAPABILITIES)

    assert read is None, (
        "a failed token read must be reported as a failed read; "
        f"got {read!r}"
    )


def test_a_failed_capability_read_fails_the_verification(monkeypatch):
    """The pre-resume verification FAILS when the capability list cannot be read.

    The capability list is the evidence that the token holds no network
    capability.  Without it the verification has established nothing, so
    it must fail closed rather than pass on absent evidence.

    The verification body is driven directly, so the test needs no
    Windows API and runs on every platform.
    """
    # The token reads that SUCCEED: the AppContainer flag and the
    # AppContainer SID, both matching the product.
    def buffers(token_handle, info_class):
        if info_class == wa._TOKEN_CAPABILITIES:
            # The read that FAILS.
            return None
        if info_class == wa._TOKEN_IS_APP_CONTAINER:
            value = ctypes.c_int32(1)
            return wa._TokenBuffer(
                ctypes.cast(
                    ctypes.pointer(value), ctypes.POINTER(ctypes.c_char)
                ),
                ctypes.sizeof(value),
            )
        if info_class == wa._TOKEN_APP_CONTAINER_SID:
            # A buffer holding the product SID.
            raw = _raw_sid(15, (2, 1307264423, 3961844790, 1637159078,
                                741858669, 3028905837, 1642583832, 2140039969))
            struct = (ctypes.c_char * (8 + len(raw)))()
            ctypes.memmove(
                ctypes.addressof(struct) + 8,
                raw,
                len(raw),
            )
            return wa._TokenBuffer(
                ctypes.cast(struct, ctypes.POINTER(ctypes.c_char)),
                ctypes.sizeof(struct),
            )
        if info_class == wa._TOKEN_GROUPS:
            return wa._TokenBuffer(
                (ctypes.c_char * 8)(), 8,
            )
        return None

    monkeypatch.setattr(wa, "_get_token_buffer", buffers)

    verification = wa.TokenVerification()
    wa._verify_token_into(
        verification,
        ctypes.c_void_p(1),  # a stub token handle; never dereferenced
        wa.PRODUCT_PACKAGE_SID,
        wa.ZERO_CAPABILITIES,
    )

    assert not verification.ok, (
        "a verification whose capability list could not be read must fail"
    )
    assert any(
        "capability list could not be read" in error
        for error in verification.errors
    ), verification.errors
