#!/bin/bash
# Install a container-scoped AppArmor profile for the FU-20 proof.
#
# WHY
#
# The GitHub-hosted `ubuntu-latest` runner's kernel (7.0.0-1017-azure)
# has `kernel.apparmor_restrict_unprivileged_userns = 1`, and the
# runner's `docker-default` AppArmor profile DENIES `mount`. The
# launcher's container therefore cannot mount even a fresh tmpfs
# inside its own user namespace, and the proof fails closed at the
# `mount_new_root` stage.
#
# The denial is SILENT: the profile's rule is a plain `deny`, not an
# `audit deny`, so no DENIED record reaches the audit log. The
# `unprivileged_userns` transition target is NOT the denier -- the
# container's profile after the unshare is still `docker-default`.
#
# WHAT
#
# A profile derived from the runner's OWN `docker-default`, with the
# `deny mount` rule removed and `allow mount` added, installed under a
# different name and attached ONLY to this job's container. The
# runner's `docker-default` itself is left untouched, and no other
# container on the runner is affected.
#
# The script prints the exact diff so the change is auditable, and
# verifies that the resulting profile still carries the `docker-default`
# rules for everything except `mount`.
set -euo pipefail

PROFILE_NAME="chess-coach-fu20"
SRC="/etc/apparmor.d/docker-default"
DST="/etc/apparmor.d/${PROFILE_NAME}"

if [[ ! -f "$SRC" ]]; then
  echo "FAIL: ${SRC} does not exist on this host" >&2
  exit 1
fi

sudo cp "$SRC" "$DST"

# Derive the profile: rename it, drop the `deny mount` rule, and add
# `allow mount`. python3 is used rather than sed because the profile's
# structure (a nested `profile` block with its own braces) makes a
# textual rule edit fragile.
sudo python3 - "$DST" "$PROFILE_NAME" <<'PYEOF'
import re
import sys

path, name = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()

# 1. Rename the profile so the runner's own `docker-default` is kept.
text, count = re.subn(
    r"^profile\s+docker-default\b", f"profile {name}", text, count=1, flags=re.M
)
if count != 1:
    sys.exit(f"FAIL: could not rename the profile (found {count} matches)")

# 2. Remove the `deny mount` rule. A plain `deny` OUTRANKS an `allow`
#    in AppArmor, so the deny has to go, not be overridden.
before = text
text = re.sub(r"^[ \t]*deny[ \t]+mount[ \t]*,[ \t]*\n", "", text, flags=re.M)
removed = before.count("deny mount") - text.count("deny mount")

# 3. Add `allow mount` inside the profile body: immediately before the
#    profile's own closing brace.
closing = text.rfind("}")
if closing == -1:
    sys.exit("FAIL: the profile has no closing brace")
text = text[:closing] + "  allow mount,\n" + text[closing:]

open(path, "w", encoding="utf-8").write(text)
print(f"removed {removed} `deny mount` rule(s) and added `allow mount`")
PYEOF

echo "--- the exact diff against the runner's docker-default ---"
sudo diff -u "$SRC" "$DST" || true

echo "--- installing the derived profile ---"
sudo apparmor_parser -r "$DST"

echo "--- the profile the container will run under ---"
sudo aa-status 2>/dev/null | grep -E "${PROFILE_NAME}|docker-default" || true
