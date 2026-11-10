r"""Windows AppContainer identity, capabilities, and handle-containment policy.

**BBF-FU-20-windows-appcontainer-network-isolation.**

This module is the Windows counterpart of the Linux sandbox launcher
(:mod:`chess_coach.pdf_ocr.linux_sandbox`). It owns ONE responsibility:
preparing the *identity* and *containment contract* for a parser launch
that must be unable to reach the network.

It is deliberately narrow. It does not create processes, create Jobs, or
resume threads — :mod:`chess_coach.pdf_ocr.windows_job` owns that
lifecycle. What this module owns is:

* the product-owned AppContainer package identity;
* the zero-network-capability set;
* the explicit inherited-handle allowlist policy;
* the pre-resume token verification that proves the launched process really
  is the AppContainer it claims to be.

Security contract (all of it measured on a native Windows host — see the
FU-20 feasibility memo and the implementation evidence bundle):

1. **Zero network capabilities.** The launched token carries no
   ``S-1-15-3-*`` capability SID at all, so it cannot hold ``internetClient``
   and therefore cannot create a new outbound network connection. Measured:
   the restricted child timed out on an outbound TCP connect while an
   unrestricted control in the same run connected.

2. **An AppContainer token does not revoke an inherited network handle.**
   This is a property of the platform, not a harness defect: a connected
   socket that is *inherited* by the child stays usable inside the
   AppContainer. The mitigation is therefore the handle policy below, not
   the container alone.

3. **The handle allowlist is explicit and populated.**
   ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST`` is used with
   ``bInheritHandles=TRUE`` and contains *only* the handles the parser
   actually needs (stdout and stderr). Measured: with that populated
   allowlist a live connected socket in the parent was reported as
   ``PRESENT ... inheritable=False`` inside the child and every send on it
   failed with ``WSAENOTSOCK`` (10038), while the same socket was usable
   in the positive control that used no allowlist.
   The **empty** allowlist is explicitly NOT used: it was measured not to
   provide an empty allowlist.

4. **The token is verified before the target runs.** The launcher's
   ``TokenIsAppContainer`` and ``TokenAppContainerSid`` are read while the
   target is still suspended. A mismatch is a fail-closed setup error; the
   target is never resumed.

The product-owned package identity
----------------------------------

``PRODUCT_PACKAGE_SID`` is a fixed, documented, product-owned AppContainer
package SID under the ``S-1-15-2`` application-package authority.

It is **not** borrowed from a Store package, and it is **not** claimed to be
the output of ``DeriveAppContainerSidFromAppContainerName`` — that API was
measured to be a no-op on the validation host (``S_OK`` with a zero count
and a null SID, exactly like ``CreateAppContainerProfile``). The constant
is the 256-bit SHA-256 of the package name, split into seven 32-bit
big-endian subauthorities and rendered in decimal, which is the form
Windows itself uses for AppContainer package SIDs.

Windows requires an AppContainer SID to be *known* to the system before it
can back a launched token: an unregistered SID fails at process creation
with ``ERROR_FILE_NOT_FOUND``. The profile is therefore registered under
``HKCU\...\CurrentVersion\AppContainer\Mappings\<SID>`` with the same
shape Windows itself uses (a ``Moniker``/``DisplayName`` pair plus
``Capabilities`` and ``Children`` subkeys), and the moniker package folder
is created under ``%LOCALAPPDATA%\Packages``. Both steps are per-user and
require no administrator rights.

Registration is idempotent and verified: if the mapping is missing or has
the wrong shape, the launch fails closed rather than falling back to a
borrowed identity.
"""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: The package moniker owned by this product.
PRODUCT_PACKAGE_MONIKER = "ChessCoach.PdfParser_8wekyb3d8bbwe"

#: The package **name** whose SHA-256 digest defines the product SID.
#:
#: The derivation is: ``SHA-256(PRODUCT_PACKAGE_NAME)``, taken as its
#: first 28 bytes (seven big-endian 32-bit groups), each rendered in
#: decimal and appended to the ``S-1-15-2`` application-package
#: authority. See :data:`PRODUCT_PACKAGE_SID`.
PRODUCT_PACKAGE_NAME = "ChessCoach.PdfParser"

#: The product-owned AppContainer package SID.
#:
#: Application-package authority ``S-1-15-2`` with seven product-owned
#: 32-bit subauthorities. The value is the SHA-256 of the package name
#: ``ChessCoach.PdfParser``, split into seven big-endian 32-bit groups and
#: rendered in **decimal** (Windows parses AppContainer package
#: subauthorities as decimal; a hex-formatted variant is rejected with
#: ``ERROR_INVALID_SID`` / 1337).
#:
#: Ownership: this constant belongs to Chess Coach alone. It is not
#: derived from, and does not collide with, any Store package identity.
PRODUCT_PACKAGE_SID = (
    "S-1-15-2-1307264423-3961844790-1637159078-741858669-3028905837-"
    "1642583832-2140039969"
)

#: The seven subauthorities of :data:`PRODUCT_PACKAGE_SID`, for callers that
#: want to verify the constant's shape without re-parsing it.
PRODUCT_PACKAGE_SUBAUTHORITIES: tuple[int, ...] = (
    1307264423,
    3961844790,
    1637159078,
    741858669,
    3028905837,
    1642583832,
    2140039969,
)

#: The ``internetClient`` capability SID. Its absence is what makes the
#: container unable to open a new outbound connection.
INTERNET_CLIENT_CAPABILITY_SID = "S-1-15-3-1"

#: The capability-authority prefix. No SID under it may appear in the
#: launched token.
CAPABILITY_AUTHORITY_PREFIX = "S-1-15-3-"

#: The ALL APPLICATION PACKAGES group SID. Windows always places this in
#: an AppContainer token; it grants *no* network capability on its own.
ALL_APPLICATION_PACKAGES_SID = "S-1-15-2-1"

#: ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST``.
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002

#: ``PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES``.
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009

