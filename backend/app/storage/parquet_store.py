from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from backend.app.config.settings import Settings
from backend.app.observability.sanitizer import sanitize


class ParquetStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.parquet_dir.mkdir(parents=True, exist_ok=True)
        self.settings.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.settings.exports_dir.mkdir(parents=True, exist_ok=True)

    def write_raw_calls(self, country: str, rows: list[dict[str, Any]]) -> Path | None:
        if not rows:
            return None
        ingestion_id = str(rows[0]["ingestion_id"])
        target = self.settings.parquet_dir / f"country={country}" / "raw_api_calls"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"ingestion_id={ingestion_id}.parquet"
        frame = pl.DataFrame(rows)
        frame.write_parquet(path)
        return path

    def append_manifest(self, manifest: dict[str, Any]) -> Path:
        path = self.settings.manifests_dir / "ingestion_manifest.parquet"
        row = sanitize(manifest)
        new_frame = pl.DataFrame([row])
        if path.exists():
            old = pl.read_parquet(path)
            frame = pl.concat([old, new_frame], how="diagonal_relaxed")
        else:
            frame = new_frame
        frame.write_parquet(path)
        return path

    def list_ingestions(self) -> list[dict[str, Any]]:
        path = self.settings.manifests_dir / "ingestion_manifest.parquet"
        if not path.exists():
            return []
        return pl.read_parquet(path).sort("started_at", descending=True).to_dicts()

    def list_datasets(self) -> list[dict[str, Any]]:
        datasets: list[dict[str, Any]] = []
        for country_dir in sorted(self.settings.parquet_dir.glob("country=*")):
            if not country_dir.is_dir():
                continue
            files = list(country_dir.rglob("*.parquet"))
            size = sum(file.stat().st_size for file in files)
            datasets.append(
                {
                    "country": country_dir.name.split("=", 1)[1],
                    "files": len(files),
                    "bytes": size,
                    "updated_at": datetime.fromtimestamp(
                        max((file.stat().st_mtime for file in files), default=0), UTC
                    ).isoformat()
                    if files
                    else None,
                }
            )
        return datasets

    def delete_country(self, country: str) -> bool:
        target = self.settings.parquet_dir / f"country={country}"
        if not target.exists():
            return False
        shutil.rmtree(target)
        return True

    def export_countries(self, countries: list[str]) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_countries = "_".join(sorted(countries)) or "all"
        target = self.settings.exports_dir / f"quantum_export_{safe_countries}_{timestamp}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest = {
                "schema_version": "1.0",
                "created_at": datetime.now(UTC).isoformat(),
                "countries": countries,
                "checksum": "",
            }
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            for country in countries:
                root = self.settings.parquet_dir / f"country={country}"
                if not root.exists():
                    continue
                for file in root.rglob("*.parquet"):
                    archive.write(file, file.relative_to(self.settings.qm_data_dir))
        return target

    def import_zip(self, zip_path: Path) -> dict[str, Any]:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            if "manifest.json" not in names:
                raise ValueError("ZIP does not include manifest.json.")
            manifest = json.loads(archive.read("manifest.json"))
            for name in names:
                if not name.startswith("parquet/") or not name.endswith(".parquet"):
                    continue
                destination = self.settings.qm_data_dir / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        return {"imported_files": len(names), "manifest": manifest}

    def analytics_summary(self) -> dict[str, Any]:
        files = list(self.settings.parquet_dir.glob("country=*/raw_api_calls/*.parquet"))
        if not files:
            return {"raw_calls": 0, "countries": [], "rows": 0, "cards": 0}
        frame = pl.concat([pl.read_parquet(file) for file in files], how="diagonal_relaxed")
        countries = sorted(frame.get_column("country").unique().to_list())
        cards = (
            frame.get_column("card_id").drop_nulls().unique().len()
            if "card_id" in frame.columns
            else 0
        )
        return {
            "raw_calls": frame.height,
            "countries": countries,
            "rows": int(frame.get_column("row_count").sum()) if "row_count" in frame.columns else 0,
            "cards": cards,
        }

    def card_data(self, card_id: str) -> list[dict[str, Any]]:
        files = list(self.settings.parquet_dir.glob("country=*/raw_api_calls/*.parquet"))
        if not files:
            return []
        frame = pl.concat([pl.read_parquet(file) for file in files], how="diagonal_relaxed")
        if "card_id" not in frame.columns:
            return []
        return frame.filter(pl.col("card_id") == card_id).to_dicts()


def hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
