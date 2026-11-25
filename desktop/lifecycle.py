"""Lifecycle management for LUMO Windows Desktop background services."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from desktop.config import DesktopConfig

logger = logging.getLogger("lumo.desktop.lifecycle")


def is_port_in_use(host: str, port: int) -> bool:
    """Check whether a local TCP port is currently accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def find_free_port(host: str, preferred_port: int) -> int:
    """Return preferred_port if free, otherwise allocate an ephemeral free port on host."""
    if not is_port_in_use(host, preferred_port):
        return preferred_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def check_lumo_backend_health(base_url: str, timeout: float = 1.5) -> dict | None:
    """Verify that base_url hosts a healthy LUMO FastAPI instance."""
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/v1/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("application") == "LUMO" and payload.get("status") == "healthy":
                return payload
            return None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


class _QuietHTTPHandler(SimpleHTTPRequestHandler):
    """Serve static frontend assets without noisy stderr access logs."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.debug("Frontend HTTP: " + format, *args)


@dataclass
class StartupStatus:
    """Represents the current startup state of managed desktop services."""

    ready: bool
    backend_url: str
    frontend_url: str
    backend_managed: bool
    frontend_managed: bool
    error: str | None = None


class DesktopServiceManager:
    """Manages local FastAPI backend and static frontend HTTP server for LUMO Desktop."""

    def __init__(self, config: DesktopConfig | None = None) -> None:
        self.config = config or DesktopConfig()
        self.config.ensure_directories()

        self._backend_process: subprocess.Popen[bytes] | None = None
        self._backend_managed: bool = False

        self._frontend_server: ThreadingHTTPServer | None = None
        self._frontend_thread: threading.Thread | None = None
        self._frontend_managed: bool = False

        self._lock = threading.Lock()
        self._shutting_down = False

    @property
    def backend_url(self) -> str:
        return self.config.backend_url

    @property
    def frontend_url(self) -> str:
        return self.config.frontend_url

    def start_backend(self) -> None:
        """Attach to an existing healthy LUMO backend or start a managed FastAPI process."""
        with self._lock:
            # 1. Check if LUMO backend is already running on preferred port
            if is_port_in_use(self.config.backend_host, self.config.backend_port):
                existing = check_lumo_backend_health(self.config.backend_url)
                if existing is not None:
                    logger.info("Reusing existing healthy LUMO backend at %s", self.config.backend_url)
                    self._backend_managed = False
                    return
                # Port occupied by unrelated service -> choose free port
                free_port = find_free_port(self.config.backend_host, self.config.backend_port)
                logger.warning(
                    "Port %d occupied by non-LUMO process; switching managed backend to %d",
                    self.config.backend_port,
                    free_port,
                )
                self.config.backend_port = free_port

            # 2. Spawn managed uvicorn process
            self._spawn_backend_process()

        # 3. Wait for readiness outside lock
        self._wait_for_backend()

    def _spawn_backend_process(self) -> None:
        python_exe = str(self.config.venv_python)
        cmd = [
            python_exe,
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            self.config.backend_host,
            "--port",
            str(self.config.backend_port),
        ]

        env = os.environ.copy()
        env.setdefault("LUMO_DATA_DIR", str(self.config.data_dir))
        # Ensure CORS permits the desktop frontend origin
        desktop_origin = f"http://{self.config.frontend_host}:{self.config.frontend_port}"
        existing_cors = env.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        if desktop_origin not in existing_cors:
            env["CORS_ORIGINS"] = f"{existing_cors},{desktop_origin}"

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        log_path = self.config.logs_dir / "backend_desktop.log"
        log_file = open(log_path, "ab")  # noqa: SIM115

        logger.info("Starting managed FastAPI backend on %s", self.config.backend_url)
        try:
            self._backend_process = subprocess.Popen(
                cmd,
                cwd=str(self.config.backend_dir),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
            self._backend_managed = True
        finally:
            log_file.close()

    def _wait_for_backend(self) -> None:
        deadline = time.monotonic() + self.config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self._backend_managed and self._backend_process is not None:
                exit_code = self._backend_process.poll()
                if exit_code is not None:
                    raise RuntimeError(
                        f"LUMO backend exited unexpectedly during startup (code {exit_code}). "
                        f"Check logs at {self.config.logs_dir / 'backend_desktop.log'}."
                    )

            if check_lumo_backend_health(self.config.backend_url) is not None:
                logger.info("LUMO backend is healthy at %s", self.config.backend_url)
                return

            time.sleep(self.config.health_poll_interval_seconds)

        raise TimeoutError(
            f"LUMO backend did not become healthy within {self.config.startup_timeout_seconds}s."
        )

    def start_frontend(self) -> None:
        """Start an isolated 127.0.0.1 static HTTP server for lumo-frontend if not already running."""
        with self._lock:
            if not self.config.frontend_dir.exists():
                raise FileNotFoundError(f"Frontend directory not found: {self.config.frontend_dir}")

            # Check if frontend already serving on preferred port
            if is_port_in_use(self.config.frontend_host, self.config.frontend_port):
                try:
                    with urllib.request.urlopen(f"{self.config.frontend_url}/index.html", timeout=1.0) as resp:
                        if resp.status == 200 and b"LUMO" in resp.read(2048):
                            logger.info("Reusing existing LUMO frontend server at %s", self.config.frontend_url)
                            self._frontend_managed = False
                            return
                except Exception:
                    pass
                self.config.frontend_port = find_free_port(
                    self.config.frontend_host, self.config.frontend_port
                )

            handler = partial(_QuietHTTPHandler, directory=str(self.config.frontend_dir))
            self._frontend_server = ThreadingHTTPServer(
                (self.config.frontend_host, self.config.frontend_port),
                handler,
            )
            self._frontend_thread = threading.Thread(
                target=self._frontend_server.serve_forever,
                name="lumo-desktop-frontend",
                daemon=True,
            )
            self._frontend_thread.start()
            self._frontend_managed = True
            logger.info("Started managed frontend server at %s", self.config.frontend_url)

    def start_all(self) -> StartupStatus:
        """Start frontend and backend services and return status."""
        try:
            self.start_frontend()
            self.start_backend()
            return StartupStatus(
                ready=True,
                backend_url=self.backend_url,
                frontend_url=self.frontend_url,
                backend_managed=self._backend_managed,
                frontend_managed=self._frontend_managed,
            )
        except Exception as exc:
            logger.error("Desktop service startup failed: %s", exc)
            return StartupStatus(
                ready=False,
                backend_url=self.backend_url,
                frontend_url=self.frontend_url,
                backend_managed=self._backend_managed,
                frontend_managed=self._frontend_managed,
                error=str(exc),
            )

    def is_backend_alive(self) -> bool:
        """Return True if the backend responds to health checks."""
        return check_lumo_backend_health(self.backend_url, timeout=1.0) is not None

    def recover_backend_if_needed(self) -> bool:
        """Restart managed backend process if it terminated unexpectedly."""
        if self._shutting_down or not self._backend_managed:
            return False
        if self._backend_process is not None and self._backend_process.poll() is not None:
            logger.warning("Managed backend process died unexpectedly; attempting recovery...")
            try:
                self._spawn_backend_process()
                self._wait_for_backend()
                return True
            except Exception as exc:
                logger.error("Backend recovery failed: %s", exc)
                return False
        return False

    def shutdown(self) -> None:
        """Gracefully terminate only services managed by this desktop instance."""
        with self._lock:
            self._shutting_down = True

            if self._frontend_managed and self._frontend_server is not None:
                logger.info("Shutting down managed frontend server...")
                try:
                    self._frontend_server.shutdown()
                    self._frontend_server.server_close()
                except Exception as exc:
                    logger.debug("Frontend shutdown error: %s", exc)
                self._frontend_server = None
                self._frontend_managed = False

            if self._backend_managed and self._backend_process is not None:
                logger.info("Shutting down managed FastAPI backend (PID %s)...", self._backend_process.pid)
                try:
                    self._backend_process.terminate()
                    self._backend_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("Backend did not exit gracefully; forcing kill.")
                    self._backend_process.kill()
                except Exception as exc:
                    logger.debug("Backend shutdown error: %s", exc)
                self._backend_process = None
                self._backend_managed = False