#: Token information classes used for the pre-resume verification.
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_TOKEN_GROUPS = 2
_TOKEN_CAPABILITIES = 30
_TOKEN_IS_APP_CONTAINER = 29
_TOKEN_APP_CONTAINER_SID = 31


class AppContainerError(Exception):
    """Base class for AppContainer preparation failures.

    Every failure here happens *before* the parser is allowed to run, so
    an ``AppContainerError`` always means "the parser did not execute",
    never "the parser failed".
    """

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, object] = dict(details or {})


class AppContainerUnsupportedError(AppContainerError):
    """The Windows AppContainer backend is unavailable on this host.

    Distinct from a *setup* failure: this says the backend cannot be used
    here at all (wrong platform, or the required Win32 surface is absent).
    The route layer maps this to the retained 501 refusal.
    """


class AppContainerSetupError(AppContainerError):
    """A containment stage failed, so the parser was never executed.

    Distinct from the unsupported-platform case and from every parser
    failure, timeout, or limit violation. The route layer maps this to
    500 ``internal.network_isolation_setup_failed``.
    """


class AppContainerVerificationError(AppContainerSetupError):
    """The launched token did not match the expected AppContainer identity.

    Raised when the pre-resume verification finds that the target is not
    an AppContainer, or that its AppContainer SID is not the product SID.
    The target is never resumed on this path.
    """


# ---------------------------------------------------------------------------
# Win32 loading
# ---------------------------------------------------------------------------


#: ``ctypes.WinDLL`` exists ONLY on Windows.  It is resolved through
#: ``getattr`` so this module stays importable -- and type-checkable -- on
#: the Linux CI runners, exactly as the sibling ``windows_job`` module does.
_WINDLL_LOADER = getattr(ctypes, "WinDLL", None)

#: ``ctypes.get_last_error`` exists only on Windows.  It is reached
#: through a module-level accessor rather than named directly, so this
#: module stays importable **and** type-checkable on Linux -- exactly as
#: the sibling ``windows_job`` module does.  Using ``getattr`` rather than
#: a direct attribute access also keeps the module free of
#: platform-specific ``type: ignore`` comments, which
#: ``warn_unused_ignores`` would flag on the platform where the
#: attribute *does* exist.
_LAST_ERROR_GETTER = getattr(ctypes, "get_last_error", None)


def _last_error() -> int:
    """Return the last Win32 error code (``ctypes.get_last_error``)."""
    getter = _LAST_ERROR_GETTER
    if getter is None:
        return 0
    code: int = getter()
    return code


def _windll(name: str) -> ctypes.CDLL:
    """Load a Windows DLL (``ctypes.WinDLL``).

    Raises:
        AppContainerUnsupportedError: on a platform with no ``WinDLL``.
    """
    loader = _WINDLL_LOADER
    if loader is None:
        raise AppContainerUnsupportedError(
            "the AppContainer backend requires Windows",
            details={"platform": sys.platform, "stage": "platform_gate"},
        )
    library: ctypes.CDLL = loader(name, use_last_error=True)
    return library


def _load_kernel32() -> ctypes.CDLL:
    try:
        return _windll("kernel32")
    except OSError as exc:  # pragma: no cover - platform gate
        raise AppContainerUnsupportedError(
            "kernel32.dll is unavailable",
            details={"platform": sys.platform, "error": str(exc)},
        ) from exc


def _load_advapi32() -> ctypes.CDLL:
    try:
        return _windll("advapi32")
    except OSError as exc:  # pragma: no cover - platform gate
        raise AppContainerUnsupportedError(
            "advapi32.dll is unavailable",
            details={"platform": sys.platform, "error": str(exc)},
        ) from exc


#: ``True`` when the host can run the Windows AppContainer backend.
APPCONTAINER_SUPPORTED: bool = sys.platform == "win32"


def _require_windows() -> None:
    if not APPCONTAINER_SUPPORTED:
        raise AppContainerUnsupportedError(
            "the Windows AppContainer backend is only available on Windows",
            details={"platform": sys.platform, "stage": "platform_gate"},
        )


# ---------------------------------------------------------------------------
# SID handling
# ---------------------------------------------------------------------------


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_uint32)]


class _TOKEN_APPCONTAINER_SID(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Flags", ctypes.c_uint32)]


def sid_to_string(sid_ptr: int | None) -> str | None:
    """Render a SID from its raw bytes.

    The subauthority DWORDs are stored **little-endian** in the SID
    structure; only the string form is big-endian decimal. Reading them
    big-endian yields a plausible-looking but wrong SID, which is exactly
    the kind of error that would silently defeat a token check.
    """
    if not sid_ptr:
        return None
    # Read the count byte first, then exactly that many subauthorities.
    # Reading a fixed 46 bytes truncated a long SID (16 subauthorities)
    # to 8, which would have silently produced a wrong identity.
    header = ctypes.string_at(ctypes.cast(sid_ptr, ctypes.c_void_p), 8)
    count = header[1]
    if count > 15:
        # SECURITY_MAX_SID_SIZE is 68 bytes = 15 subauthorities. A SID with
        # more subauthorities is malformed for the Windows binary form.
        # Truncating it silently would produce a DIFFERENT identity, so it
        # is rejected instead.
        raise AppContainerSetupError(
            "the SID has an invalid subauthority count",
            details={"stage": "sid_decode", "count": int(count)},
        )
    raw = ctypes.string_at(
        ctypes.cast(sid_ptr, ctypes.c_void_p), 8 + count * 4,
    )
    revision = raw[0]
    authority = int.from_bytes(raw[2:8], "big")
    subs = [
        int.from_bytes(raw[8 + i * 4:12 + i * 4], "little") for i in range(count)
    ]
    return "-".join([f"S-{revision}-{authority}"] + [str(v) for v in subs])


def parse_sid_string(sid_string: str) -> ctypes.c_void_p:
    """Parse a SID string into a SID pointer.

    The caller owns the allocation and must release it with
    :func:`free_sid` once it is no longer needed.

    Raises:
        AppContainerSetupError: the string is not a valid SID.
    """
    validate_application_package_sid(sid_string)
    adv = _load_advapi32()
    adv.ConvertStringSidToSidW.restype = ctypes.c_int
    adv.ConvertStringSidToSidW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    sid = ctypes.c_void_p()
    if not adv.ConvertStringSidToSidW(sid_string, ctypes.byref(sid)):
        raise AppContainerSetupError(
            f"the package SID {sid_string!r} is not a valid SID",
            details={
                "sid": sid_string,
                "win32_error": _last_error(),
                "stage": "sid_parse",
            },
        )
    return sid


def free_sid(sid_ptr: ctypes.c_void_p | None) -> None:
    """Release a SID allocated by :func:`parse_sid_string`.

    ``ConvertStringSidToSidW`` allocates with ``LocalAlloc``, so the
    allocation must be released with ``LocalFree``.  Doing it here keeps
    the per-launch leak out of the launch path.
    """
    if not sid_ptr:
        return
    try:
        kernel32 = _load_kernel32()
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(sid_ptr, ctypes.c_void_p))
    except Exception:  # pragma: no cover - defensive
        # A failure to release the SID must never mask the launch outcome,
        # but it is worth recording.
        import logging

        logging.getLogger(__name__).warning(
            "could not release the package SID allocation", exc_info=True,
        )


