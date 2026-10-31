#!/usr/bin/env python3
"""Prove the shipped seccomp profile is a narrow delta on the pinned
Docker/Moby default.

Checks, in order:

1. The shipped profile's rules are exactly the pinned Moby default's rules
   PLUS the narrow ALLOW rules -- no Docker default rule was removed,
   reordered, or modified.
2. The narrow rules name ONLY the namespace/mount/identity syscalls the
   launcher needs.
3. The dangerous capability-gated operations remain denied for a non-root
   process: `bpf`, `perf_event_open`, `fsopen`, `fsmount`, `fsconfig`,
   `open_tree`, `move_mount`, `fspick`, `mount_setattr`,
   `lookup_dcookie`, `fanotify_init`, `quotactl`, `setdomainname`,
   `sethostname`, `syslog`.

Exit 0 only if every check passes.
"""
import json
import sys
import urllib.request
from pathlib import Path

MOBY_TAG = "v26.1.4"
URL = (
    f"https://raw.githubusercontent.com/moby/moby/{MOBY_TAG}/"
    "profiles/seccomp/default.json"
)

#: The syscalls the launcher needs. Anything outside this set in a narrow
#: rule is a broadening.
REQUIRED = {
    # namespace lifecycle
    "unshare", "clone", "clone3", "setns",
    # mount policy
    "mount", "umount2", "pivot_root", "chroot",
    # identity mapping
    "setuid", "setgid", "setresuid", "setresgid", "setgroups",
    "setfsuid", "setfsgid", "setreuid", "setregid",
}

