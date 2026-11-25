"""Tests for LUMO Phase 13 Windows Desktop shell, lifecycle, security, and data dirs."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import threading
import urllib.request

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from desktop.app import build_preferences_bootstrap_js  # noqa: E402
from desktop.config import DesktopConfig, resolve_data_dir  # noqa: E402
from desktop.lifecycle import (  # noqa: E402
    DesktopServiceManager,
    check_lumo_backend_health,
    find_free_port,
)
from desktop.splash import build_error_html, build_splash_html  # noqa: E402


def test_desktop_config_creates_and_preserves_data_dirs(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "lumo_appdata"
    monkeypatch.setenv("LUMO_DATA_DIR", str(data_dir))

    resolved = resolve_data_dir()
    assert resolved == data_dir.resolve()

    cfg = DesktopConfig(repo_root=REPO_ROOT, data_dir=resolved)
    cfg.ensure_directories()

    assert cfg.data_dir.exists()
    assert cfg.qdrant_storage_path.exists()
    assert cfg.logs_dir.exists()
    assert cfg.temp_dir.exists()
    assert cfg.webview_storage_dir.exists()

    # Existing user data must never be deleted
    sentinel = cfg.db_path
    sentinel.write_text("user-data", encoding="utf-8")
    cfg.ensure_directories()
    assert sentinel.read_text(encoding="utf-8") == "user-data"


def test_desktop_frontend_server_starts_serves_and_stops(tmp_path: Path):
    free_port = find_free_port("127.0.0.1", 39100)
    cfg = DesktopConfig(
        repo_root=REPO_ROOT,
        data_dir=tmp_path / "data",
        frontend_port=free_port,
    )
    manager = DesktopServiceManager(cfg)

    try:
        manager.start_frontend()
        assert manager._frontend_managed is True

        with urllib.request.urlopen(f"{manager.frontend_url}/index.html", timeout=2) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "LUMO" in body
    finally:
        manager.shutdown()

    assert manager._frontend_managed is False


def test_desktop_attaches_to_existing_lumo_backend_without_killing_it(tmp_path: Path):
    class MockLumoHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/api/v1/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "healthy", "application": "LUMO", "version": "0.1.0"}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):  # noqa: A002
            pass

    server = HTTPServer(("127.0.0.1", 0), MockLumoHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        cfg = DesktopConfig(
            repo_root=REPO_ROOT,
            data_dir=tmp_path / "data",
            backend_port=port,
        )
        manager = DesktopServiceManager(cfg)
        manager.start_backend()

        # Must reuse external healthy backend without spawning duplicate
        assert manager._backend_managed is False
        assert check_lumo_backend_health(f"http://127.0.0.1:{port}") is not None

        # Shutdown must NOT stop the external server
        manager.shutdown()
        assert check_lumo_backend_health(f"http://127.0.0.1:{port}") is not None
    finally:
        server.shutdown()
        server.server_close()


def test_desktop_avoids_unrelated_process_on_occupied_port(tmp_path: Path):
    class OtherAppHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OtherService")

        def log_message(self, format, *args):  # noqa: A002
            pass

    server = HTTPServer(("127.0.0.1", 0), OtherAppHandler)
    occupied_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # Mock health returns None for non-LUMO service
        assert check_lumo_backend_health(f"http://127.0.0.1:{occupied_port}") is None
        alt_port = find_free_port("127.0.0.1", occupied_port)
        assert alt_port != occupied_port
    finally:
        server.shutdown()
        server.server_close()


def test_splash_and_error_html_escape_xss_and_bootstrap_js():
    splash = build_splash_html("0.1.0")
    assert "LUMO" in splash
    assert "0.1.0" in splash

    err_html = build_error_html("<script>alert(1)</script>", "C:\\Users\\test\\desktop.log")
    assert "<script>alert(1)</script>" not in err_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in err_html

    js = build_preferences_bootstrap_js("http://127.0.0.1:8000")
    assert "http://127.0.0.1:8000" in js
    assert "lumo_preferences" in js


def test_pywebview_module_available_for_windows():
    import webview
    assert hasattr(webview, "create_window")
    assert hasattr(webview, "start")
