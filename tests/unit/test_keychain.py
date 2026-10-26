"""Unit tests for ``services/chess_coach/keychain.py`` (A-F10 contract).

Per the FU-18 ledger entry (``docs/16_audit/OPEN-FOLLOWUPS.md:1404+``)
and the BBF-FU-18-keyring-test decision brief
(``docs/16_audit/BBF-FU-18-keyring-test.md``): secrets MUST come
from the OS-native keychain, with a plaintext env-var fallback
ONLY enabled when ``dev_fallback=True`` is passed explicitly.

These tests install an in-memory keyring backend for the duration
of each test, so the wrapper behavior is exercised against a
deterministic backend rather than the OS-native one (which is
unavailable on the Linux CI runner — no Secret Service). The
wrapper itself is still being tested; only the underlying storage
is swapped for a fixture. This is the standard pytest pattern
for testing code that depends on a side-effecting external
service.

Note on test fixtures: the secret values used here are deliberately
chosen to NOT match gitleaks' ``generic-api-key`` pattern (which
requires a known prefix like ``sk-`` followed by 20+ alphanumeric
chars). Using a non-secret-looking prefix (e.g. ``test-key-``)
keeps the gitleaks CI job green while still exercising the
get/set/delete code paths with realistic-shape strings.
"""
from __future__ import annotations

import logging
import uuid

import keyring
import pytest
from keyring.backend import KeyringBackend

from chess_coach import keychain as secrets


class _InMemoryKeyring(KeyringBackend):
    """A dict-backed keyring backend for tests.

    Subclasses ``keyring.backend.KeyringBackend`` so the ``keyring``
    library's ``set_keyring()`` accepts it. ``priority = 1`` puts
    it ahead of the platform default so it wins the
    ``get_keyring()`` race after ``set_keyring`` installs it.

    The dict is per-instance, so each test gets a fresh store when
    a new instance is installed via the ``_in_memory_keyring``
    fixture below.
    """

    priority = 1

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


@pytest.fixture
def _in_memory_keyring() -> None:
    """Install a fresh in-memory keyring backend for one test.

    The previous backend is restored at teardown so the test cannot
    leak its fixture into other tests. This makes the secrets
    wrapper's behavior deterministic on every platform — the
    Linux CI runner (no Secret Service) and the developer's macOS
    / Windows machine (native backends) both see the same
    in-process dict.
    """
    previous = keyring.get_keyring()
    keyring.set_keyring(_InMemoryKeyring())
    yield
    keyring.set_keyring(previous)


# A unique name per test invocation so concurrent or repeated
# runs don't collide. The keyring entry is cleaned up at the end
# of each test via the fixture.
def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def keyring_secret_name(_in_memory_keyring: None) -> str:
    """Yield a unique keyring name; delete the entry at teardown.

    Depends on ``_in_memory_keyring`` so the in-memory backend is
    installed before the cleanup fixture runs.
    """
    name = _unique_name("chess-coach-test")
    yield name
    # Cleanup: idempotent (delete_secret returns False on a
    # backend miss but does not raise).
    secrets.delete_secret(name)


# A test fixture value that looks like a real secret for code-path
# purposes but does NOT match gitleaks' `generic-api-key` regex
# (which requires `sk-` + 20+ chars). The `test-key-` prefix is
# clearly a fixture.
_FIXTURE_VALUE = "test-key-fixture-value-1234"


def test_get_secret_returns_keyring_value_when_present(keyring_secret_name: str) -> None:
    """A keyring hit returns the stored value."""
    secrets.set_secret(keyring_secret_name, _FIXTURE_VALUE)
    result = secrets.get_secret(keyring_secret_name, dev_fallback=False)
    assert result == _FIXTURE_VALUE


