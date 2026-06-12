from __future__ import annotations

import os
import signal
from pathlib import Path


def main() -> None:
    runtime = Path("data/runtime")
    for pid_file in runtime.glob("*.pid"):
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped {pid_file.stem} ({pid})")
        except ProcessLookupError:
            print(f"Already stopped {pid_file.stem}")
        except Exception as exc:
            print(f"Could not stop {pid_file}: {exc}")
        finally:
            pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
