"""Main entry point for LUMO Windows Desktop Application (Edge WebView2)."""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path

from desktop.config import DesktopConfig
from desktop.lifecycle import DesktopServiceManager
from desktop.splash import build_error_html, build_splash_html


def configure_desktop_logging(logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "desktop.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("lumo.desktop")


def build_preferences_bootstrap_js(backend_url: str) -> str:
    """Safely configure frontend localStorage apiBaseUrl on desktop load if unset or localhost."""
    safe_url = json.dumps(backend_url)
    return f"""
    (function() {{
      try {{
        var key = 'lumo_preferences';
        var raw = localStorage.getItem(key);
        var prefs = raw ? JSON.parse(raw) : {{}};
        if (!prefs.apiBaseUrl || /^http:\\/\\/(127\\.0\\.0\\.1|localhost):\\d+$/i.test(prefs.apiBaseUrl)) {{
          prefs.apiBaseUrl = {safe_url};
          localStorage.setItem(key, JSON.stringify(prefs));
        }}
      }} catch (e) {{}}
    }})();
    """


def run_desktop_app(config: DesktopConfig | None = None) -> int:
    """Launch LUMO inside a native Windows WebView2 window with managed local services."""
    import webview  # Imported here so tests can inspect config/lifecycle without GUI dependency

    cfg = config or DesktopConfig()
    cfg.ensure_directories()
    logger = configure_desktop_logging(cfg.logs_dir)
    logger.info("Launching LUMO Desktop v%s (data_dir=%s)", cfg.app_version, cfg.data_dir)

    manager = DesktopServiceManager(cfg)
    stop_watchdog = threading.Event()

    window = webview.create_window(
        title=cfg.app_title,
        html=build_splash_html(cfg.app_version),
        width=cfg.window_width,
        height=cfg.window_height,
        min_size=(cfg.min_width, cfg.min_height),
        resizable=True,
        js_api=None,  # Security: No arbitrary Python/OS bridge exposed to webview JS
    )

    def on_closing() -> None:
        logger.info("Desktop window closing; initiating graceful shutdown.")
        stop_watchdog.set()
        manager.shutdown()

    window.events.closing += on_closing

    def startup_worker() -> None:
        status = manager.start_all()
        if not status.ready:
            err_msg = status.error or "Unknown startup error"
            logger.error("Startup failed: %s", err_msg)
            window.load_html(build_error_html(err_msg, str(cfg.logs_dir / "backend_desktop.log")))
            return

        logger.info("Navigating desktop webview to %s", status.frontend_url)
        window.load_url(f"{status.frontend_url}/index.html")

        # Wait briefly for page load then ensure apiBaseUrl is synced to managed backend
        def inject_prefs() -> None:
            time.sleep(0.6)
            try:
                window.evaluate_js(build_preferences_bootstrap_js(status.backend_url))
            except Exception as exc:
                logger.debug("Preferences bootstrap skipped: %s", exc)

        window.events.loaded += lambda: threading.Thread(target=inject_prefs, daemon=True).start()

        # Watchdog loop for unexpected backend crash recovery
        while not stop_watchdog.is_set():
            stop_watchdog.wait(timeout=10.0)
            if stop_watchdog.is_set():
                break
            if not manager.is_backend_alive():
                manager.recover_backend_if_needed()

    def on_started() -> None:
        threading.Thread(target=startup_worker, name="lumo-desktop-startup", daemon=True).start()

    try:
        webview.start(
            on_started,
            gui="edgechromium",
            storage_path=str(cfg.webview_storage_dir),
            private_mode=False,
            debug=False,
        )
    finally:
        stop_watchdog.set()
        manager.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(run_desktop_app())
