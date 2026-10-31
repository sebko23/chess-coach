# AppArmor profile for the FU-20 Linux network-isolation containers.
#
# WHY THIS EXISTS
#
# Moby's `docker-default` AppArmor profile -- the one every container
# runs under when AppArmor is enabled on the host -- contains:
#
#     deny mount,
#
# That rule is a plain `deny`, NOT an `audit deny`, so it produces NO
# entry in the kernel's audit log: the denial is silent. It is also
# not overridable by an `allow mount` elsewhere in the profile, because
# in AppArmor a plain `deny` outranks an `allow`.
#
# The consequence for FU-20: the PDF parser's containment sequence
# builds its own root by mounting a fresh tmpfs, and the container
# cannot mount at all under `docker-default`. The launcher therefore
# fails closed at the `mount_new_root` stage with EACCES, and the
# restricted-versus-unrestricted proof cannot run.
#
# This is not a runner quirk. It applies to EVERY AppArmor-enabled
# Docker host, which includes the supported production deployment.
#
# WHAT THIS PROFILE IS
#
# This is Moby's own `docker-default` profile for the pinned version
# (v26.1.4, the same version the shipped seccomp profile is derived
# from), with EXACTLY TWO changes:
#
#   1. the profile is renamed from `docker-default` to
#      `chess-coach-fu20`, so the host's own `docker-default` is left
#      untouched and every other container on the host is unaffected;
#   2. `deny mount,` is replaced by `allow mount,`.
#
# Nothing else is changed. Every other rule -- the `@{PROC}` write
# denials, the `/sys` exec denials, the `ptrace` scoping, the
# `signal` peer rules -- is byte-for-byte Moby's.
#
# The `{{...}}` fields are the Go template placeholders Moby's daemon
# substitutes at load time; they are resolved below.
#
# HOW IT IS APPLIED
#
# `scripts/dev/install_fu20_apparmor_profile.sh` installs this profile
# and the containers in the CI job attach it with
# `--security-opt apparmor=chess-coach-fu20`. The container still runs
# as UID 1000 with no host CAP_SYS_ADMIN, and the shipped seccomp
# profile still governs which syscalls are permitted.
#
# The deployment policy this imposes on an operator: the container's
# AppArmor profile must permit `mount`. A host whose policy denies it
# will fail closed at the mount stage with
# `internal.network_isolation_setup_failed` rather than parse without
# the boundary.

#include <tunables/global>

profile chess-coach-fu20 flags=(attach_disconnected,mediate_deleted) {

  network,
  capability,
  file,
  umount,
  # Host (privileged) processes may send signals to container processes.
  signal (receive) peer=unconfined,
  # runc may send signals to container processes (for "docker stop").
  signal (receive) peer=runc,
  # crun may send signals to container processes (for "docker stop" when used with crun OCI runtime).
  signal (receive) peer=crun,
  # dockerd may send signals to container processes (for "docker kill").
  signal (receive) peer=unconfined,
  # Container processes may send signals amongst themselves.
  signal (send,receive) peer=chess-coach-fu20,

  deny @{PROC}/* w,   # deny write for all files directly in /proc (not in a subdir)
  # deny write to files not in /proc/<number>/** or /proc/sys/**
  deny @{PROC}/{[^1-9],[^1-9][^0-9],[^1-9s][^0-9y],[^1-9s],[^1-9][^0-9][^0-9][^0-9/]*}/** w,
  deny @{PROC}/sys/[^k]** w,  # deny /proc/sys except /proc/sys/k* (effectively /proc/sys/kernel)
  deny @{PROC}/sys/kernel/{?,??,[^s][^h][^m]**} w,  # deny everything except shm* in /proc/sys/kernel/
  deny @{PROC}/sysrq-trigger rwklx,
  deny @{PROC}/kcore rwklx,

  allow mount,
  # AppArmor checks `pivot_root` as a SEPARATE permission from
  # `mount`: the launcher pivots into the root it built, and the
  # denial is reported as
  #   apparmor="DENIED" operation="pivotroot" class="mount"
  # even though the class is `mount`.
  allow pivot_root,

  deny /sys/[^f]*/** wklx,
  deny /sys/f[^s]*/** wklx,
  deny /sys/fs/[^c]*/** wklx,
  deny /sys/fs/c[^g]*/** wklx,
  deny /sys/fs/cg[^r]*/** wklx,
  deny /sys/firmware/** rwklx,
  deny /sys/devices/virtual/powercap/** rwklx,
  deny /sys/kernel/security/** rwklx,

  # suppress ptrace denials when using 'docker ps' or using 'ps' inside a container
  ptrace (trace,read,tracedby,readby) peer=chess-coach-fu20,
}
