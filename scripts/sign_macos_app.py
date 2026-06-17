from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

APP_PATH = Path("dist") / "SDS Quantum Metric.app"


def main() -> None:
    if platform.system() != "Darwin":
        print("macOS signing skipped: not running on macOS.")
        return
    if not APP_PATH.exists():
        raise FileNotFoundError(f"macOS app bundle not found: {APP_PATH}")

    codesign = shutil.which("codesign")
    if not codesign:
        raise RuntimeError("macOS signing requires `codesign` in PATH.")

    identity = os.getenv("APPLE_CODESIGN_IDENTITY", "-").strip() or "-"
    command = [
        codesign,
        "--force",
        "--deep",
        "--timestamp=none" if identity == "-" else "--timestamp",
    ]
    if identity != "-":
        command.extend(["--options", "runtime"])
    command.extend(["--sign", identity, str(APP_PATH)])
    subprocess.run(command, check=True)
    subprocess.run([codesign, "--verify", "--deep", "--strict", str(APP_PATH)], check=True)
    print(f"Signed {APP_PATH} with {'ad-hoc identity' if identity == '-' else identity}.")

    _notarize_if_configured(identity)


def _notarize_if_configured(identity: str) -> None:
    if identity == "-":
        print("Notarization skipped: ad-hoc signing does not support notarization.")
        return
    apple_id = os.getenv("APPLE_ID")
    password = os.getenv("APPLE_APP_SPECIFIC_PASSWORD")
    team_id = os.getenv("APPLE_TEAM_ID")
    if not all((apple_id, password, team_id)):
        print(
            "Notarization skipped: APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD or APPLE_TEAM_ID missing."
        )
        return

    ditto = shutil.which("ditto")
    notarytool = shutil.which("xcrun")
    stapler = shutil.which("xcrun")
    if not ditto or not notarytool or not stapler:
        raise RuntimeError("Notarization requires `ditto` and `xcrun` in PATH.")

    archive = APP_PATH.with_suffix(".zip")
    subprocess.run(
        [ditto, "-c", "-k", "--keepParent", str(APP_PATH), str(archive)],
        check=True,
    )
    subprocess.run(
        [
            notarytool,
            "notarytool",
            "submit",
            str(archive),
            "--apple-id",
            apple_id,
            "--password",
            password,
            "--team-id",
            team_id,
            "--wait",
        ],
        check=True,
    )
    subprocess.run([stapler, "stapler", "staple", str(APP_PATH)], check=True)
    print(f"Notarized and stapled {APP_PATH}.")


if __name__ == "__main__":
    main()