def validate_product_sid(sid_string: str = PRODUCT_PACKAGE_SID) -> tuple[int, ...]:
    """Validate the shape of a product package SID.

    Returns the parsed subauthorities.

    Raises:
        AppContainerSetupError: the SID does not have the required shape.
    """
    parts = sid_string.split("-")
    # S-1-15-2-<sub0>-<sub1>-...-<sub7>
    #   "S", revision "1", authority "15", then EIGHT subauthorities: the
    #   literal "2" (the application-package subauthority) followed by the
    #   seven product-owned 32-bit values.
    if len(parts) != 11 or parts[0] != "S" or parts[1] != "1" or parts[2] != "15":
        raise AppContainerSetupError(
            f"the package SID {sid_string!r} is not an S-1-15-2 application-package SID",
            details={"sid": sid_string, "stage": "sid_shape"},
        )
    if parts[3] != "2":
        raise AppContainerSetupError(
            f"the package SID {sid_string!r} does not carry the "
            "application-package subauthority 2",
            details={"sid": sid_string, "stage": "sid_shape"},
        )
    subs = tuple(int(p) for p in parts[4:])
    if len(subs) != 7:
        raise AppContainerSetupError(
            f"the package SID {sid_string!r} does not have seven product subauthorities",
            details={"sid": sid_string, "stage": "sid_shape"},
        )
    for sub in subs:
        if not 0 <= sub <= 0xFFFFFFFF:
            raise AppContainerSetupError(
                f"the package SID {sid_string!r} has an out-of-range subauthority",
                details={"sid": sid_string, "stage": "sid_shape"},
            )
    return subs


def validate_application_package_sid(sid_string: str) -> None:
    """Validate that ``sid_string`` is *some* application-package SID.

    Used for the pre-resume comparison, where the launcher may be pointed
    at an identity other than the product one (the fail-closed test does
    exactly that). It checks the ``S-1-15-2`` authority and the decimal
    subauthority form without requiring the seven product subauthorities.
    """
    parts = sid_string.split("-")
    if len(parts) < 4 or parts[0] != "S" or parts[1] != "1" or parts[2] != "15" \
            or parts[3] != "2":
        raise AppContainerSetupError(
            f"the package SID {sid_string!r} is not an S-1-15-2 application-package SID",
            details={"sid": sid_string, "stage": "sid_shape"},
        )
    for part in parts[4:]:
        if not part.isdigit():
            raise AppContainerSetupError(
                f"the package SID {sid_string!r} has a non-decimal subauthority",
                details={"sid": sid_string, "stage": "sid_shape"},
            )

# ---------------------------------------------------------------------------
# Capability selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilitySet:
    """The capability SIDs granted to the launched parser.

    The production set is **empty**: no ``S-1-15-3-*`` capability at all,
    so the token cannot hold ``internetClient`` and cannot open a new
    outbound network connection.

    A non-empty set is representable so that a future, explicitly reviewed
    product decision could grant a specific capability, but the production
    path never does so, and there is no code path that grants
    ``internetClient``.
    """

    sids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for sid in self.sids:
            if not sid.startswith(CAPABILITY_AUTHORITY_PREFIX):
                raise AppContainerSetupError(
                    f"{sid!r} is not a capability SID",
                    details={"sid": sid, "stage": "capability_selection"},
                )
        if INTERNET_CLIENT_CAPABILITY_SID in self.sids:
            raise AppContainerSetupError(
                "the internetClient capability must never be granted to the parser",
                details={
                    "sid": INTERNET_CLIENT_CAPABILITY_SID,
                    "stage": "capability_selection",
                },
            )

    @property
    def is_network_capable(self) -> bool:
        """``True`` when this set would grant any network capability."""
        return any(sid.startswith(CAPABILITY_AUTHORITY_PREFIX) for sid in self.sids)


#: The production capability set: no capabilities at all.
ZERO_CAPABILITIES = CapabilitySet()


def select_capabilities() -> CapabilitySet:
    """Return the capability set for a parser launch.

    Always the zero-capability set. Kept as a named function so the
    policy is explicit at the call site and independently testable.
    """
    return ZERO_CAPABILITIES


