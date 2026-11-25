# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for LUMO Windows Desktop Application (Phase 13)."""

from pathlib import Path

block_cipher = None
REPO_ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(REPO_ROOT / "desktop" / "app.py")],
    pathex=[str(REPO_ROOT), str(REPO_ROOT / "backend")],
    binaries=[],
    datas=[
        (str(REPO_ROOT / "lumo-frontend"), "lumo-frontend"),
        (str(REPO_ROOT / "backend" / "app"), "backend/app"),
        (str(REPO_ROOT / "backend" / ".env.example"), "backend"),
    ],
    hiddenimports=[
        "webview",
        "clr",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LUMO",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(REPO_ROOT / "lumo-frontend" / "assets" / "favicon.ico")
    if (REPO_ROOT / "lumo-frontend" / "assets" / "favicon.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LUMO",
)
