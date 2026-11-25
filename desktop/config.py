"""Configuration and local data directory management for LUMO Windows Desktop."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sys


def resolve_repo_root() -> Path:
    """Resolve the LUMO root directory in both source and frozen PyInstaller modes."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def resolve_data_dir() -> Path:
    """Resolve the persistent local user data directory (%LOCALAPPDATA%\\LUMO on Windows)."""
    override = os.environ.get("LUMO_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        return Path(local_appdata) / "LUMO"

    return Path.home() / ".lumo"


@dataclass
class DesktopConfig:
    """Runtime configuration for the LUMO Windows desktop shell."""

    app_name: str = "LUMO"
    app_title: str = "LUMO — Independent Search & Intelligence"
    app_version: str = "0.1.0"
    repo_root: Path = field(default_factory=resolve_repo_root)
    data_dir: Path = field(default_factory=resolve_data_dir)

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 3000

    startup_timeout_seconds: float = 25.0
    health_poll_interval_seconds: float = 0.4
    window_width: int = 1280
    window_height: int = 840
    min_width: int = 960
    min_height: int = 640

    @property
    def backend_dir(self) -> Path:
        return self.repo_root / "backend"

    @property
    def frontend_dir(self) -> Path:
        return self.repo_root / "lumo-frontend"

    @property
    def venv_python(self) -> Path:
        candidate = self.backend_dir / ".venv" / "Scripts" / "python.exe"
        if candidate.exists():
            return candidate
        return Path(sys.executable)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lumo.db"

    @property
    def qdrant_storage_path(self) -> Path:
        return self.data_dir / "qdrant_storage"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "temp"

    @property
    def webview_storage_dir(self) -> Path:
        return self.data_dir / "webview"

    @property
    def backend_url(self) -> str:
        return f"http://{self.backend_host}:{self.backend_port}"

    @property
    def frontend_url(self) -> str:
        return f"http://{self.frontend_host}:{self.frontend_port}"

    def ensure_directories(self) -> None:
        """Create required local data directories without overwriting existing user data."""
        for directory in (
            self.data_dir,
            self.qdrant_storage_path,
            self.logs_dir,
            self.temp_dir,
            self.webview_storage_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