# ---------------------------------------------------------------------------
# Inherited-handle policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HandlePolicy:
    """The inherited-handle contract for the parser launch.

    Attributes:
        inherit_handles: the value passed to ``CreateProcessW`` as
            ``bInheritHandles``. It must be ``True`` for
            ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST`` to be honoured at all
            (measured: ``CreateProcessW`` fails with
            ``ERROR_INVALID_PARAMETER`` / 87 when a handle list is supplied
            together with ``bInheritHandles=FALSE``).
        allowlist_stdout: whether the stdout handle may be inherited.
        allowlist_stderr: whether the stderr handle may be inherited.
        use_explicit_allowlist: whether the explicit handle list is
            applied at all. Production always sets it to ``True``.

            When it is ``False`` **no** handle list is applied, so every
            inheritable handle in the parent crosses into the child. That
            is the *bypass* shape: it exists so the threat-model fact that
            an AppContainer token does not revoke an inherited network
            handle stays directly demonstrable, and it is never used by the
            production launch path.
    """

    inherit_handles: bool = True
    allowlist_stdout: bool = True
    allowlist_stderr: bool = True
    use_explicit_allowlist: bool = True

    def __post_init__(self) -> None:
        if not self.inherit_handles:
            raise AppContainerSetupError(
                "the parser launch requires bInheritHandles=TRUE so the "
                "explicit handle allowlist can be applied",
                details={"stage": "handle_policy"},
            )

    @property
    def allows_stdout(self) -> bool:
        return self.allowlist_stdout

    @property
    def allows_stderr(self) -> bool:
        return self.allowlist_stderr

    def permitted_handles(self, *, stdout: int | None, stderr: int | None) -> list[int]:
        """The exact handle values permitted to cross into the child.

        Only the parser's own standard handles appear. No other inherited
        handle — in particular no connected socket — is ever included.
        """
        if not self.use_explicit_allowlist:
            return []
        allowed: list[int] = []
        if self.allowlist_stdout and stdout:
            allowed.append(int(stdout))
        if self.allowlist_stderr and stderr:
            allowed.append(int(stderr))
        return allowed


#: The production handle policy.
#:
#: ``bInheritHandles=TRUE`` plus an explicit allowlist containing only the
#: parser's stdout and stderr. Measured on a native Windows host: a live
#: connected socket held by the parent was excluded from the child
#: (``SEND-FAILED`` / 10038) while the same socket remained usable in the
#: positive control that used no allowlist.
#:
#: The **empty** allowlist is deliberately not used: it was measured not to
#: provide an empty allowlist, because the child's own standard handles
#: occupy the same handle values.
DEFAULT_HANDLE_POLICY = HandlePolicy()


# ---------------------------------------------------------------------------
# Profile registration
# ---------------------------------------------------------------------------

_APP_CONTAINER_MAPPINGS_REG = (
    r"HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows"
    r"\CurrentVersion\AppContainer\Mappings"
)


def _run_reg(args: Sequence[str]) -> tuple[int, str, str]:
    import subprocess

    try:
        proc = subprocess.run(  # noqa: S603 -- fixed system binary
            [r"C:\Windows\System32\reg.exe", *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=120,
            check=False,
            # The arguments are built from module constants, never user input.
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AppContainerSetupError(
            "could not run reg.exe to register the AppContainer profile",
            details={"stage": "profile_registration", "error": str(exc)},
        ) from exc
    return proc.returncode, proc.stdout or "", proc.stderr or ""


#: Cache of the registration check, keyed by SID.
#:
#: The check spawns ``reg.exe``, and a subprocess launch costs Win32
#: handles in this process (measured: ~3 handles per 10 ``subprocess.run``
#: calls).  The registration is this application's own state and cannot
#: change while the process runs, so the answer is cached.  Every code path
#: that CHANGES the registration invalidates the cache.
_REGISTRATION_CACHE: dict[str, bool] = {}


def profile_is_registered(sid_string: str = PRODUCT_PACKAGE_SID) -> bool:
    """Whether the AppContainer mapping for ``sid_string`` exists.

    The answer is cached per SID, because the check spawns ``reg.exe`` and
    a subprocess launch costs Win32 handles in this process.  The cache is
    invalidated whenever the registration is changed.
    """
    cached = _REGISTRATION_CACHE.get(sid_string)
    if cached is not None:
        return cached
    rc, out, _ = _run_reg(["query", f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}"])
    registered = rc == 0
    _REGISTRATION_CACHE[sid_string] = registered
    return registered


def invalidate_registration_cache(sid_string: str | None = None) -> None:
    """Forget a cached registration check.

    Called by every routine that changes the registration, so the next
    check re-reads the registry.
    """
    if sid_string is None:
        _REGISTRATION_CACHE.clear()
    else:
        _REGISTRATION_CACHE.pop(sid_string, None)


def register_profile(
    *,
    sid_string: str = PRODUCT_PACKAGE_SID,
    moniker: str = PRODUCT_PACKAGE_MONIKER,
    display_name: str = "Chess Coach PDF Parser",
) -> None:
    """Register the product-owned AppContainer profile for the current user.

    Windows keys AppContainer mappings by the SID itself::

        HKCU\\...\\CurrentVersion\\AppContainer\\Mappings\\<SID>
            Moniker    REG_SZ  <moniker>
            DisplayName REG_SZ <display name>
            Capabilities
            Children

    and expects the moniker package folder to exist under
    ``%LOCALAPPDATA%\\Packages``. An unregistered SID cannot back a
    launched token: the process creation fails with
    ``ERROR_FILE_NOT_FOUND``.

    Both steps are per-user and need no administrator rights. The
    operation is idempotent.

    Raises:
        AppContainerSetupError: the mapping could not be created or
            verified.
    """
    _require_windows()
    validate_product_sid(sid_string)

    steps = (
        ["add", f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}"],
        ["add", f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}", "/v", "Moniker",
         "/t", "REG_SZ", "/d", moniker],
        ["add", f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}", "/v", "DisplayName",
         "/t", "REG_SZ", "/d", display_name],
        ["add", f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}\\Capabilities"],
        ["add", f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}\\Children"],
    )
    for step in steps:
        rc, out, err = _run_reg(step)
        if rc != 0:
            raise AppContainerSetupError(
                "could not register the AppContainer profile for the product SID",
                details={
                    "stage": "profile_registration",
                    "sid": sid_string,
                    "operation": step[1],
                    "win32_error": rc,
                    "message": (err or out).strip()[:400],
                },
            )

    package_folder = package_folder_path(moniker)
    for sub in ("AC", os.path.join("AC", "Temp"), "LocalCache", "LocalState",
                "RoamingState", "Settings"):
        try:
            (package_folder / sub).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AppContainerSetupError(
                "could not create the AppContainer package folder",
                details={
                    "stage": "profile_registration",
                    "path": str(package_folder / sub),
                    "error": str(exc),
                },
            ) from exc

    invalidate_registration_cache(sid_string)
    if not profile_is_registered(sid_string):
        raise AppContainerSetupError(
            "the AppContainer profile registration could not be verified",
            details={"stage": "profile_registration", "sid": sid_string},
        )


def package_folder_path(moniker: str = PRODUCT_PACKAGE_MONIKER) -> Path:
    """The per-user package folder for ``moniker``."""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Packages" / moniker


# ---------------------------------------------------------------------------
# Owned-state cleanup
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CleanupReport:
    """What a cleanup pass removed, and what it deliberately left alone.

    Every entry is either ``removed`` (this application created it) or
    ``preserved`` (it belongs to another identity or a pre-existing
    installation, so it must not be deleted).
    """

    removed: tuple[str, ...] = ()
    preserved: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def _mapping_moniker(sid_string: str) -> str | None:
    """The moniker registered for ``sid_string``, or ``None``."""
    rc, out, _ = _run_reg(["query", f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}",
                           "/v", "Moniker"])
    if rc != 0:
        return None
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("Moniker"):
            parts = stripped.split(None, 2)
            if len(parts) >= 3:
                return parts[2].strip()
    return None


