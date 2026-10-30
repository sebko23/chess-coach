# BBF — FU-20 Linux Phase 1: network isolation and explicit Windows refusal

**Date:** 2026-10-29
**Finding:** FU-20 (A-F11 property 2 — no network access)
**Status:** implementation + proof; FU-20 release-scope closure is a separate stage

---

## 1. The defect

A-F11 property 2 requires the PDF parser subprocess to run with **no
network access**. The implementation did not enforce that.

**Linux.** `set_network_isolation_preexec()` called `os.setsid()` and then
attempted `unshare(CLONE_NEWNET)` through libc. When the syscall failed it
**silently fell through to removing proxy environment variables**. Proxy
stripping is defense in depth, never network denial: it prevents neither a
direct socket nor LAN, host-local, or loopback access. The existing tests
proved only that `setsid()` ran and that `unshare` was *requested* — not
that a namespace existed or that traffic was denied.

**Windows.** After FU-22 B2, the Windows path calls
`run_in_windows_job(args, stdin_bytes=…, timeout_seconds=…, limit_bytes=…,
cwd=tmpdir)` with **no `env` argument**, so it inherits the parent
environment, and the composed Linux `preexec_fn` network helper is never
invoked. Windows therefore applied **no network policy at all**, and the
ledger's claim that Windows strips proxy variables was false — the code
path was unreachable.

**No CI proof.** No check demonstrated that a parser could not reach a
network.

## 2. The architecture

One dedicated Linux launcher owns the whole containment boundary.

`services/chess_coach/pdf_ocr/linux_sandbox.py` performs, in order, before
the parser is executed:

1. `unshare(CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS)` — **exactly once**.
2. UID/GID **identity** mapping (`1000 1000 1`), preserving the deployment
   identity's ownership of the artifact path. `setgroups` is denied before
   the GID map is written, as the kernel requires.
3. Private mount propagation (`MS_REC | MS_PRIVATE` on `/`).
4. Root filesystem remounted read-only.
5. The artifact directory bind-mounted, then remounted writable — a bind of
   a read-only source inherits the read-only flag, so it needs its own
   `MS_REMOUNT | MS_BIND` pass.
6. Descriptor hygiene: every descriptor above 2 closed, and a
   **socket-valued standard descriptor rejected**. `close_fds=True` alone is
   not accepted as proof — it does not *detect* a socket on fd 0/1/2, which
   would hand the parser a live network handle.
7. The 2 GiB per-process `RLIMIT_AS` applied and read back.
8. `exec` of the parser.

Every stage is checked. **The first failure aborts before `exec`**, is
reported on a dedicated status channel as `SETUP_FAILURE <stage>\x00
<message>`, and surfaces as a typed error naming the stage. There is no
fallback to direct execution, proxy stripping, a source-tree copy, or an
unconstrained subprocess.

### Why a launcher rather than `preexec_fn`

`preexec_fn` runs inside the forked child and cannot report *which* stage
failed through a dedicated channel, so a setup failure would be
indistinguishable from a parser failure. The launcher is a separate program
invoked with a **controlled argv protocol** (no shell string is ever
evaluated) and owns the namespace lifecycle across the `fork`/`exec`
boundary.

### Retired helpers

`set_rlimit_as_preexec`, `set_network_isolation_preexec`, and
`set_fs_isolation_preexec` are removed from the production composition.
There is now **one namespace owner and one `setsid()`**. The proxy-only
fallback and the filesystem no-op fallback are gone.

## 3. The deployment policy

Docker's default seccomp profile allows `unshare`, `clone`, `mount`, and
`setns` **only under `CAP_SYS_ADMIN`**. The supported deployment runs the
backend as **non-root UID 1000 without host `CAP_SYS_ADMIN`** and without
`privileged: true`, so the default profile denies the namespace and the
launcher would (correctly) fail closed — making PDF parsing unusable.

`infra/docker/seccomp-backend.json` is Docker's default profile with
**three narrow ALLOW rules prepended** for exactly the syscalls the
launcher needs:

