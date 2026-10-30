#!/usr/bin/env python3
"""Probe which mount-propagation strategy works in THIS environment.

Run as: ``probe_mount_strategies.py <strategy>``

Each strategy runs in a FRESH process, because ``unshare(CLONE_NEWUSER)``
cannot be undone and a failed attempt changes what the next attempt sees.

The strategies cover the ways a container can make its root read-only
inside a user namespace. The launcher needs one that works both on a
developer's Docker Desktop and on a CI runner.

This is a DIAGNOSTIC: it prints what happened and exits 0 on success,
1 on failure. It never installs a fallback.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import errno as _errno
import os
import sys

CLONE_NEWNS = 0x00020000
CLONE_NEWUSER = 0x10000000
CLONE_NEWNET = 0x40000000

MS_RDONLY = 1
MS_REMOUNT = 32
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18
MS_SLAVE = 1 << 19
MS_SHARED = 1 << 20


def _libc() -> ctypes.CDLL:
    lib = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    lib.unshare.argtypes = [ctypes.c_int]
    lib.unshare.restype = ctypes.c_int
    lib.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    lib.mount.restype = ctypes.c_int
    return lib


def _mount(
    lib: ctypes.CDLL,
    source: bytes | None,
    target: bytes,
    flags: int,
    fstype: bytes | None = None,
) -> int:
    ctypes.set_errno(0)
    rc = lib.mount(source, target, fstype, flags, None)
    return rc


def _propagation(path: str = "/") -> str:
    """The propagation state of a mount, from /proc/self/mountinfo."""
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 6 or parts[4] != path:
                    continue
                optional = parts[6] if len(parts) > 6 else ""
                marks = [
                    f
                    for f in optional.split(",")
                    if f.split(":")[0] in {"shared", "master", "private", "slave", "unbindable"}
                ]
                return ",".join(marks) if marks else "none"
    except OSError:
        pass
    return "unknown"


def _caps() -> str:
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("CapEff:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def _apparmor_status() -> str:
    """The AppArmor status of this process, for diagnostics.

    GitHub's hosted runners ship an AppArmor profile that can deny
    `mount` inside an unprivileged user namespace even when the kernel
    capability check would pass. The status file names the profile so a
    CI log shows which LSM, if any, is in force.
    """
    try:
        with open("/proc/self/attr/current", encoding="utf-8") as handle:
            value = handle.read().strip()
        if value and value != "unconfined":
            return value
        return "unconfined"
    except OSError:
        return "unknown"


def _security_opts() -> str:
    """The container's security options, for diagnostics."""
    parts = []
    for path, label in (("/proc/self/attr/current", "apparmor"),):
        try:
            with open(path, encoding="utf-8") as handle:
                parts.append(f"{label}={handle.read().strip()}")
        except OSError:
            parts.append(f"{label}=unavailable")
    return " ".join(parts)


def _report(stage: str, rc: int) -> bool:
    err = ctypes.get_errno()
    name = _errno.errorcode.get(err, str(err)) if err else ""
    ok = rc == 0
    print(f"  {stage}: rc={rc} errno={err} {name} {'OK' if ok else 'FAIL'}", flush=True)
    return ok


def _enter_userns(lib: ctypes.CDLL, *, also_netns: bool = True) -> bool:
    flags = CLONE_NEWUSER | CLONE_NEWNS
    if also_netns:
        flags |= CLONE_NEWNET
    # The deployment identity must be captured BEFORE the unshare: once
    # CLONE_NEWUSER is active the uid map is empty and getuid() reports
    # the overflow uid 65534, which the kernel rejects as a map target.
    uid = os.getuid()
    gid = os.getgid()
    ctypes.set_errno(0)
    rc = lib.unshare(flags)
    if rc != 0:
        return _report("unshare", rc)
    try:
        with open("/proc/self/setgroups", "w") as handle:
            handle.write("deny")
        with open("/proc/self/uid_map", "w") as handle:
            handle.write(f"{uid} {uid} 1\n")
        with open("/proc/self/gid_map", "w") as handle:
            handle.write(f"{gid} {gid} 1\n")
    except OSError as exc:
        print(f"  map: FAILED {exc}", flush=True)
        return False
    print(f"  map: OK caps={_caps()} propagation(/)={_propagation('/')}", flush=True)
    # The profile AFTER the transition is what governs the mount: on
    # Ubuntu 24.04 the process transitions into `unprivileged_userns`
    # when it creates a user namespace.
    print(f"  apparmor AFTER unshare: {_apparmor_status()}", flush=True)
    return True