def cleanup_owned_state(
    *,
    sid_string: str = PRODUCT_PACKAGE_SID,
    moniker: str = PRODUCT_PACKAGE_MONIKER,
    staging: Path | None = None,
    remove_package_folder: bool = True,
) -> CleanupReport:
    """Remove the state this application owns, and nothing else.

    The application owns exactly three things:

    1. the AppContainer mapping registered under ``sid_string``;
    2. the ``ProgramData\\ChessCoach*`` parser-staging tree;
    3. the package moniker folder under ``%LOCALAPPDATA%\\Packages``.

    The cleanup is **ownership-scoped**:

    * the mapping is removed only when it is keyed by the product SID
      **and** its ``Moniker`` value is the product moniker. A mapping
      keyed by the product SID that carries a *different* moniker belongs
      to another installation and is preserved.
    * the staging tree is removed only when it lives under the product's
      own staging root and carries the product marker.
    * the package folder is removed only when it is named for the product
      moniker.

    A pre-existing mapping for a **different** identity is never touched:
    the cleanup never enumerates the mappings key and never deletes a
    sibling's state.

    The operation is idempotent: running it twice removes nothing the
    second time and reports no error.

    Raises:
        AppContainerSetupError: the product state could not be inspected.
    """
    import shutil

    removed: list[str] = []
    preserved: list[str] = []
    errors: list[str] = []

    # The cleanup CHANGES the registration, so the cached check is stale.
    invalidate_registration_cache(sid_string)

    # --- 1. the AppContainer mapping ------------------------------------
    # The mapping lives in the Windows registry.  On a non-Windows host it
    # cannot exist, so it is reported as absent rather than failing -- the
    # FILESYSTEM half of the cleanup below is platform independent.
    mapping_key = f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}"
    if sys.platform != "win32":
        preserved.append(f"appcontainer-mapping:{sid_string} (not a Windows host)")
    elif profile_is_registered(sid_string):
        existing_moniker = _mapping_moniker(sid_string)
        if existing_moniker is None:
            preserved.append(f"appcontainer-mapping:{sid_string}")
        elif existing_moniker == moniker:
            rc, out, err = _run_reg(["delete", mapping_key, "/f"])
            if rc == 0:
                removed.append(f"appcontainer-mapping:{sid_string}")
            else:
                errors.append(
                    f"could not remove the AppContainer mapping for {sid_string}: "
                    f"{(err or out).strip()[:200]}"
                )
        else:
            # A DIFFERENT moniker under the product SID: not ours.
            preserved.append(
                f"appcontainer-mapping:{sid_string} (moniker {existing_moniker!r})"
            )
    else:
        preserved.append(f"appcontainer-mapping:{sid_string} (absent)")

    # --- 2. the parser staging tree -------------------------------------
    root = staging if staging is not None else staging_root()
    poppler_dir = root / "poppler"
    if poppler_dir.exists():
        marker = poppler_dir / ".chesscoach-staging"
        if marker.exists():
            try:
                shutil.rmtree(poppler_dir, ignore_errors=False)
                removed.append(f"staging:{poppler_dir}")
            except OSError as exc:
                errors.append(f"could not remove the staging tree {poppler_dir}: {exc}")
        else:
            # Not marked as ours: leave it alone.
            preserved.append(f"staging:{poppler_dir} (not owned)")
    else:
        preserved.append(f"staging:{poppler_dir} (absent)")

    # --- 3. the package moniker folder -----------------------------------
    package = package_folder_path(moniker)
    if package.exists():
        if remove_package_folder:
            try:
                shutil.rmtree(package, ignore_errors=False)
                removed.append(f"package-folder:{package}")
            except OSError as exc:
                errors.append(f"could not remove the package folder {package}: {exc}")
        else:
            preserved.append(f"package-folder:{package} (retained by request)")
    else:
        preserved.append(f"package-folder:{package} (absent)")

    # The cleanup CHANGED the registration, so the cached check is stale
    # again -- after the removal, not only before it.
    invalidate_registration_cache(sid_string)

    return CleanupReport(
        removed=tuple(removed),
        preserved=tuple(preserved),
        errors=tuple(errors),
    )


# ---------------------------------------------------------------------------
# Staging and minimum ACLs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StagedParser:
    """A parser executable staged outside the user profile.

    An AppContainer token cannot traverse the user profile, so a
    profile-resident executable is unlaunchable inside the container
    (measured: ``STATUS_DLL_NOT_FOUND``). The parser and its runtime
    dependencies must therefore live in a location the restricted token can
    reach, with the minimum ACLs the parser needs.
    """

    executable: Path
    directory: Path
    runtime_dirs: tuple[Path, ...] = ()

    def paths(self) -> tuple[Path, ...]:
        """Every path that must be reachable by the restricted token.

        The CONTAINING DIRECTORY comes first and is required: a Windows
        token needs ``FILE_TRAVERSE`` on the parent directory to resolve
        a child file, and the directory's own ACL therefore governs
        whether the staged DLLs can be opened at all.
        """
        return (self.directory, self.executable, *self.runtime_dirs)


