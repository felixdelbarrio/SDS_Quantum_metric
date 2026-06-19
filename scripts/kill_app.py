from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from backend.app.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    stopped: set[int] = set()
    for runtime in [settings.runtime_dir, Path("data/runtime")]:
        if not runtime.exists():
            continue
        for pid_file in runtime.glob("*.pid"):
            _stop_pid_file(pid_file, stopped)

    for port in range(settings.backend_port, settings.backend_port + 20):
        _stop_listeners(port, ["backend.app.main:app"], stopped)
    for port in range(settings.frontend_port, settings.frontend_port + 20):
        _stop_listeners(port, ["vite"], stopped)


def _stop_pid_file(pid_file: Path, stopped: set[int]) -> None:
    try:
        pid = int(pid_file.read_text().strip())
        _terminate_pid(pid, stopped)
        print(f"Stopped {pid_file.stem} ({pid})")
    except ProcessLookupError:
        print(f"Already stopped {pid_file.stem}")
    except Exception as exc:
        print(f"Could not stop {pid_file}: {exc}")
    finally:
        pid_file.unlink(missing_ok=True)


def _stop_listeners(port: int, command_markers: list[str], stopped: set[int]) -> None:
    for pid in _listener_pids(port):
        if pid in stopped:
            continue
        command = _command_for_pid(pid)
        if all(marker in command for marker in command_markers):
            _terminate_pid(pid, stopped)
            print(f"Stopped listener on port {port} ({pid})")


def _listener_pids(port: int) -> list[int]:
    try:
        result = subprocess.run(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]


def _command_for_pid(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip()


def _terminate_pid(pid: int, stopped: set[int]) -> None:
    if pid in stopped:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        stopped.add(pid)
        raise
    stopped.add(pid)


if __name__ == "__main__":
    main()