def strategy_private(lib: ctypes.CDLL) -> bool:
    """The current launcher strategy."""
    if not _enter_userns(lib):
        return False
    return _report("mount(/, MS_REC|MS_PRIVATE)", _mount(lib, b"none", b"/", MS_REC | MS_PRIVATE))


def strategy_slave(lib: ctypes.CDLL) -> bool:
    """Make the root a SLAVE instead of fully private."""
    if not _enter_userns(lib):
        return False
    return _report("mount(/, MS_REC|MS_SLAVE)", _mount(lib, b"none", b"/", MS_REC | MS_SLAVE))


def strategy_bind_then_private(lib: ctypes.CDLL) -> bool:
    """Bind / onto itself, then make the NEW mount private.

    A bind mount created inside the new user namespace is not LOCKED, so
    the propagation change on it is permitted even when the inherited
    root is.
    """
    if not _enter_userns(lib):
        return False
    if not _report("mount(/, MS_BIND)", _mount(lib, b"/", b"/", MS_BIND)):
        return False
    return _report("mount(/, MS_REC|MS_PRIVATE)", _mount(lib, b"none", b"/", MS_REC | MS_PRIVATE))


def strategy_separate_mountns(lib: ctypes.CDLL) -> bool:
    """Unshare the mount namespace in a SECOND call, after the userns."""
    if not _enter_userns(lib, also_netns=True):
        return False
    # A second, dedicated mount-namespace unshare.
    ctypes.set_errno(0)
    rc = lib.unshare(CLONE_NEWNS)
    if rc != 0:
        return _report("unshare(CLONE_NEWNS) #2", rc)
    print(f"  second mountns: OK caps={_caps()}", flush=True)
    return _report("mount(/, MS_REC|MS_PRIVATE)", _mount(lib, b"none", b"/", MS_REC | MS_PRIVATE))


def strategy_tmpfs_root(lib: ctypes.CDLL) -> bool:
    """Mount a fresh tmpfs and pivot_root into it.

    The new root is created by this process inside its own user
    namespace, so it is never LOCKED and the old root is discarded
    entirely rather than made read-only.
    """
    if not _enter_userns(lib):
        return False
    # The mountpoint must exist before the mount, and the container's
    # root filesystem may be read-only, so it is created under /tmp.
    newroot = "/tmp/newroot"  # noqa: S108 -- a mountpoint, not a data file
    try:
        os.makedirs(f"{newroot}/oldroot", exist_ok=True)
    except OSError as exc:
        print(f"  mkdir {newroot}: FAILED {exc}", flush=True)
        return False
    if not _report(
        f"mount(tmpfs, {newroot})",
        _mount(lib, None, newroot.encode(), 0, fstype=b"tmpfs"),
    ):
        return False
    # After the tmpfs mount the new root is EMPTY, so the "put_old"
    # directory has to be created INSIDE it.
    try:
        os.makedirs(f"{newroot}/oldroot", exist_ok=True)
    except OSError as exc:
        print(f"  mkdir {newroot}/oldroot: FAILED {exc}", flush=True)
        return False
    # pivot_root(new_root, put_old)
    libc = _libc()
    libc.pivot_root.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    libc.pivot_root.restype = ctypes.c_int
    ctypes.set_errno(0)
    rc = libc.pivot_root(newroot.encode(), f"{newroot}/oldroot".encode())
    if rc != 0:
        return _report("pivot_root", rc)
    os.chdir("/")
    rc = _mount(lib, b"none", b"/", MS_REC | MS_PRIVATE)
    return _report("mount(/, MS_REC|MS_PRIVATE) after pivot", rc)