| Rule | Syscalls |
|---|---|
| namespace / mount / identity | `unshare`, `clone`, `clone3`, `setns`, `mount`, `umount2`, `pivot_root`, `chroot`, `setuid`, `setgid`, `setresuid`, `setresgid`, `setgroups`, `setfsuid`, `setfsgid`, `setreuid`, `setregid` |
| clone with the launcher's flags | `clone`, `clone3` with `CLONE_NEWUSER\|CLONE_NEWNET\|CLONE_NEWNS` |
| unshare with the launcher's flags | `unshare` with the same flags |

`scripts/dev/verify_seccomp_profile.py` proves the profile is a narrow
delta on the pinned Moby/Docker **26.1.4** default: every Docker default
rule is preserved byte-for-byte and in order; the narrow rules name only
the required syscalls and carry no capability gate; and the dangerous
operations — `bpf`, `perf_event_open`, `fsopen`, `fsmount`, `fsconfig`,
`open_tree`, `move_mount`, `fspick`, `mount_setattr`, `lookup_dcookie`,
`fanotify_init`, `quotactl`, `setdomainname`, `sethostname`, `syslog` —
**remain gated behind `CAP_SYS_ADMIN`** and therefore denied to UID 1000.

`docker-compose.yml` wires the profile onto the backend service only. The
Qdrant sidecar and every other service are unchanged. No host
`CAP_SYS_ADMIN`, no `privileged: true`, no broad seccomp relaxation.

**Local non-container execution** does not provide the boundary and must
fail closed. The launcher reports the failing stage rather than degrading.

### The host AppArmor policy is part of the deployment contract

The seccomp profile governs *which syscalls* the container may call. A
second, independent confinement governs *whether a permitted syscall is
allowed in this context*: the host's AppArmor policy.

**Ubuntu 24.04 and later restrict unprivileged user namespaces by
default.** A process that creates a user namespace transitions into
AppArmor's `unprivileged_userns` profile, which grants `userns`,
`network`, `file rwlkm`, `signal`, `dbus`, `unix`, `mqueue` and
`ptrace` — but **not `mount`**. The launcher's containment sequence
needs `mount` inside that namespace, so on such a host the launcher
fails closed at the mount stage with `EACCES`.

This was measured on the GitHub-hosted `ubuntu-latest` runner
(Ubuntu 24.04.5). **Every** mount variant was refused, including a
brand-new tmpfs with no inheritance involved:

| Operation | Result on the runner |
|---|---|
| `mount("/", MS_REC\|MS_PRIVATE)` | `EACCES` |
| `mount("/", MS_REC\|MS_SLAVE)` | `EACCES` |
| `mount("/", MS_BIND)` | `EACCES` |
| `mount(tmpfs, "/tmp/newroot")` | `EACCES` |
| `mount("/", MS_REMOUNT\|MS_BIND\|MS_RDONLY)` | `EACCES` |

The same strategies all succeed on a host without the restriction.

**The denial is the kernel's mount-namespace rule, not the LSM and not
a missing capability.** Three measurements establish this:

* The AppArmor `DENIED` audit log is **empty** for the denial. A denial
  by AppArmor always produces an `apparmor="DENIED"` record, so the
  LSM is not the denyer.
* The container runs under `docker-default (enforce)`, and the
  capability sets are **identical** on the runner and on a working
  machine: `CapPrm` and `CapEff` both become the full
  `0x000001ffffffffff` after the unshare, `CapBnd` likewise, and
  `Seccomp: 2` (filter mode) in both.
* The mount that the launcher operates on is **inherited** from the
  container's parent mount namespace. A mount inherited into a new
  mount namespace is *locked* when the creating process lacked
  `CAP_SYS_ADMIN` in the namespace that owns it. A locked mount cannot
  have its propagation changed, and the kernel refuses the operation
  with `EACCES`.

The last point is the deployment requirement, and it is the same one
the AppArmor policy expresses: **the host's mount namespace must let a
user-namespace process modify the mounts it inherits.**

