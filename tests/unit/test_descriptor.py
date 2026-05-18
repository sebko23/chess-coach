"""Tests for the connection-descriptor file writer."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from chess_coach.gateway.descriptor import (
    Descriptor,
    generate_token,
    remove_descriptor,
    write_descriptor,
)


class TestToken:
    def test_generate_token_is_long_enough(self) -> None:
        t = generate_token()
        # 32 bytes urlsafe-base64 -> 43 chars, no padding
        assert len(t) >= 43

    def test_tokens_are_unique(self) -> None:
        seen = {generate_token() for _ in range(50)}
        assert len(seen) == 50


class TestWriteDescriptor:
    def _sample(self) -> Descriptor:
        return Descriptor(
            host="127.0.0.1",
            port=8765,
            session_token="test-token-abc",
            protocol_version="1.0.0",
            backend_version="0.1.0",
        )

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "runtime" / "backend.json"
        write_descriptor(path, self._sample())
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {
            "host": "127.0.0.1",
            "port": 8765,
            "session_token": "test-token-abc",
            "protocol_version": "1.0.0",
            "backend_version": "0.1.0",
        }

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "a" / "b" / "c" / "backend.json"
        write_descriptor(path, self._sample())
        assert path.exists()

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "backend.json"
        write_descriptor(path, self._sample())
        new_d = Descriptor(
            host="127.0.0.1",
            port=9000,
            session_token="different-token",
            protocol_version="1.0.0",
            backend_version="0.1.0",
        )
        write_descriptor(path, new_d)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["port"] == 9000
        assert data["session_token"] == "different-token"

    @pytest.mark.skipif(os.name != "posix", reason="chmod is POSIX-only")
    def test_permissions_are_restrictive_on_posix(self, tmp_path: Path) -> None:
        path = tmp_path / "backend.json"
        write_descriptor(path, self._sample())
        mode = path.stat().st_mode & 0o777
        # 0o600 means only owner read/write
        assert mode == 0o600

    def test_remove_is_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "backend.json"
        # remove on missing file: no error
        remove_descriptor(path)
        write_descriptor(path, self._sample())
        remove_descriptor(path)
        assert not path.exists()
        # remove again: no error
        remove_descriptor(path)