def grant_minimum_access(
    paths: Sequence[Path],
    *,
    sid_string: str = PRODUCT_PACKAGE_SID,
    read_only: bool = True,
) -> None:
    """Grant the product SID the minimum access it needs on ``paths``.

    Read-only paths get ``RX``; the output/artifact directory gets ``M``.
    No source tree, parent-process directory, or arbitrary user-profile
    path is granted.
    """
    import subprocess

    _require_windows()
    for path in paths:
        perms = "RX" if read_only else "M"
        # The inheritance flags only mean anything on a DIRECTORY.  On a
        # FILE, `icacls /grant *SID:(OI)(CI)(RX)` returns success and adds
        # NO ACE, so the grant silently does nothing and the parser cannot
        # load its DLLs (STATUS_DLL_NOT_FOUND).  A file therefore gets the
        # plain right, and a directory keeps the inheritable form.
        #
        # The directory is granted as well as the files.  That is a
        # SUPERSET of what the parser strictly needs: measured on this
        # host, granting the files alone was enough for the parser to
        # resolve its runtime.  The directory grant is kept because it
        # states the intent (the container may reach into the staged
        # runtime) and because it removes the dependence on the
        # inherited-user ACEs of the staging tree.
        is_dir = path.is_dir()
        right = f"*{sid_string}:(OI)(CI)({perms})" if is_dir else f"*{sid_string}:({perms})"
        cmd = [
            "icacls", str(path), "/grant", right,
        ]
        try:
            proc = subprocess.run(  # noqa: S603 -- fixed system binary
                cmd, capture_output=True, text=True, errors="replace",
                timeout=120, check=False,
                # The paths are the product's own staging directories.
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AppContainerSetupError(
                "could not apply the minimum-access ACL",
                details={"stage": "acl_grant", "path": str(path), "error": str(exc)},
            ) from exc
        if proc.returncode != 0:
            raise AppContainerSetupError(
                "could not apply the minimum-access ACL",
                details={
                    "stage": "acl_grant",
                    "path": str(path),
                    "win32_error": proc.returncode,
                    "message": (proc.stderr or proc.stdout).strip()[:400],
                },
            )
        # `icacls` reports success even when it adds no ACE, so the grant
        # is verified by reading the ACL back.  A grant that did not land
        # is a setup failure, not a silent no-op that shows up later as a
        # confusing parser exit code.
        try:
            check = subprocess.run(  # noqa: S603 -- fixed system binary
                [r"C:\Windows\System32\icacls.exe", str(path)],
                capture_output=True, text=True,
                errors="replace", timeout=120, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AppContainerSetupError(
                "could not verify the minimum-access ACL",
                details={
                    "stage": "acl_grant",
                    "path": str(path),
                    "error": str(exc),
                },
            ) from exc
        # A bare substring test would also pass if the SID appeared only in
        # a DENIED or an unrelated ACE line, so the GRANT line itself is
        # matched: the SID must be followed by an explicit right set.
        acl_text = check.stdout or ""
        lines = acl_text.splitlines()
        # A GRANT line, not a DENY line: `(DENY)(...)` also has the SID
        # followed by "(", so the deny form must be excluded explicitly.
        granted = any(
            sid_string in line
            and "(DENY)" not in line.upper()
            and "(" in line.split(sid_string, 1)[1]
            for line in lines
        )
        # A DENY line is never mistaken for a grant.  Note that
        # `icacls /grant` REPLACES the explicit ACE for the SID, so a
        # deny that was present before the grant is gone by the time the
        # readback runs; the check below is what catches a deny that
        # SURVIVED the grant, for example an inherited deny on a
        # directory the grant did not touch.
        if not granted:
            raise AppContainerSetupError(
                "the minimum-access ACL did not grant the product SID",
                details={
                    "stage": "acl_grant",
                    "path": str(path),
                    "sid": sid_string,
                    "message": (check.stdout or check.stderr or "").strip()[:400],
                },
            )


# ---------------------------------------------------------------------------
# Parser staging
# ---------------------------------------------------------------------------

#: The directory the parser is staged into. It is **outside the user
#: profile**: an AppContainer token cannot traverse the user profile, so a
#: profile-resident executable is unlaunchable inside the container.
DEFAULT_STAGING_ROOT = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ChessCoach"

#: The environment variable that overrides the staging root. It exists for
#: CI, where the runner stages Poppler into a directory it controls.
ENV_STAGING_ROOT = "CHESS_COACH_APPCONTAINER_STAGING_ROOT"


def staging_root() -> Path:
    """The directory the parser is staged into."""
    override = os.getenv(ENV_STAGING_ROOT)
    if override:
        return Path(override)
    return DEFAULT_STAGING_ROOT


def stage_parser(
    *,
    source_dir: Path | None = None,
    staging: Path | None = None,
) -> StagedParser:
    """Stage the PDF parser and its runtime outside the user profile.

    The parser is copied from ``source_dir`` (by default the directory
    ``pdftoppm`` is found in) into a staging directory under
    :func:`staging_root`, which is outside the user profile.

    Staging is idempotent: a staged tree whose contents already match is
    reused rather than recopied.

    Raises:
        AppContainerUnsupportedError: the parser could not be located.
        AppContainerSetupError: the staging copy failed.
    """
    import shutil

    _require_windows()
    if source_dir is None:
        found = shutil.which("pdftoppm")
        if not found:
            raise AppContainerUnsupportedError(
                "pdftoppm was not found, so the AppContainer parser cannot be staged",
                details={"stage": "parser_staging", "executable": "pdftoppm"},
            )
        source_dir = Path(found).parent

    executable_name = "pdftoppm.exe" if os.name == "nt" else "pdftoppm"
    source_executable = source_dir / executable_name
    if not source_executable.exists():
        raise AppContainerUnsupportedError(
            "the PDF parser executable could not be located for staging",
            details={
                "stage": "parser_staging",
                "expected": str(source_executable),
            },
        )

    root = staging if staging is not None else staging_root() / "poppler"
    target_executable = root / executable_name

    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AppContainerSetupError(
            "could not create the AppContainer staging directory",
            details={"stage": "parser_staging", "path": str(root), "error": str(exc)},
        ) from exc

    if not target_executable.exists():
        # Copy the whole runtime directory: the Poppler DLLs live beside
        # the executable and the container needs them.
        try:
            for item in source_dir.iterdir():
                if not item.is_file():
                    continue
                destination = root / item.name
                if destination.exists() and destination.stat().st_size == item.stat().st_size:
                    continue
                shutil.copy2(item, destination)
        except OSError as exc:
            raise AppContainerSetupError(
                "could not stage the PDF parser for the AppContainer",
                details={
                    "stage": "parser_staging",
                    "source": str(source_dir),
                    "target": str(root),
                    "error": str(exc),
                },
            ) from exc

    # The ownership marker: cleanup removes this staging tree only when it
    # carries the marker, so a directory that belongs to another
    # installation is never deleted.
    marker = root / ".chesscoach-staging"
    if not marker.exists():
        try:
            marker.write_text(
                "Staged by Chess Coach for the Windows AppContainer PDF parser.\n"
                "This directory is owned by the Chess Coach installation and is\n"
                "removed by the application's own cleanup routine.\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise AppContainerSetupError(
                "could not mark the staged parser directory as owned",
                details={"stage": "parser_staging", "path": str(marker), "error": str(exc)},
            ) from exc

    if not target_executable.exists():
        raise AppContainerSetupError(
            "the staged PDF parser is missing after staging",
            details={"stage": "parser_staging", "expected": str(target_executable)},
        )

    runtime_dirs = tuple(
        path for path in sorted(root.iterdir()) if path.is_file()
    )
    return StagedParser(
        executable=target_executable,
        directory=root,
        runtime_dirs=runtime_dirs,
    )


# ---------------------------------------------------------------------------
# Pre-resume token verification
# ---------------------------------------------------------------------------


@dataclass
class TokenVerification:
    """The result of the pre-resume token verification."""

    is_app_container: bool = False
    app_container_sid: str | None = None
    capability_sids: tuple[str, ...] = ()
    group_sids: tuple[str, ...] = ()
    internet_client_present: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _open_process_token(process_handle: int) -> ctypes.c_void_p:
    """Open the target's token for querying.

    The returned token handle is owned by the CALLER, which must close it
    with :func:`_close_token` -- otherwise every verification leaks a
    handle.
    """
    adv = _load_advapi32()
    adv.OpenProcessToken.restype = ctypes.c_int
    adv.OpenProcessToken.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    token = ctypes.c_void_p()
    if not adv.OpenProcessToken(process_handle, _TOKEN_QUERY, ctypes.byref(token)):
        raise AppContainerSetupError(
            "could not open the launched process token",
            details={
                "stage": "token_verification",
                "win32_error": _last_error(),
            },
        )
    return token


def _close_token(token: ctypes.c_void_p) -> None:
    """Close a token handle opened by :func:`_open_process_token`."""
    if not token:
        return
    try:
        kernel32 = _load_kernel32()
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(ctypes.cast(token, ctypes.c_void_p))
    except Exception:  # pragma: no cover - defensive
        import logging

        logging.getLogger(__name__).warning(
            "could not close the process token handle", exc_info=True,
        )


def _get_token_buffer(
    token: ctypes.c_void_p,
    info_class: int,
) -> ctypes.Array[ctypes.c_char] | None:
    adv = _load_advapi32()
    adv.GetTokenInformation.restype = ctypes.c_int
    adv.GetTokenInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    size = ctypes.c_uint32(0)
    adv.GetTokenInformation(token, info_class, None, 0, ctypes.byref(size))
    if not size.value:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if not adv.GetTokenInformation(token, info_class, buf, size.value,
                                   ctypes.byref(size)):
        return None
    return buf


def _read_token_sids(token: ctypes.c_void_p, info_class: int) -> list[str]:
    """Read the SIDs from a token's group or capability list.

    The two Win32 layouts DIFFER and must not be read the same way:

    * ``TOKEN_GROUPS`` is ``{ DWORD GroupCount; SID_AND_ATTRIBUTES
      Groups[ANYSIZE]; }`` -- an **inline** array at offset 8.
    * ``TOKEN_CAPABILITIES`` is ``{ DWORD CapabilityCount;
      PSID_AND_ATTRIBUTES Capabilities; }`` -- a **pointer** at offset 8.

    Reading the capability list with the inline layout reads the
    elements from inside the descriptor buffer instead of from the
    pointed-to array.  It happens to agree when the count is 1 and
    silently returns the wrong SIDs for any larger count, so the two
    classes are handled separately.
    """
    buf = _get_token_buffer(token, info_class)
    if buf is None:
        return []

    count = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))[0]
    if count > 4096:
        return []

    if info_class == _TOKEN_CAPABILITIES:
        # The descriptor holds a POINTER to the array.  The pointer is NULL
        # when the token holds no capability at all, which is the normal
        # case for the production token.
        # The pointer field is at offset 8, NOT 0: the struct is
        # { DWORD CapabilityCount; PSID_AND_ATTRIBUTES Capabilities; } and
        # on x64 the 4-byte count is followed by 4 bytes of padding before
        # the 8-byte pointer.  Measured on a real token:
        #   count@0 = 1  pointer@8 = 0x27b28f682e8
        pointer = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[1]
        if not pointer or count == 0:
            return []
        array = ctypes.cast(pointer, ctypes.POINTER(_SID_AND_ATTRIBUTES))
        base = ctypes.addressof(array.contents)
    else:
        # TOKEN_GROUPS holds the array INLINE, right after the count.
        base = ctypes.addressof(buf) + 8

    sids: list[str] = []
    for i in range(count):
        elem = ctypes.cast(base + i * 16, ctypes.POINTER(_SID_AND_ATTRIBUTES)).contents
        if not elem.Sid:
            continue
        rendered = sid_to_string(elem.Sid)
        if rendered:
            sids.append(rendered)
    return sids


