#!/bin/bash
# Install the FU-20 container-scoped AppArmor profile.
#
# WHY
#
# Moby's `docker-default` profile -- the one every container runs
# under when AppArmor is enabled on the host -- contains `deny mount,`.
# That rule is a plain `deny`, not an `audit deny`, so it produces NO
# audit-log entry: the denial is silent. It also outranks any `allow
# mount` elsewhere in the profile.
#
# The FU-20 launcher's containment sequence builds its own root by
# mounting a fresh tmpfs, so under `docker-default` the container
# cannot mount at all and the launcher fails closed at the
# `mount_new_root` stage.
#
# The profile installed here is Moby's own `docker-default` for the
# pinned version (v26.1.4) with exactly two changes: the profile is
# renamed so the host's `docker-default` is left untouched, and
# `deny mount,` becomes `allow mount,`. Every other rule is Moby's.
#
# It is attached ONLY to this job's containers with
# `--security-opt apparmor=chess-coach-fu20`. The container still runs
# as UID 1000 with no host CAP_SYS_ADMIN, and the shipped seccomp
# profile still governs which syscalls are permitted.
set -euo pipefail

PROFILE_NAME="chess-coach-fu20"
SRC="$(dirname "$0")/../../infra/docker/apparmor-fu20.profile"
DST="/etc/apparmor.d/${PROFILE_NAME}"

if [[ ! -f "$SRC" ]]; then
  echo "FAIL: the profile source ${SRC} does not exist" >&2
  exit 1
fi

sudo cp "$SRC" "$DST"
echo "--- the profile being installed (${DST}) ---"
sudo grep -vE '^\s*(#|$)' "$DST"

echo "--- installing it ---"
sudo apparmor_parser -r "$DST"

echo "--- the profiles now loaded ---"
sudo aa-status 2>/dev/null | grep -E "${PROFILE_NAME}|docker-default" || true
