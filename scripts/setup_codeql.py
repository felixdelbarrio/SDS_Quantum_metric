from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

REPO_API = "https://api.github.com/repos/github/codeql-action"


def main() -> None:
    args = _parse_args()
    home = Path(args.home).resolve()
    binary = _codeql_binary(home)
    if binary.exists():
        print(f"CodeQL already installed: {binary}")
        return

    asset = _asset_name()
    url = _find_release_asset(args.version, asset)
    home.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        archive = Path(temp_dir) / asset
        _download(url, archive)
        extracted = Path(temp_dir) / "extracted"
        extracted.mkdir()
        _extract(archive, extracted)
        bundle = _find_bundle_dir(extracted)
        if home.exists():
            shutil.rmtree(home)
        shutil.move(str(bundle), str(home))
    _mark_executable(binary)
    print(f"CodeQL installed: {binary}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install a local CodeQL CLI bundle.")
    parser.add_argument("--version", default="latest", help="CodeQL release tag or 'latest'.")
    parser.add_argument("--home", default=".tools/codeql", help="Destination CodeQL directory.")
    return parser.parse_args()


def _codeql_binary(home: Path) -> Path:
    return home / ("codeql.exe" if platform.system() == "Windows" else "codeql")


def _asset_name() -> str:
    system = platform.system()
    if system == "Darwin":
        return "codeql-bundle-osx64.tar.gz"
    if system == "Linux":
        return "codeql-bundle-linux64.tar.gz"
    if system == "Windows":
        return "codeql-bundle-win64.zip"
    raise RuntimeError(f"Unsupported platform for CodeQL bundle: {system}")


def _find_release_asset(version: str, asset_name: str) -> str:
    for release in _release_candidates(version):
        data = _fetch_json(_release_url(release))
        for asset in data.get("assets", []):
            if asset.get("name") == asset_name:
                return str(asset["browser_download_url"])
    raise RuntimeError(f"Could not find CodeQL asset {asset_name!r} for version {version!r}.")


def _release_candidates(version: str) -> tuple[str, ...]:
    if version == "latest":
        return ("latest",)
    candidates = [version]
    if not version.startswith("codeql-bundle-"):
        normalized = version if version.startswith("v") else f"v{version}"
        candidates.append(f"codeql-bundle-{normalized}")
    return tuple(dict.fromkeys(candidates))


def _release_url(version: str) -> str:
    if version == "latest":
        return f"{REPO_API}/releases/latest"
    return f"{REPO_API}/releases/tags/{version}"


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(  # noqa: S310
        url, headers={"User-Agent": "sds-quantum-metric-codeql"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"assets": []}
        raise


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310
        url, headers={"User-Agent": "sds-quantum-metric-codeql"}
    )
    print(f"Downloading CodeQL from {url}")
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def _extract(archive: Path, destination: Path) -> None:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zip_file:
            members = zip_file.infolist()
            _validate_members(destination, [member.filename for member in members])
            for member in members:
                target = destination / member.filename
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip_file.open(member) as source:
                    with target.open("wb") as output:
                        shutil.copyfileobj(source, output)
        return
    with tarfile.open(archive) as tar_file:
        members = tar_file.getmembers()
        _validate_members(destination, [member.name for member in members])
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if member.isfile():
                source = tar_file.extractfile(member)
                if source is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source:
                    with target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)
                continue
            if member.issym():
                _create_safe_symlink(destination, target, member.linkname)


def _validate_members(destination: Path, member_names: list[str]) -> None:
    root = destination.resolve()
    for name in member_names:
        target = (root / name).resolve()
        if os.path.commonpath([root, target]) != str(root):
            raise RuntimeError(f"Refusing to extract archive member outside destination: {name}")


def _create_safe_symlink(root: Path, target: Path, link_name: str) -> None:
    resolved_root = root.resolve()
    link_target = (target.parent / link_name).resolve()
    if os.path.commonpath([resolved_root, link_target]) != str(resolved_root):
        raise RuntimeError(f"Refusing to create symlink outside destination: {link_name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(link_name)


def _find_bundle_dir(extracted: Path) -> Path:
    candidates = [
        path
        for path in extracted.rglob("codeql")
        if path.is_dir() and _codeql_binary(path).exists()
    ]
    if not candidates:
        raise RuntimeError("Downloaded CodeQL bundle did not contain a codeql executable.")
    return candidates[0]


def _mark_executable(path: Path) -> None:
    if platform.system() == "Windows":
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


if __name__ == "__main__":
    main()