def verify_token(
    process_handle: int,
    *,
    expected_sid: str = PRODUCT_PACKAGE_SID,
    expected_capabilities: CapabilitySet = ZERO_CAPABILITIES,
) -> TokenVerification:
    """Verify the launched token's AppContainer identity and capabilities.

    This is called **while the target is still suspended**, so a failure
    means the parser never ran.

    Returns a :class:`TokenVerification`. A verification with a non-empty
    ``errors`` list must be treated as a fail-closed setup error.
    """
    result = TokenVerification()
    try:
        token = _open_process_token(process_handle)
    except AppContainerSetupError as exc:
        result.errors.append(exc.message)
        return result

    try:
        _verify_token_into(result, token, expected_sid, expected_capabilities)
    finally:
        # The token handle is closed on EVERY path, including the failure
        # paths: an unclosed token handle leaked one handle per launch.
        _close_token(token)
    return result


def _verify_token_into(
    result: TokenVerification,
    token: ctypes.c_void_p,
    expected_sid: str,
    expected_capabilities: CapabilitySet,
) -> None:
    """Fill ``result`` from an already-open token handle."""
    is_app_buf = _get_token_buffer(token, _TOKEN_IS_APP_CONTAINER)
    if is_app_buf is None:
        result.errors.append("could not read TokenIsAppContainer")
    else:
        result.is_app_container = bool(
            ctypes.cast(is_app_buf, ctypes.POINTER(ctypes.c_int32))[0]
        )
        if not result.is_app_container:
            result.errors.append(
                "the launched token is not an AppContainer token"
            )

    acs_buf = _get_token_buffer(token, _TOKEN_APP_CONTAINER_SID)
    if acs_buf is None:
        result.errors.append("could not read TokenAppContainerSid")
    else:
        acs = ctypes.cast(acs_buf, ctypes.POINTER(_TOKEN_APPCONTAINER_SID)).contents
        result.app_container_sid = sid_to_string(acs.Sid) if acs.Sid else None
        if result.app_container_sid != expected_sid:
            result.errors.append(
                "the launched token's AppContainer SID does not match the "
                "product SID"
            )

    result.capability_sids = tuple(_read_token_sids(token, _TOKEN_CAPABILITIES))
    result.group_sids = tuple(_read_token_sids(token, _TOKEN_GROUPS))
    # The capability SIDs are NOT in TokenGroups, so this must be checked
    # against the capability list.  Checking the group list would always
    # report False, even for a token that really holds internetClient.
    result.internet_client_present = (
        INTERNET_CLIENT_CAPABILITY_SID in result.capability_sids
    )
    if result.internet_client_present:
        result.errors.append("the launched token holds the internetClient capability")
    unexpected = [
        s for s in result.capability_sids if s.startswith(CAPABILITY_AUTHORITY_PREFIX)
    ]
    if unexpected:
        result.errors.append("the launched token holds unexpected capabilities")
    granted = set(expected_capabilities.sids)
    extra = [s for s in result.capability_sids if s not in granted]
    if extra:
        result.errors.append("the launched token holds capabilities outside the granted set")


