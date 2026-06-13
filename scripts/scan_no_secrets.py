from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".codeql-db",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tools",
    ".venv",
    "build",
    "data",
    "dist",
    "htmlcov",
    "node_modules",
    "QuantumMetric.iconset",
    "__pycache__",
    "tests",
}
PATTERNS = [
    re.compile(r"Cookie:\s*[A-Za-z0-9_:\-.]+=[^<\n;\s]{20,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*Bearer\s+eyJ", re.IGNORECASE),
    re.compile(r"refreshToken[\"']?\s*[:=]\s*[\"'][^\"']{16,}", re.IGNORECASE),
    re.compile(r"accessToken[\"']?\s*[:=]\s*[\"']eyJ", re.IGNORECASE),
]


def main() -> None:
    failures: list[str] = []
    for path in _iter_scannable_files(Path(".")):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                failures.append(str(path))
                break
    if failures:
        print("Potential secrets found:")
        for failure in failures:
            print(f" - {failure}")
        sys.exit(1)
    print("No persisted cookies or tokens detected.")


def _iter_scannable_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in SKIP_DIRS]
        files.extend(Path(current_root) / filename for filename in filenames)
    return files


if __name__ == "__main__":
    main()