#: Operations that must remain denied to a non-root process.
MUST_REMAIN_DENIED = {
    "bpf", "perf_event_open", "fsopen", "fsmount", "fsconfig",
    "open_tree", "move_mount", "fspick", "mount_setattr",
    "lookup_dcookie", "fanotify_init", "quotactl", "quotactl_fd",
    "setdomainname", "sethostname", "syslog",
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def main() -> int:
    shipped_path = Path(sys.argv[1])
    shipped = json.loads(shipped_path.read_text(encoding="utf-8"))

    print(f"=== 0. fetch the pinned Docker/Moby default ({MOBY_TAG}) ===")
    with urllib.request.urlopen(URL, timeout=180) as resp:
        default = json.loads(resp.read().decode())
    print(f"  default syscall groups: {len(default['syscalls'])}")
    print(f"  shipped syscall groups: {len(shipped['syscalls'])}")

    # ------------------------------------------------------------------
    # 1. the shipped profile is the default PLUS narrow rules
    # ------------------------------------------------------------------
    shipped_groups = shipped["syscalls"]
    default_groups = default["syscalls"]
    n_narrow = len(shipped_groups) - len(default_groups)
    if n_narrow <= 0:
        fail(f"the shipped profile has no narrow additions ({n_narrow})")
    narrow = shipped_groups[:n_narrow]
    remainder = shipped_groups[n_narrow:]
    print(f"\n=== 1. narrow additions: {n_narrow} ===")
    if remainder != default_groups:
        # Find the first difference so the report is actionable.
        for i, (a, b) in enumerate(zip(remainder, default_groups, strict=False)):
            if a != b:
                fail(f"the shipped profile modifies Docker default rule {i}: "
                     f"{json.dumps(a)[:120]} != {json.dumps(b)[:120]}")
        fail("the shipped profile's default rules differ in length")
    print("  OK: every Docker default rule is preserved byte-for-byte, in order")

    # ------------------------------------------------------------------
    # 2. the narrow rules name ONLY the required syscalls
    # ------------------------------------------------------------------
    print("\n=== 2. the narrow rules name only the required syscalls ===")
    narrow_names: set[str] = set()
    for rule in narrow:
        if rule.get("action") != "SCMP_ACT_ALLOW":
            fail(f"a narrow rule is not an ALLOW: {json.dumps(rule)[:120]}")
        if rule.get("excludes"):
            fail(f"a narrow rule carries a caps exclusion, so a non-root "
                 f"process would not be covered: {json.dumps(rule)[:160]}")
        if (rule.get("includes") or {}).get("caps"):
            fail(f"a narrow rule carries a caps 'includes' gate, so a "
                 f"non-root process would not be covered: "
                 f"{json.dumps(rule)[:160]}")
        narrow_names.update(rule.get("names", []))
    extra = sorted(narrow_names - REQUIRED)
    if extra:
        fail(f"the narrow rules name syscalls outside the required set: {extra}")
    missing = sorted(REQUIRED - narrow_names)
    if missing:
        fail(f"the narrow rules do not cover: {missing}")
    print(f"  OK: the narrow rules name exactly {len(narrow_names)} required syscalls")
    for rule in narrow:
        args = rule.get("args")
        print(f"    {rule['names']}" + (f" args={json.dumps(args)}" if args else ""))

    # ------------------------------------------------------------------
    # 3. the dangerous operations remain denied for a non-root process
    # ------------------------------------------------------------------
    print("\n=== 3. the dangerous operations remain denied ===")
    # A syscall is granted to a NON-ROOT process only if it appears in an
    # ALLOW rule that applies to a process WITHOUT CAP_SYS_ADMIN.
    #
    # Docker's default expresses the capability gate in EITHER direction:
    #   * "includes": {"caps": ["CAP_SYS_ADMIN"]} -- the rule applies ONLY
    #     to processes that HAVE the capability. A non-root process does
    #     not match, so the syscall falls through to the profile's default
    #     action (EPERM).
    #   * "excludes": {"caps": ["CAP_SYS_ADMIN"]} -- the rule applies to
    #     everyone EXCEPT those with the capability. A non-root process
    #     DOES match, so the syscall would be allowed.
    #
    # A rule grants a non-root process only when it has neither an
    # `includes.caps` gate nor an `excludes.caps` gate naming a
    # capability the process lacks.
    # The capabilities the supported deployment's backend process holds.
    # It runs as UID 1000 with no host CAP_SYS_ADMIN and an empty
    # CapEff (measured), so it holds NONE of these.
    DEPLOYMENT_CAPABILITIES: set[str] = set()

    def grants_to_non_root(rule: dict) -> bool:
        """Does this ALLOW rule apply to a process with no capabilities?

        Docker expresses a capability gate in two directions:

        * ``includes: {"caps": ["CAP_X"]}`` -- the rule applies ONLY to
          processes that HOLD CAP_X. A process without CAP_X does not
          match the rule, so the syscall falls through to the profile's
          ``defaultAction`` (SCMP_ACT_ERRNO). This is the form Docker
          uses for ``bpf``/``perf_event_open``/the mount-namespace escape
          syscalls, and it is what keeps them denied for UID 1000.
        * ``excludes: {"caps": ["CAP_X"]}`` -- the rule applies to everyone
          EXCEPT processes holding CAP_X. A process without CAP_X DOES
          match, so the syscall would be allowed.
        """
        if rule.get("action") != "SCMP_ACT_ALLOW":
            return False
        includes = set((rule.get("includes") or {}).get("caps") or [])
        if includes:
            # Applies only to capability holders. We hold none, so it does
            # NOT apply to us.
            return bool(includes & DEPLOYMENT_CAPABILITIES)
        excludes = set((rule.get("excludes") or {}).get("caps") or [])
        if excludes:
            # Applies to everyone except capability holders. We are not a
            # holder, so it DOES apply to us.
            return True
        return True

    unconditional: set[str] = set()
    for rule in shipped["syscalls"]:
        if grants_to_non_root(rule):
            unconditional.update(rule.get("names", []))
    still_denied = sorted(MUST_REMAIN_DENIED - unconditional)
    leaked = sorted(MUST_REMAIN_DENIED & unconditional)
    if leaked:
        fail(f"these dangerous operations are now granted unconditionally: {leaked}")
    print(f"  OK: {len(still_denied)} dangerous operations remain gated behind "
          f"CAP_SYS_ADMIN (and therefore denied to UID 1000)")
    print(f"    still denied: {still_denied}")

    print("\n=== SECCOMP PROFILE VERIFIED: narrow delta on the pinned default ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
