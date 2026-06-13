from __future__ import annotations

import platform
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS_DIR = ROOT / "desktop" / "assets"
DEFAULT_SVG = DEFAULT_ASSETS_DIR / "app-icon.svg"
PNG_SIZE = 1024
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICONSET_SPECS = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)


def ensure_icons(
    assets_dir: Path = DEFAULT_ASSETS_DIR,
    *,
    source_svg: Path | None = None,
    generate_icns: bool | None = None,
) -> dict[str, Path]:
    source = source_svg or assets_dir / DEFAULT_SVG.name
    if not source.exists():
        raise FileNotFoundError(
            f"Missing app icon source SVG at {source}. Restore desktop/assets/app-icon.svg."
        )

    try:
        import cairosvg  # type: ignore[import-not-found,import-untyped]
        from PIL import Image  # type: ignore[import-not-found,import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised by build environments.
        raise RuntimeError(
            'Icon generation requires desktop extras. Run: python -m pip install -e ".[desktop]"'
        ) from exc

    assets_dir.mkdir(parents=True, exist_ok=True)
    generated = {
        "png": assets_dir / "icon.png",
        "ico": assets_dir / "icon.ico",
    }

    generated["png"].write_bytes(_render_png(cairosvg, source, PNG_SIZE))

    ico_image = Image.open(BytesIO(generated["png"].read_bytes())).convert("RGBA")
    ico_image.save(
        generated["ico"],
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
    )

    should_generate_icns = platform.system() == "Darwin" if generate_icns is None else generate_icns
    if should_generate_icns:
        iconset = assets_dir / "QuantumMetric.iconset"
        if iconset.exists():
            shutil.rmtree(iconset)
        iconset.mkdir(parents=True, exist_ok=True)
        for file_name, size in ICONSET_SPECS:
            (iconset / file_name).write_bytes(_render_png(cairosvg, source, size))
        iconutil = shutil.which("iconutil")
        if not iconutil:
            raise RuntimeError("macOS icon generation requires iconutil in PATH.")
        subprocess.run(
            [iconutil, "-c", "icns", str(iconset), "-o", str(assets_dir / "icon.icns")],
            check=True,
        )
        generated["icns"] = assets_dir / "icon.icns"
        generated["iconset"] = iconset

    return generated


def _render_png(cairosvg_module: Any, source: Path, size: int) -> bytes:
    output = BytesIO()
    cairosvg_module.svg2png(
        url=str(source),
        write_to=output,
        output_width=size,
        output_height=size,
    )
    return output.getvalue()


def main() -> None:
    generated = ensure_icons()
    for label, path in generated.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
