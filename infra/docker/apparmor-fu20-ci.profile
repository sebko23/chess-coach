# AppArmor profile for the FU-20 Linux network-isolation CI job.
#
# WHY THIS EXISTS
#
# Ubuntu 24.04 (the GitHub-hosted `ubuntu-latest` runner image) enables
# restricted unprivileged user namespaces by default. An unconfined
# process that creates a user namespace transitions into AppArmor's
# `unprivileged_userns` profile. That profile grants `userns`,
# `network`, `file rwlkm`, `signal`, `dbus`, `unix`, `mqueue` and
# `ptrace` -- but NOT `mount`.
#
# The sandbox launcher's containment sequence NEEDS `mount` inside that
# namespace: it makes mount propagation private, remounts the root
# filesystem read-only, and bind-mounts the artifact path writable.
# Without `mount` the launcher cannot establish the boundary, and it
# correctly fails closed.
#
# MEASURED ON THE RUNNER
#
# Every mount variant was refused with EACCES, including a brand-new
# tmpfs with no inheritance involved:
#
#   mount(/, MS_REC|MS_PRIVATE)            EACCES
#   mount(/, MS_REC|MS_SLAVE)              EACCES
#   mount(/, MS_BIND)                      EACCES
#   mount(tmpfs, /tmp/newroot)             EACCES
#   mount(/, MS_REMOUNT|MS_BIND|MS_RDONLY) EACCES
#
# The same strategies succeed on a developer machine, where the host
# does not apply the restriction. The capability mask inside the new
# user namespace is fully populated in both cases, so the denial is the
# LSM policy and not the kernel capability check.
#
# WHAT IT PERMITS
#
# `userns` allows the process to create and use an unprivileged user
# namespace. `mount` allows the mount operations the launcher performs
# inside that namespace. The remaining rules mirror Ubuntu's own
# `unprivileged_userns` profile, so the container is confined in the
# same way the host intends for unprivileged namespace users.
#
# SCOPE
#
# This profile applies ONLY to the dedicated `linux-network-isolation`
# CI job's container, through `--security-opt apparmor=...`. It is not
# applied to the production Compose deployment, whose host AppArmor
# policy is the operator's to configure.
#
# The profile does not grant the container anything it did not already
# have: the container still runs as UID 1000 with no host CAP_SYS_ADMIN,
# and the shipped seccomp profile still governs which syscalls are
# permitted at all. The profile is NOT `flags=(unconfined)` and does not
# disable AppArmor.
#
# Reference: Ubuntu 24.04 restricts unprivileged user namespaces via
# AppArmor; creating a namespace is permitted, `mount` within it is
# denied unless a profile allows it.

abi <abi/4.0>,

include <tunables/global>

profile chess-coach-fu20 {
  userns,
  mount,

  # Mirrors the host's `unprivileged_userns` profile for everything the
  # launcher needs besides the namespace and the mount.
  allow network,
  allow signal,
  allow dbus,
  allow file rwlkm /{,**},
  allow unix,
  allow mqueue,
  allow ptrace,

  # AppArmor writes the profile into this path when the container is
  # started. Without it the runtime fails with:
  #   write fsmount:fscontext:proc/thread-self/attr/apparmor/exec:
  #   no such file or directory
  allow file rw /proc/thread-self/attr/apparmor/exec,

  include if exists <local/chess-coach-fu20>
}
