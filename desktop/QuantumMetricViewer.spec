# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path.cwd()
ASSETS = ROOT / "desktop" / "assets"
ICON = next(
    (
        path
        for path in [ASSETS / "icon.icns", ASSETS / "icon.ico", ASSETS / "icon.png"]
        if path.exists()
    ),
    None,
)

a = Analysis(
    [str(ROOT / "desktop" / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "frontend" / "dist"), "frontend/dist")],
    hiddenimports=["uvicorn.lifespan.on", "uvicorn.protocols.http.h11_impl"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SDS Quantum Metric",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ICON) if ICON else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SDS Quantum Metric",
)
