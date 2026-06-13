# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

ROOT = Path.cwd()
ASSETS = ROOT / "desktop" / "assets"
if sys.platform == "darwin":
    ICON_CANDIDATES = [ASSETS / "icon.icns", ASSETS / "icon.png"]
elif sys.platform == "win32":
    ICON_CANDIDATES = [ASSETS / "icon.ico", ASSETS / "icon.png"]
else:
    ICON_CANDIDATES = [ASSETS / "icon.png", ASSETS / "icon.ico", ASSETS / "icon.icns"]
ICON = next((path for path in ICON_CANDIDATES if path.exists()), None)
if ICON is None:
    expected = ", ".join(str(path) for path in ICON_CANDIDATES)
    raise FileNotFoundError(
        f"Missing desktop icon asset. Expected one of: {expected}. "
        "Run `python scripts/generate_icons.py` before PyInstaller."
    )

a = Analysis(
    [str(ROOT / "desktop" / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
        (str(ASSETS), "desktop/assets"),
    ],
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
    icon=str(ICON),
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
