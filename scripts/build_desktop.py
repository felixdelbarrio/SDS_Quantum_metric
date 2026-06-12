from __future__ import annotations

import platform
import struct
import subprocess
import zlib
from pathlib import Path


def main() -> None:
    assets = Path("desktop/assets")
    assets.mkdir(parents=True, exist_ok=True)
    png = assets / "icon.png"
    _write_png(png, 256)
    system = platform.system()
    if system == "Darwin":
        iconset = assets / "QuantumMetric.iconset"
        iconset.mkdir(exist_ok=True)
        for size in [16, 32, 64, 128, 256, 512]:
            _write_png(iconset / f"icon_{size}x{size}.png", size)
        _write_png(iconset / "icon_512x512@2x.png", 1024)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(assets / "icon.icns")], check=True
        )
    elif system == "Windows":
        _write_ico(assets / "icon.ico", png.read_bytes(), 256)
    subprocess.run(["pyinstaller", "desktop/QuantumMetricViewer.spec", "--noconfirm"], check=True)


def _write_png(path: Path, size: int) -> None:
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            band = 24 if (x // max(size // 8, 1)) % 2 else 0
            r = 15 + band
            g = 123 + (y * 40 // size)
            b = 108 + (x * 60 // size)
            a = 255
            row.extend([r, g, b, a])
        rows.append(bytes(row))
    raw = b"".join(rows)
    png = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)),
            _chunk(b"IDAT", zlib.compress(raw, 9)),
            _chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(png)


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _write_ico(path: Path, png: bytes, size: int) -> None:
    header = struct.pack("<HHH", 0, 1, 1)
    directory = struct.pack(
        "<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0, 0, 0, 1, 32, len(png), 22
    )
    path.write_bytes(header + directory + png)


if __name__ == "__main__":
    main()
