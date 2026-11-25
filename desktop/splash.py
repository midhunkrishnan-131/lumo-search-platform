"""Lightweight monochrome splash and error HTML templates for LUMO Desktop."""

from __future__ import annotations

import html


def build_splash_html(app_version: str = "0.1.0") -> str:
    """Return a clean monochrome loading screen matching LUMO's design language."""
    ver = html.escape(app_version)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Starting LUMO...</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #fafafa;
      --fg: #111111;
      --muted: #666666;
      --border: #e5e5e5;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0c0c0c;
        --fg: #f4f4f5;
        --muted: #a1a1aa;
        --border: #27272a;
      }}
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--fg);
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      user-select: none;
    }}
    .card {{
      text-align: center;
      padding: 2.5rem 3rem;
      border: 1px solid var(--border);
      border-radius: 10px;
      max-width: 420px;
      width: 90%;
    }}
    .logo {{
      width: 42px;
      height: 42px;
      margin: 0 auto 1.25rem;
      display: block;
    }}
    h1 {{
      font-size: 1.25rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      margin-bottom: 0.5rem;
    }}
    p {{
      font-size: 0.875rem;
      color: var(--muted);
      line-height: 1.5;
    }}
    .bar {{
      margin: 1.5rem auto 0.75rem;
      height: 3px;
      width: 100%;
      background: var(--border);
      border-radius: 2px;
      overflow: hidden;
      position: relative;
    }}
    .bar::after {{
      content: "";
      position: absolute;
      left: -40%;
      width: 40%;
      height: 100%;
      background: var(--fg);
      animation: slide 1.2s ease-in-out infinite;
    }}
    @keyframes slide {{
      0% {{ left: -40%; }}
      100% {{ left: 100%; }}
    }}
    .meta {{
      font-size: 0.75rem;
      color: var(--muted);
      margin-top: 0.5rem;
    }}
  </style>
</head>
<body>
  <div class="card">
    <svg class="logo" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="26" height="26" rx="6" stroke="currentColor" stroke-width="2"/>
      <circle cx="15" cy="15" r="5.5" stroke="currentColor" stroke-width="2"/>
      <path d="M19.5 19.5L24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </svg>
    <h1>LUMO</h1>
    <p id="status-msg">Starting local search engine and intelligence services...</p>
    <div class="bar"></div>
    <div class="meta">Version {ver} · Local Desktop Workspace</div>
  </div>
</body>
</html>"""


def build_error_html(error_message: str, log_path: str) -> str:
    """Return a safe startup failure screen with diagnostic guidance."""
    err = html.escape(error_message)
    log_p = html.escape(log_path)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>LUMO Startup Error</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #fafafa;
      --fg: #111111;
      --muted: #666666;
      --border: #e5e5e5;
      --err: #dc2626;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0c0c0c;
        --fg: #f4f4f5;
        --muted: #a1a1aa;
        --border: #27272a;
        --err: #f87171;
      }}
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--fg);
      height: 100vh;
      margin: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .card {{
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 2rem;
      max-width: 520px;
      width: 90%;
    }}
    h1 {{ font-size: 1.125rem; color: var(--err); margin-bottom: 0.75rem; }}
    p {{ font-size: 0.875rem; color: var(--muted); line-height: 1.5; margin-bottom: 0.75rem; }}
    code {{
      display: block;
      padding: 0.75rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 0.8125rem;
      word-break: break-word;
      margin-bottom: 1rem;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>LUMO Desktop Failed to Start</h1>
    <p>The local backend service could not be initialized.</p>
    <code>{err}</code>
    <p>Diagnostic logs are stored at:<br/><strong>{log_p}</strong></p>
  </div>
</body>
</html>"""