**Operational requirement.** The supported Linux deployment therefore
needs a host AppArmor policy that permits `mount` inside an
unprivileged user namespace. Two ways to satisfy it:

1. Ship the `unprivileged_userns` profile from AppArmor upstream, which
   grants broad namespace privileges to unprivileged namespace users.
2. Ship a narrower profile that grants `userns` and `mount` only.

`infra/docker/apparmor-fu20-ci.profile` is the second form, used by the
`linux-network-isolation` CI job through
`--security-opt apparmor=...`. It is **not** `flags=(unconfined)`, does
not disable AppArmor and grants no capability; the container still runs
as UID 1000 with no host `CAP_SYS_ADMIN`, and the shipped seccomp
profile still governs which syscalls are permitted at all.

The production Compose deployment does **not** force this profile: the
host's AppArmor policy is the operator's to configure. A deployment
whose policy denies `mount` inside an unprivileged user namespace will
fail closed at the mount stage, and the PDF route will report
`internal.network_isolation_setup_failed` rather than parse without
the boundary.

## 4. The error taxonomy

| Outcome | Condition | HTTP | ADR-0002 code |
|---|---|---|---|
| **Windows network-isolation refusal** | no proven no-network boundary | **501** | `internal.not_implemented` |
| **Linux isolation setup failure** | a containment stage failed | **500** | `internal.network_isolation_setup_failed` |
| Memory limit | `RLIMIT_AS` / Job per-process cap hit | 422 | (existing) |
| Timeout | budget exceeded | 504 | (existing) |
| Parser failure | nonzero exit / stderr | 422 | (existing) |
| Malformed PDF | bad magic bytes | 400 | (existing) |

The two new outcomes are **deliberately distinct**: an unsupported
*platform* is not the same condition as a blocked or misconfigured
*deployment*, and operators and telemetry need to tell them apart.

The Linux setup failure names the exact stage that failed
(`namespace_creation`, `uid_map`, `gid_map`, `setgroups_denial`,
`mount_private_propagation`, `mount_root_read_only`, `mount_artifact_bind`,
`mount_artifact_writable`, `artifact_not_writable`,
`root_filesystem_writable`, `socket_valued_standard_descriptor`,
`memory_limit`, `exec`).

## 5. The proof

`scripts/dev/verify_linux_network_isolation.py` runs inside the **production
container**, as **UID 1000**, with the **shipped seccomp profile**, against
a **controlled reachable endpoint** (a real TCP + UDP echo server).

* An **unrestricted control** runs the same probe without the launcher. It
  **must connect**; if it does not, the run is invalid and the job fails.
* The **restricted** probe runs through the production launcher.

### Measured (production container, shipped profile, UID 1000)

| Property | Result |
|---|---|
| `unshare(CLONE_NEWUSER\|CLONE_NEWNET\|CLONE_NEWNS)` | `rc=0` |
| Host `CapEff` | `0000000000000000` (no host `CAP_SYS_ADMIN`) |
| Identity after mapping | `uid=1000 gid=1000` (preserved) |
| Capabilities in the new user namespace | `0x000001ffffffffff` (confined) |
| Mount propagation private | `rc=0` |
| Root remounted read-only | `rc=0`; ordinary root write → `EROFS` |
| Artifact path | writable |
| Non-standard descriptors | closed |
| `RLIMIT_AS` | `2147483648` (2 GiB), read back |
| New network namespace interfaces | `['lo']` only |

### End-to-end restricted-versus-unrestricted run

The control and the restricted parser run in the **same job**, against the
**same controlled endpoint** (`172.18.0.2:18099`). The unrestricted control
**connected**, so the run is valid.