def test_get_secret_falls_back_to_env_var_when_dev_fallback_true(
    keyring_secret_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A keyring miss + env var set + dev_fallback=True returns the env var."""
    # Ensure no keyring entry
    secrets.delete_secret(keyring_secret_name)
    # Set env var with a non-secret-looking fixture value
    monkeypatch.setenv(keyring_secret_name, "test-envvar-fixture-5678")
    result = secrets.get_secret(keyring_secret_name, dev_fallback=True)
    assert result == "test-envvar-fixture-5678"


def test_get_secret_returns_none_when_dev_fallback_false_and_keyring_empty(
    keyring_secret_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A keyring miss + env var set + dev_fallback=False returns None.

    This is the production code path: a missing keyring entry must
    NOT silently fall back to a plaintext env var.
    """
    # Ensure no keyring entry
    secrets.delete_secret(keyring_secret_name)
    # Set env var (would be a leak if the production path read it)
    monkeypatch.setenv(keyring_secret_name, "test-leak-fixture-9012")
    result = secrets.get_secret(keyring_secret_name, dev_fallback=False)
    assert result is None


def test_get_secret_never_logs_value(
    keyring_secret_name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The secret value must never appear in any log output.

    Per A-F10: "Secrets are NEVER logged. A redaction filter wraps
    the logger and replaces matched key patterns with ``***``."
    This test asserts the ``secrets`` module itself does not log
    the value at any code path. The log_redaction filter (tested
    separately in ``test_log_redaction.py``) handles log records
    produced by other modules.
    """
    secrets.set_secret(keyring_secret_name, _FIXTURE_VALUE)
    with caplog.at_level(logging.DEBUG, logger="chess_coach.keychain"):
        result = secrets.get_secret(keyring_secret_name, dev_fallback=False)
    assert result == _FIXTURE_VALUE
    # The value must not appear in any captured log record.
    for record in caplog.records:
        assert _FIXTURE_VALUE not in record.getMessage(), (
            f"secret value leaked into log: {record.getMessage()!r}"
        )


def test_get_secret_logs_warning_when_env_var_fallback_used(
    keyring_secret_name: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A WARNING is logged when the env-var fallback is used.

    This makes the dev-mode behavior visible in production logs so
    a misconfigured production deployment does not silently leak
    secrets via env vars.
    """
    secrets.delete_secret(keyring_secret_name)
    env_value = "test-dev-fixture-7890"
    monkeypatch.setenv(keyring_secret_name, env_value)
    with caplog.at_level(logging.WARNING, logger="chess_coach.keychain"):
        secrets.get_secret(keyring_secret_name, dev_fallback=True)
    # The WARNING must mention the secret NAME (so an operator can
    # find the leak) but NOT the VALUE.
    assert any(
        keyring_secret_name in record.getMessage() for record in caplog.records
    ), f"WARNING did not name the leaking secret: {[r.getMessage() for r in caplog.records]}"
    assert not any(
        env_value in record.getMessage() for record in caplog.records
    ), f"WARNING leaked the secret value: {[r.getMessage() for r in caplog.records]}"

def test_set_secret_returns_false_when_backend_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """On a host with no keyring backend, ``set_secret`` returns
    False (and logs a WARNING) rather than raising ``NoKeyringError``.

    This is the behavior the Linux CI runner hits (no Secret
    Service). The fix decouples the wrapper from the backend's
    availability so the test fixture's teardown is robust on every
    platform.
    """
    # Use the real fail backend (the platform default on the Linux
    # CI runner). Skip the test if a real backend is available —
    # the test only proves the no-backend code path.
    keyring.set_keyring(keyring.backends.fail.Keyring())
    try:
        with caplog.at_level(logging.WARNING, logger="chess_coach.keychain"):
            result = secrets.set_secret("chess-coach-test-x", "val")
    finally:
        # Restore the in-memory backend so subsequent tests work
        # (we bypassed the fixture here).
        keyring.set_keyring(_InMemoryKeyring())
    assert result is False
    assert any(
        "set_secret" in r.getMessage() for r in caplog.records
    ), f"WARNING did not mention set_secret: {[r.getMessage() for r in caplog.records]}"


def test_delete_secret_returns_false_when_backend_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """On a host with no keyring backend, ``delete_secret`` returns
    False (and logs a WARNING) rather than raising ``NoKeyringError``.
    """
    keyring.set_keyring(keyring.backends.fail.Keyring())
    try:
        with caplog.at_level(logging.WARNING, logger="chess_coach.keychain"):
            result = secrets.delete_secret("chess-coach-test-y")
    finally:
        keyring.set_keyring(_InMemoryKeyring())
    assert result is False
    assert any(
        "delete_secret" in r.getMessage() for r in caplog.records
    ), f"WARNING did not mention delete_secret: {[r.getMessage() for r in caplog.records]}"


def test_get_secret_returns_none_when_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """On a host with no keyring backend, ``get_secret`` returns
    None (and logs a WARNING) rather than raising ``NoKeyringError``.

    With ``dev_fallback=True`` and no env var set, the result is
    None (no keyring entry, no env var to fall back to). With
    ``dev_fallback=False``, the result is None (production path).
    """
    keyring.set_keyring(keyring.backends.fail.Keyring())
    try:
        with caplog.at_level(logging.WARNING, logger="chess_coach.keychain"):
            assert (
                secrets.get_secret("chess-coach-test-z", dev_fallback=False)
                is None
            )
            # And the dev_fallback path also returns None because
            # no env var is set.
            assert (
                secrets.get_secret(
                    "chess-coach-test-z-2", dev_fallback=True
                )
                is None
            )
    finally:
        keyring.set_keyring(_InMemoryKeyring())

