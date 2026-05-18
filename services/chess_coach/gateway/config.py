"""Gateway configuration via environment variables.

Follows protocol §1.3 (data directory) and §2.1 (static-token option).
Uses pydantic-settings so values are validated and typed.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_HOST = "127.0.0.1"


def _default_data_dir() -> Path:
    """Resolve the default data directory per protocol §1.3.

    Order:
    1. ``CHESS_COACH_DATA_DIR`` env var (handled by Settings, not here)
    2. Platform-appropriate user data dir.
    """
    # Minimal cross-platform default; we deliberately don't pull in `appdirs`/
    # `platformdirs` for one path resolution. If the user wants a non-default
    # location they set the env var.
    if os.name == "nt":
        # Windows: %LOCALAPPDATA%\ChessCoach (LOCALAPPDATA always set on win).
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "ChessCoach"
        return Path.home() / "AppData" / "Local" / "ChessCoach"
    # macOS / Linux: ~/.local/share/chess-coach (XDG_DATA_HOME fallback)
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "chess-coach"
    return Path.home() / ".local" / "share" / "chess-coach"


class GatewaySettings(BaseSettings):
    """Process-wide configuration, populated from env on import.

    Field names are snake_case; environment variables use the
    ``CHESS_COACH_`` prefix and uppercase form.
    """

    model_config = SettingsConfigDict(
        env_prefix="CHESS_COACH_",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Network ----
    host: str = Field(
        default=_DEFAULT_HOST,
        description="Bind address. Loopback only by default; non-loopback values trigger an explicit warning.",
    )
    port: int = Field(
        default=0,
        ge=0,
        le=65535,
        description="TCP port; 0 means kernel-assigned (recorded in backend.json).",
    )

    # ---- Auth (protocol §2.1) ----
    backend_token: str | None = Field(
        default=None,
        description="If set, a static token is used and rotation on restart is suppressed.",
    )

    # ---- Filesystem (protocol §1.3) ----
    data_dir: Path = Field(
        default_factory=_default_data_dir,
        description="Root of all backend-managed state; runtime/, sqlite/, backups/ live under it.",
    )

    # ---- Behaviour flags ----
    enable_descriptor: bool = Field(
        default=True,
        description="Write backend.json on startup. Disable for tests that don't need discovery.",
    )
    log_level: str = Field(
        default="INFO",
        description="Root logger level: DEBUG, INFO, WARNING, ERROR.",
    )

    # ---- Derived paths ----

    @property
    def runtime_dir(self) -> Path:
        return self.data_dir / "runtime"

    @property
    def descriptor_path(self) -> Path:
        return self.runtime_dir / "backend.json"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "sqlite" / "chess_coach.db"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"