| Probe | Unrestricted control | Restricted (through the launcher) |
|---|---|---|
| Status channel | n/a | `OK` (setup reported success) |
| Parser exit code | n/a | `0` |
| `/proc/self/ns/net` | `4026532680` | `4026532753` (**differs**) |
| Interfaces | `['lo', 'eth0']` | `['lo']` |
| UID | `1000` | `1000` |
| TCP to the endpoint | **connected** (`TCP_ECHO:P`) | **denied** — `ENETUNREACH` (errno 101) |
| UDP to the endpoint | **echoed** (`UDP_ECHO:P`) | **denied** — `ENETUNREACH` (errno 101) |
| DNS query to the resolver (`127.0.0.11:53`) | **answered** (61 bytes) | **denied** — `ENETUNREACH` (errno 101) |
| Name resolution (via `/etc/hosts`) | resolved | resolved — a **local file read**, not network egress |
| Child descendant | **connected** | **denied** — `ENETUNREACH` |
| Grandchild descendant | **connected** | **denied** — `ENETUNREACH` |

Every probe is **validated by the control**: the control connects over TCP
and UDP, gets a real DNS answer from the container resolver, and its child
and grandchild both connect. A denial that the control could not
reproduce would prove nothing; here the control reproduces every probe's
success.

The DNS row is deliberately split. Docker writes the container's own name
and address into `/etc/hosts`, so a name lookup can succeed inside the
restricted namespace **by reading a local file** — that is not network
egress and is reported as such. The separate `dns_query` row sends a
well-formed DNS query over the network to the resolver in the parent
namespace, and that is denied.

The harness verdict:

```json
{
  "control_connected": true,
  "restricted_denied": true,
  "setup_reported_ok": true,
  "valid_test": true,
  "netns_differs": true
}
```

`valid_test: true` is the load-bearing assertion: it records that the
unrestricted control connected, so the restricted denial is attributable to
the containment boundary and not to an unreachable endpoint.

### Launcher unit tests in the same container

`tests/unit/test_linux_sandbox.py` runs in the production container with
the shipped profile at UID 1000: **22 passed, 0 failed**. It covers the
error taxonomy, the controlled argv protocol, per-stage mapping failures
(`setgroups_denial` / `uid_map` / `gid_map` each report their own stage),
the transactional abort before the mounts, the descriptor sweep in a forked
child, socket-valued standard-descriptor rejection, the namespace identity,
the 2 GiB cap inside the namespace, the root-read-only / artifact-writable
filesystem policy, and the status channel.

## 6. FU-21 and FU-22 compatibility

**FU-21 (filesystem isolation).** The intended policy is unchanged: the
root filesystem is read-only and only the per-book artifact path is
writable. The launcher now *enforces* it instead of falling back to a
no-op, so the policy is stronger than the previous behaviour rather than
different. The compatibility clarification is recorded in the FU-21 entry.

**FU-22 (memory cap).** Unchanged: the 2 GiB per-process `RLIMIT_AS`
semantics are preserved, including independent per-descendant inheritance.
The Windows Job Object backend is untouched, except that the Windows path
now refuses *before* it is invoked.

## 7. Windows refusal

On Windows the PDF route refuses with
`NetworkIsolationUnsupportedError` (HTTP **501**,
`internal.not_implemented`) **before** the Job backend is invoked and
before any parser process or Job target is created.

The Job Object backend enforces the **memory** cap, not network
isolation. Job Object network-rate control is **throttling**, never
isolation. Proxy-environment stripping is **defense in depth**, never
isolation. None of these is presented as network isolation.

**Explicitly deferred:** AppContainer with the no-internet-client
capability is the preferred Windows mechanism and is a separately approved
follow-up. It is not implemented here, and no Windows network policy of
any kind is implemented here.

## 8. Known limitations

1. **The Windows denial proof does not exist** — Windows is refused, not
   isolated. The AppContainer proof is the deferred follow-up.
2. **Local (non-container) Linux execution fails closed.** The boundary
   needs the shipped seccomp profile; the launcher reports the failing
   stage rather than degrading.
3. **The namespace-escape-resistance measurement is a residual gap.** The
   `setns` escape attempt must be proven under the effective capability
   contract; the CI job covers descendants and inherited-socket
   non-bypass, and the escape attempt is recorded as an explicit
   not-established item rather than assumed.
