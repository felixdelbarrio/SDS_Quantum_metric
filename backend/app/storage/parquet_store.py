from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from backend.app.config.settings import Settings
from backend.app.observability.sanitizer import sanitize

DEDUPLICATION_COLUMNS = (
    "source_endpoint",
    "dashboard_id",
    "card_id",
    "card_type",
    "view_name",
    "metric_ids",
    "source_ts_start",
    "source_ts_end",
    "query_hash",
    "response_hash",
)
COMPACTED_RAW_CALLS_FILE = "raw_api_calls.parquet"


@dataclass(frozen=True)
class RawCallMergeResult:
    path: Path | None
    rows_captured: int
    rows_replaced: int
    rows_after: int


class ParquetStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.parquet_dir.mkdir(parents=True, exist_ok=True)
        self.settings.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.settings.exports_dir.mkdir(parents=True, exist_ok=True)

    def write_raw_calls(self, country: str, rows: list[dict[str, Any]]) -> Path | None:
        return self.merge_raw_calls(country, rows).path

    def merge_raw_calls(self, country: str, rows: list[dict[str, Any]]) -> RawCallMergeResult:
        if not rows:
            return RawCallMergeResult(path=None, rows_captured=0, rows_replaced=0, rows_after=0)
        target = self.settings.parquet_dir / f"country={country}" / "raw_api_calls"
        target.mkdir(parents=True, exist_ok=True)
        path = target / COMPACTED_RAW_CALLS_FILE
        files = self._raw_call_files(country)
        new_frame = pl.DataFrame(rows)
        existing = self._read_parquet_files(files)
        kept_existing, rows_replaced = self._drop_overlapping_source_range(existing, rows)
        frame = pl.concat([kept_existing, new_frame], how="diagonal_relaxed")
        dedupe_columns = [column for column in DEDUPLICATION_COLUMNS if column in frame.columns]
        if dedupe_columns:
            frame = frame.unique(subset=dedupe_columns, keep="last", maintain_order=True)

        temporary = path.with_suffix(".tmp.parquet")
        frame.write_parquet(temporary)
        for file in files:
            file.unlink(missing_ok=True)
        temporary.replace(path)
        return RawCallMergeResult(
            path=path,
            rows_captured=len(rows),
            rows_replaced=rows_replaced,
            rows_after=frame.height,
        )

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

    def latest_source_end(self, country: str) -> datetime | None:
        files = self._raw_call_files(country)
        if not files:
            return None
        frame = self._read_parquet_files(files)
        if "source_ts_end" not in frame.columns or frame.is_empty():
            return None
        values = frame.get_column("source_ts_end").drop_nulls().to_list()
        parsed = [_parse_source_ts(value) for value in values]
        timestamps = [value for value in parsed if value is not None]
        return max(timestamps) if timestamps else None

    def _raw_call_files(self, country: str) -> list[Path]:
        root = self.settings.parquet_dir / f"country={country}" / "raw_api_calls"
        return sorted(root.glob("*.parquet")) if root.exists() else []

    def _read_parquet_files(self, files: list[Path]) -> pl.DataFrame:
        if not files:
            return pl.DataFrame()
        return pl.concat([pl.read_parquet(file) for file in files], how="diagonal_relaxed")

    def _drop_overlapping_source_range(
        self, frame: pl.DataFrame, new_rows: list[dict[str, Any]]
    ) -> tuple[pl.DataFrame, int]:
        bounds = _source_bounds(new_rows)
        if frame.is_empty() or bounds is None:
            return frame, 0
        kept: list[dict[str, Any]] = []
        replaced = 0
        for row in frame.to_dicts():
            if _row_overlaps(row, bounds):
                replaced += 1
            else:
                kept.append(row)
        if kept:
            return pl.DataFrame(kept), replaced
        return pl.DataFrame(schema=frame.schema), replaced


def hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _source_bounds(rows: list[dict[str, Any]]) -> tuple[datetime, datetime] | None:
    starts = [_parse_source_ts(row.get("source_ts_start")) for row in rows]
    ends = [_parse_source_ts(row.get("source_ts_end")) for row in rows]
    valid_starts = [value for value in starts if value is not None]
    valid_ends = [value for value in ends if value is not None]
    if not valid_starts or not valid_ends:
        return None
    return min(valid_starts), max(valid_ends)


def _row_overlaps(row: dict[str, Any], bounds: tuple[datetime, datetime]) -> bool:
    start = _parse_source_ts(row.get("source_ts_start"))
    end = _parse_source_ts(row.get("source_ts_end"))
    if start is None or end is None:
        return False
    lower, upper = bounds
    return start <= upper and end >= lower


def _parse_source_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        timestamp = value / 1000 if abs(value) > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, UTC)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            return _parse_source_ts(int(normalized))
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
    return None