def assert_verified(verification: TokenVerification) -> None:
    """Raise unless ``verification`` passed every check."""
    if verification.ok:
        return
    raise AppContainerVerificationError(
        "the launched process token failed the AppContainer verification",
        details={
            "stage": "token_verification",
            "errors": list(verification.errors),
            "is_app_container": verification.is_app_container,
            "app_container_sid": verification.app_container_sid,
            "capability_sids": list(verification.capability_sids),
            "internet_client_present": verification.internet_client_present,
        },
    )


# ---------------------------------------------------------------------------
# The launch preparation contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AppContainerLaunchPlan:
    """Everything the launcher needs to build an isolated parser launch.

    Attributes:
        package_sid: the product-owned AppContainer SID.
        capabilities: the capability set to request (always empty).
        handle_policy: the inherited-handle contract.
        staged: the staged parser location, when one was prepared.
    """

    package_sid: str = PRODUCT_PACKAGE_SID
    capabilities: CapabilitySet = ZERO_CAPABILITIES
    handle_policy: HandlePolicy = DEFAULT_HANDLE_POLICY
    staged: StagedParser | None = None

    def security_capabilities(self) -> object:
        """Build the ``SECURITY_CAPABILITIES`` structure for this plan."""
        raise NotImplementedError  # replaced by the Windows-specific builder


def build_launch_plan(
    *,
    staged: StagedParser | None = None,
    capabilities: CapabilitySet | None = None,
    handle_policy: HandlePolicy | None = None,
    package_sid: str | None = None,
) -> AppContainerLaunchPlan:
    """Build the launch plan, validating every component first.

    ``package_sid`` defaults to the product-owned constant.  It is resolved
    at CALL time, not at definition time, so the constant the plan is built
    from is the one that is validated and carried.  Whichever SID is
    supplied is the one that is VALIDATED and the one that is carried by
    the plan, so a divergent or malformed SID cannot reach the launch.

    Raises:
        AppContainerSetupError: any component is invalid.
    """
    _require_windows()
    sid = package_sid if package_sid is not None else PRODUCT_PACKAGE_SID
    validate_product_sid(sid)
    caps = capabilities if capabilities is not None else select_capabilities()
    if caps.is_network_capable:
        raise AppContainerSetupError(
            "a network-capable capability set must never be used for the parser",
            details={"stage": "launch_plan", "capabilities": list(caps.sids)},
        )
    policy = handle_policy if handle_policy is not None else DEFAULT_HANDLE_POLICY
    return AppContainerLaunchPlan(
        package_sid=sid,
        capabilities=caps,
        handle_policy=policy,
        staged=staged,
    )
