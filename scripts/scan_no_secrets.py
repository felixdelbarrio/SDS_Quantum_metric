from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "frontend/dist",
    "data",
    "dist",
    "build",
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
    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.parts)
        if parts & SKIP_DIRS:
            continue
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


if __name__ == "__main__":
    main()
