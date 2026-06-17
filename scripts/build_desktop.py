from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.ensure_playwright_browsers import main as ensure_playwright_browsers
    from scripts.generate_icons import ensure_icons
    from scripts.sign_macos_app import main as sign_macos_app
    from scripts.smoke_test_desktop import main as smoke_test_desktop

    ensure_icons()
    ensure_playwright_browsers()
    if not (root / "frontend" / "dist" / "index.html").exists():
        raise RuntimeError("frontend/dist/index.html is missing. Run npm run build first.")
    subprocess.run(["pyinstaller", "desktop/QuantumMetricViewer.spec", "--noconfirm"], check=True)
    sign_macos_app()
    smoke_test_desktop()


if __name__ == "__main__":
    main()