def strategy_remount_ro(lib: ctypes.CDLL) -> bool:
    """Can the root be remounted read-only WITHOUT changing propagation?

    This is the interesting alternative: if the propagation change is
    what the kernel refuses, a read-only remount over the existing root
    might still be permitted.
    """
    if not _enter_userns(lib):
        return False
    rc = _mount(lib, b"none", b"/", MS_REMOUNT | MS_BIND | MS_RDONLY)
    return _report("mount(/, MS_REMOUNT|MS_BIND|MS_RDONLY)", rc)


def strategy_no_userns(lib: ctypes.CDLL) -> bool:
    """Can mount() be called WITHOUT a user namespace?

    This is the control that separates the two possible causes. If
    mount() fails here too, the environment's LSM (or seccomp) denies
    mount outright. If it succeeds, the denial is specific to mounts
    performed inside an unprivileged user namespace.
    """
    return _report(
        "mount(tmpfs, /tmp/probe-root) WITHOUT a userns",
        _mount(lib, b"tmpfs", b"/tmp/probe-root", 0),
    )


def strategy_no_userns_remount(lib: ctypes.CDLL) -> bool:
    """Can the root be remounted read-only WITHOUT a user namespace?"""
    return _report(
        "mount(/, MS_REMOUNT|MS_BIND|MS_RDONLY) WITHOUT a userns",
        _mount(lib, b"none", b"/", MS_REMOUNT | MS_BIND | MS_RDONLY),
    )


def strategy_lsm_report(lib: ctypes.CDLL) -> bool:
    """Report the LSM/AppArmor state, without performing any mount.

    Ubuntu 24.04 restricts unprivileged user namespaces with an AppArmor
    profile. Creating the namespace is allowed, but `mount` inside it is
    denied, which is why EVERY mount strategy fails there with EACCES.
    This reports the state so a CI log shows it.
    """
    print(f"  apparmor={_apparmor_status()}", flush=True)
    print(f"  capabilities={_caps()}", flush=True)
    print(f"  propagation(/)={_propagation('/')}", flush=True)
    for knob in (
        "/proc/sys/kernel/unprivileged_userns_clone",
        "/proc/sys/user/max_user_namespaces",
    ):
        try:
            with open(knob, encoding="utf-8") as handle:
                print(f"  {knob}={handle.read().strip()}", flush=True)
        except OSError:
            print(f"  {knob}=unavailable", flush=True)
    return True


def _cap_status() -> dict[str, str]:
    """Every capability set the process holds, for diagnostics.

    The mount stage needs CAP_SYS_ADMIN. Inside a new user namespace
    the process holds it (CapEff shows it), but a mount operation on a
    mount INHERITED from the parent namespace is governed by the
    parent's rules: if the inherited mount is LOCKED, the operation
    requires CAP_SYS_ADMIN in the namespace that owns it.
    """
    out: dict[str, str] = {}
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                for key in (
                    "CapInh",
                    "CapPrm",
                    "CapEff",
                    "CapBnd",
                    "CapAmb",
                    "NoNewPrivs",
                    "Seccomp",
                ):
                    if line.startswith(f"{key}:"):
                        out[key] = line.split(":", 1)[1].strip()
    except OSError:
        pass
    return out


def strategy_cap_status(lib: ctypes.CDLL) -> bool:
    """Report every capability set, before and after the unshare.

    This distinguishes the two possible causes of an EACCES on mount:
    a missing capability, versus an LSM policy. The kernel's AppArmor
    audit log is empty for the denial, so the capability sets are the
    decisive measurement.
    """
    before = _cap_status()
    print("  BEFORE unshare:", before, flush=True)
    if not _enter_userns(lib):
        return False
    after = _cap_status()
    print("  AFTER  unshare:", after, flush=True)
    print(f"  parent ns id: {_ns_id('user')}", flush=True)
    print(f"  mount ns id : {_ns_id('mnt')}", flush=True)
    return True


