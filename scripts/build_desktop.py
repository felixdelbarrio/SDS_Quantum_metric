from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.generate_icons import ensure_icons
    from scripts.sign_macos_app import main as sign_macos_app

    ensure_icons()
    subprocess.run(["pyinstaller", "desktop/QuantumMetricViewer.spec", "--noconfirm"], check=True)
    sign_macos_app()


if __name__ == "__main__":
    main()
