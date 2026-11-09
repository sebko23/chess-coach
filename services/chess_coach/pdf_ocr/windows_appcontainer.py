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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

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


def _windll(name: str) -> ctypes.CDLL:
    return ctypes.WinDLL(name, use_last_error=True)


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
    raw = ctypes.string_at(ctypes.cast(sid_ptr, ctypes.c_void_p), 8 + 6 + 8 * 4)
    revision = raw[0]
    count = raw[1]
    authority = int.from_bytes(raw[2:8], "big")
    subs = [
        int.from_bytes(raw[8 + i * 4:12 + i * 4], "little") for i in range(count)
    ]
    return "-".join([f"S-{revision}-{authority}"] + [str(v) for v in subs])


def parse_sid_string(sid_string: str) -> ctypes.c_void_p:
    """Parse a SID string into a SID pointer.

    Raises:
        AppContainerSetupError: the string is not a valid SID.
    """
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
                "win32_error": ctypes.get_last_error(),
                "stage": "sid_parse",
            },
        )
    return sid


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
        proc = subprocess.run(
            ["reg", *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AppContainerSetupError(
            "could not run reg.exe to register the AppContainer profile",
            details={"stage": "profile_registration", "error": str(exc)},
        ) from exc
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def profile_is_registered(sid_string: str = PRODUCT_PACKAGE_SID) -> bool:
    """Whether the AppContainer mapping for ``sid_string`` exists."""
    rc, out, _ = _run_reg(["query", f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}"])
    return rc == 0


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

    # --- 1. the AppContainer mapping ------------------------------------
    mapping_key = f"{_APP_CONTAINER_MAPPINGS_REG}\\{sid_string}"
    if profile_is_registered(sid_string):
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
        return (self.executable, *self.runtime_dirs)


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
        cmd = [
            "icacls", str(path), "/grant", f"*{sid_string}:(OI)(CI)({perms})",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, errors="replace",
                timeout=120, check=False,
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


# ---------------------------------------------------------------------------
# Parser staging
# ---------------------------------------------------------------------------

#: The directory the parser is staged into. It is **outside the user
#: profile**: an AppContainer token cannot traverse the user profile, so a
#: profile-resident executable is unlaunchable inside the container.
DEFAULT_STAGING_ROOT = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ChessCoach"

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
                "win32_error": ctypes.get_last_error(),
            },
        )
    return token


def _get_token_buffer(token: ctypes.c_void_p, info_class: int) -> ctypes.Array | None:
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
    buf = _get_token_buffer(token, info_class)
    if buf is None:
        return []
    count = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))[0]
    if count > 4096:
        return []
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
    result.internet_client_present = INTERNET_CLIENT_CAPABILITY_SID in result.group_sids
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
    return result


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

    def security_capabilities(self) -> "object":
        """Build the ``SECURITY_CAPABILITIES`` structure for this plan."""
        raise NotImplementedError  # replaced by the Windows-specific builder


def build_launch_plan(
    *,
    staged: StagedParser | None = None,
    capabilities: CapabilitySet | None = None,
    handle_policy: HandlePolicy | None = None,
) -> AppContainerLaunchPlan:
    """Build the launch plan, validating every component first.

    Raises:
        AppContainerSetupError: any component is invalid.
    """
    _require_windows()
    validate_product_sid()
    caps = capabilities if capabilities is not None else select_capabilities()
    if caps.is_network_capable:
        raise AppContainerSetupError(
            "a network-capable capability set must never be used for the parser",
            details={"stage": "launch_plan", "capabilities": list(caps.sids)},
        )
    policy = handle_policy if handle_policy is not None else DEFAULT_HANDLE_POLICY
    return AppContainerLaunchPlan(
        package_sid=PRODUCT_PACKAGE_SID,
        capabilities=caps,
        handle_policy=policy,
        staged=staged,
    )
