"""Gateway settings — read from env / .env with sensible defaults."""
from __future__ import annotations

import os
import platform
import secrets
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default data directory — XDG Base Directory / Platform conventions
_HOME = Path.home()
if platform.system() == "Linux":
    _DEFAULT_DATA_DIR = _HOME / ".local" / "share" / "chess-coach"
elif platform.system() == "Darwin":
    _DEFAULT_DATA_DIR = _HOME / "Library" / "Application Support" / "chess-coach"
else:  # Windows
    _DEFAULT_DATA_DIR = _HOME / "AppData" / "Local" / "chess-coach"

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_LOG_LEVEL = "INFO"


class GatewaySettings(BaseSettings):
    """Settings for the CHESS COACH gateway process."""

    model_config = SettingsConfigDict(
        env_prefix="CHESS_COACH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- network ---
    host: str = Field(
        default=_DEFAULT_HOST,
        description="Bind address. Uses 0.0.0.0 to accept connections from outside Docker/remote hosts.",
    )
    port: int = Field(
        default=18080,
        ge=0,
        le=65535,
        description="Port to bind on. 0 = OS-assigned ephemeral port.",
    )

    # --- data ---
    data_dir: Path = Field(
        default=_DEFAULT_DATA_DIR,
        description="Root directory for sqlite, logs, backups, engine downloads, and the runtime descriptor.",
    )

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "sqlite" / "chess_coach.db"

    @property
    def descriptor_path(self) -> Path:
        return self.runtime_dir / "backend.json"

    @property
    def runtime_dir(self) -> Path:
        return self.data_dir / "runtime"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    # --- auth ---
    backend_token: str = Field(
        default="",
        description="Pre-set bearer token. Empty or not set = auto-generate a fresh token on each start.",
    )

    # --- observation ---
    log_level: str = Field(
        default=_DEFAULT_LOG_LEVEL,
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )

    # --- descriptor ---
    enable_descriptor: bool = Field(
        default=True,
        description="Write backend.json descriptor file for frontend discovery.",
    )