def _ns_id(kind: str) -> str:
    """The kernel's id for one of this process's namespaces."""
    try:
        with open(f"/proc/self/ns/{kind}", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return "unknown"


def strategy_complain_mode(lib: ctypes.CDLL) -> bool:
    """Switch the LSM to complain mode and retry the mount.

    In complain mode the operation is ALLOWED but every denial is
    logged. If the mount succeeds once the profile is in complain
    mode, the LSM was the denyer; if it still fails with EACCES, the
    kernel is.

    This is a diagnostic and it never changes the production
    behaviour: the launcher still fails closed.
    """
    try:
        with open("/proc/self/attr/current", "w", encoding="utf-8") as handle:
            handle.write("complain")
        print("  switched the profile to complain mode", flush=True)
    except OSError as exc:
        print(f"  could not switch to complain mode: {exc}", flush=True)
        return False
    if not _enter_userns(lib):
        return False
    rc = _mount(lib, b"none", b"/", MS_REC | MS_PRIVATE)
    ok = _report("mount(/, MS_REC|MS_PRIVATE) in complain mode", rc)
    print(f"  => {'AppArmor WAS the denyer' if ok else 'the KERNEL is the denyer'}", flush=True)
    return ok


def _ns_owner_relationship() -> dict[str, str]:
    """Which user namespace owns this process's PID and mount namespaces.

    The kernel permits a mount only when the caller holds
    CAP_SYS_ADMIN in the user namespace that owns the mount namespace
    it modifies, and -- for a mount namespace the caller did not
    create -- in the user namespace that owns the PID namespace.

    A container runtime creates the PID namespace in the HOST's user
    namespace. The launcher creates its own user namespace, so the
    two differ, and the capability the launcher holds in ITS namespace
    is not the one the kernel asks for.

    This reports the ids so the relationship can be compared.
    """
    out: dict[str, str] = {}
    for kind in ("user", "mnt", "pid", "net"):
        try:
            out[kind] = os.readlink(f"/proc/self/ns/{kind}")
        except OSError:
            out[kind] = "unavailable"
    return out


def strategy_ns_owners(lib: ctypes.CDLL) -> bool:
    """Report the namespace ids BEFORE and AFTER the unshare.

    The mount is permitted only when the caller holds CAP_SYS_ADMIN in
    the user namespace that owns the PID namespace. The ids make the
    ownership relationship visible: if the user namespace changes but
    the PID namespace does not, the PID namespace is owned by the
    PARENT's user namespace and the launcher can never satisfy the
    rule.
    """
    before = _ns_owner_relationship()
    print(f"  BEFORE: {before}", flush=True)
    if not _enter_userns(lib):
        return False
    after = _ns_owner_relationship()
    print(f"  AFTER : {after}", flush=True)
    print(f"  user ns changed : {before.get('user') != after.get('user')}", flush=True)
    print(f"  pid  ns changed : {before.get('pid') != after.get('pid')}", flush=True)
    print(f"  mnt  ns changed : {before.get('mnt') != after.get('mnt')}", flush=True)
    return True


STRATEGIES = {
    "private": strategy_private,
    "slave": strategy_slave,
    "bind_then_private": strategy_bind_then_private,
    "separate_mountns": strategy_separate_mountns,
    "tmpfs_root": strategy_tmpfs_root,
    "remount_ro": strategy_remount_ro,
    "no_userns": strategy_no_userns,
    "no_userns_remount": strategy_no_userns_remount,
    "lsm_report": strategy_lsm_report,
    "cap_status": strategy_cap_status,
    "complain_mode": strategy_complain_mode,
    "ns_owners": strategy_ns_owners,
}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: probe_mount_strategies.py <strategy>", flush=True)
        print("strategies: " + ", ".join(sorted(STRATEGIES)), flush=True)
        return 2
    name = sys.argv[1]
    if name not in STRATEGIES:
        print(f"unknown strategy: {name}", flush=True)
        return 2
    print(f"=== strategy: {name} ===", flush=True)
    print(f"  before: caps={_caps()} propagation(/)={_propagation('/')}", flush=True)
    print(f"  lsm: {_security_opts()}", flush=True)
    lib = _libc()
    ok = STRATEGIES[name](lib)
    print(f"=== {name}: {'SUCCESS' if ok else 'FAILED'} ===", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
