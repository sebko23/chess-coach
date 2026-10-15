"""OS-native secret storage wrapper.

Per the A-F10 contract (`docs/08_security/security-strategy.md`
section A-F10), secrets MUST be stored in the OS-native keychain:
- Windows: Credential Manager
- macOS: Keychain
- Linux: Secret Service / libsecret

The ``keyring`` Python library provides a uniform API over those
backends. The functions in this module wrap ``keyring`` with a
plaintext environment-variable fallback that is ONLY enabled when
``dev_fallback=True`` is passed explicitly. Production code paths
should pass ``dev_fallback=False`` so a missing keyring entry
returns ``None`` instead of silently falling back to a plaintext
value.

The plaintext fallback exists for developer convenience in dev
mode (where the user may not have provisioned a keyring entry
yet) and is gated by the ``--dev-secrets`` CLI flag in the
gateway entrypoint.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Service identifier used for every keyring entry. One namespace
# per application; the keyring backend stores each (SERVICE_NAME,
# name) pair separately.
SERVICE_NAME = "chess-coach"


def get_secret(name: str, *, dev_fallback: bool = True) -> str | None:
    """Read a secret from the OS-native keychain.

    On a keyring miss:
    - If ``dev_fallback=True``: fall back to ``os.environ[name]``
      and log a WARNING. This is for dev mode only.
    - If ``dev_fallback=False``: return ``None``. This is the
      production code path.

    On a keyring hit: return the value. The value is NEVER logged
    by this function (per security-strategy.md:55 "Secrets are
    NEVER logged").
    """
    try:
        import keyring

        value = keyring.get_password(SERVICE_NAME, name)
        if value is not None:
            return value
    except keyring.errors.KeyringError as exc:
        # Backend unavailable (no Secret Service on Linux CI, etc.).
        # Log and fall through to the env-var fallback.
        logger.warning("keyring backend unavailable: %s", exc)

    if dev_fallback:
        env_value = os.environ.get(name)
        if env_value:
            logger.warning(
                "secret %r loaded from plaintext environment variable; "
                "this is dev-only behavior. Production code should use "
                "the keyring path (dev_fallback=False).",
                name,
            )
            return env_value
    return None


def set_secret(name: str, value: str) -> bool:
    """Write a secret to the OS-native keychain.

    Returns True on success, False on backend failure (e.g., the
    Linux CI runner has no Secret Service backend). A WARNING is
    logged on failure so the operator sees the missed write.

    Not used in production code paths. Intended for the test
    fixture and an optional CLI tool (out of scope for this BBF).
    """
    try:
        import keyring

        keyring.set_password(SERVICE_NAME, name, value)
    except keyring.errors.KeyringError as exc:
        # Backend unavailable (no Secret Service on Linux CI, etc.).
        # The write didn't happen; the caller can detect this via
        # the False return value.
        logger.warning("keyring backend unavailable for set_secret: %s", exc)
        return False
    return True


def delete_secret(name: str) -> bool:
    """Delete a secret from the OS-native keychain.

    Returns True on success, False on backend failure. A missing
    key is NOT an error (idempotent delete).

    Not used in production code paths. Intended for the test
    fixture and an optional CLI tool (out of scope for this BBF).
    """
    try:
        import keyring

        keyring.delete_password(SERVICE_NAME, name)
    except keyring.errors.PasswordDeleteError:
        # Missing key is not an error (idempotent delete).
        pass
    except keyring.errors.KeyringError as exc:
        # Backend unavailable (e.g., Linux CI runner has no
        # Secret Service). The delete didn't happen, but the
        # caller can move on.
        logger.warning("keyring backend unavailable for delete_secret: %s", exc)
        return False
    return True
