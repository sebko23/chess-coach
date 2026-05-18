"""Connection descriptor file (``backend.json``).

Protocol §1.4: the backend writes its host, port, session token, and protocol
version to ``${CHESS_COACH_DATA_DIR}/runtime/backend.json`` so that any client
on the same machine (typically the GUI) can discover it.

Protocol §2.1: the token is a *standard bearer credential*, not a privileged
handshake. The Backend MUST NOT restrict authentication by process identity,
binary signature, launch parent, executable path, or code-signing certificate;
any client that can read this file (or has been provided the token by the
operator) may authenticate.
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

#: Token entropy (bytes). 32 bytes -> 256 bits -> 43-char urlsafe-base64.
_TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class Descriptor:
    host: str
    port: int
    session_token: str
    protocol_version: str  # e.g. "1.0.0"
    backend_version: str   # e.g. "0.1.0"

    def as_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def generate_token() -> str:
    """Generate a fresh session token (urlsafe-base64, 43 chars)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def write_descriptor(path: Path, descriptor: Descriptor) -> None:
    """Write ``descriptor`` atomically to ``path``.

    Atomic = write-temp-then-rename; clients that re-read on 401 will never
    see a partial file.

    On POSIX, the file is also chmod 0600 to discourage accidental over-share.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # tempfile in the same directory so os.replace stays on the same filesystem.
    fd, tmp = tempfile.mkstemp(
        prefix=".backend.json.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(descriptor.as_json())
        if os.name == "posix":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        # Best-effort cleanup; suppress secondary errors.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def remove_descriptor(path: Path) -> None:
    """Remove the descriptor file if it exists. Idempotent."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


__all__ = ["Descriptor", "generate_token", "remove_descriptor", "write_descriptor"]
