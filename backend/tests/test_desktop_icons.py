from pathlib import Path

from scripts.generate_icons import ensure_icons


def test_app_icon_svg_source_exists() -> None:
    source = Path("desktop/assets/app-icon.svg")

    assert source.exists()
    assert "<svg" in source.read_text(encoding="utf-8")


def test_icon_generation_outputs_png_and_ico(tmp_path: Path) -> None:
    output_dir = tmp_path / "assets"
    generated = ensure_icons(
        output_dir,
        source_svg=Path("desktop/assets/app-icon.svg"),
        generate_icns=False,
    )

    assert generated["png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert generated["ico"].read_bytes().startswith(b"\x00\x00\x01\x00")
