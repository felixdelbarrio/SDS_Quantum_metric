from __future__ import annotations

import platform
import shutil
import subprocess
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
        from PIL import Image, ImageDraw  # type: ignore[import-not-found,import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised by build environments.
        raise RuntimeError(
            'Icon generation requires desktop extras. Run: python -m pip install -e ".[desktop]"'
        ) from exc

    assets_dir.mkdir(parents=True, exist_ok=True)
    generated = {
        "png": assets_dir / "icon.png",
        "ico": assets_dir / "icon.ico",
    }

    _render_icon(Image, ImageDraw, PNG_SIZE).save(generated["png"], format="PNG")

    ico_image = _render_icon(Image, ImageDraw, PNG_SIZE)
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
            _render_icon(Image, ImageDraw, size).save(iconset / file_name, format="PNG")
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


def _render_icon(image_module: Any, draw_module: Any, size: int) -> Any:
    scale = 4
    canvas_size = size * scale
    image = image_module.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = draw_module.Draw(image)

    def px(value: float) -> int:
        return round(value * canvas_size / 1024)

    draw.rounded_rectangle(
        (0, 0, canvas_size - 1, canvas_size - 1),
        radius=px(236),
        fill="#070E46",
    )
    draw.rounded_rectangle(
        (px(42), px(42), px(982), px(982)),
        radius=px(204),
        outline="#2165CA",
        width=px(28),
    )
    draw.ellipse((px(186), px(188), px(838), px(840)), fill="#001391")
    draw.line(
        [(px(268), px(680)), (px(448), px(502)), (px(590), px(584)), (px(756), px(342))],
        fill="#85C8FF",
        width=px(72),
        joint="curve",
    )
    for x, y, radius in ((268, 680, 62), (448, 502, 62), (590, 584, 62), (756, 342, 70)):
        draw.ellipse(
            (px(x - radius), px(y - radius), px(x + radius), px(y + radius)),
            fill="#FFFFFF",
        )
    draw.arc(
        (px(256), px(246), px(768), px(758)),
        start=208,
        end=510,
        fill="#53A9EF",
        width=px(42),
    )
    draw.rounded_rectangle(
        (px(270), px(738), px(766), px(800)),
        radius=px(31),
        fill="#FFFFFF",
    )
    return image.resize((size, size), image_module.Resampling.LANCZOS)


def main() -> None:
    generated = ensure_icons()
    for label, path in generated.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
