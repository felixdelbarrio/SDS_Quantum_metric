from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium-headless-shell"],
        check=True,
        env=env,
    )
    browser_root = _browser_root()
    if not browser_root.exists() or not any(browser_root.iterdir()):
        raise RuntimeError(f"Playwright Chromium was not installed at {browser_root}.")
    _prune_full_chromium(browser_root)
    if not any(path.name.startswith("chromium_headless_shell-") for path in browser_root.iterdir()):
        raise RuntimeError(f"Playwright Chromium headless shell is missing at {browser_root}.")


def _browser_root() -> Path:
    import playwright

    return Path(playwright.__file__).resolve().parent / "driver/package/.local-browsers"


def _prune_full_chromium(browser_root: Path) -> None:
    for path in browser_root.iterdir():
        if path.name.startswith("chromium-"):
            shutil.rmtree(path)


if __name__ == "__main__":
    main()
