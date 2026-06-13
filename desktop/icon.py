from __future__ import annotations

import sys
from pathlib import Path


def resolve_icon_png() -> str | None:
    source = Path("desktop/assets/icon.png").resolve()
    if source.exists():
        return str(source)

    bundle_root = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    bundled = (bundle_root / "desktop" / "assets" / "icon.png").resolve()
    return str(bundled) if bundled.exists() else None


def apply_macos_app_icon(icon_path: str | None = None) -> None:
    if sys.platform != "darwin":
        return
    resolved_icon = icon_path or resolve_icon_png()
    if not resolved_icon:
        return
    try:
        from AppKit import NSApplication, NSImage  # type: ignore[import-not-found,import-untyped]

        image = NSImage.alloc().initWithContentsOfFile_(resolved_icon)
        if image is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception:
        return
