from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, cast

import polars as pl

from backend.app.config.settings import Settings
from backend.app.observability.sanitizer import sanitize
from backend.app.quantum_dashboard.periods import parse_date, zoneinfo_for

DEDUPLICATION_COLUMNS = (
    "range_key",
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
COMPACTED_DATASET_FILE = "part-000.parquet"
DAY_COVERAGE_FILE = "day_coverage.parquet"


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
        files = self._legacy_raw_call_files(country)
        new_frame = pl.DataFrame(
            [_parquet_safe_row(row) for row in rows],
            infer_schema_length=None,
        )
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
        self._publish_daily_raw_calls(country, frame)
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
            try:
                old = pl.read_parquet(path)
            except Exception:
                corrupt = path.with_suffix(
                    f".corrupt-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.parquet"
                )
                path.replace(corrupt)
                old = None
        else:
            old = None
        if old is not None:
            frame = pl.concat([old, new_frame], how="diagonal_relaxed")
        else:
            frame = new_frame
        temporary = path.with_suffix(".tmp.parquet")
        frame.write_parquet(temporary)
        temporary.replace(path)
        return path

    def write_country_dataset(
        self,
        country: str,
        dataset_path: str,
        rows: list[dict[str, Any]],
        *,
        file_name: str = COMPACTED_DATASET_FILE,
    ) -> Path | None:
        target = self.settings.parquet_dir / f"country={country}" / dataset_path
        target.mkdir(parents=True, exist_ok=True)
        path = target / file_name
        if not rows:
            path.unlink(missing_ok=True)
            return None
        frame = pl.DataFrame([_parquet_safe_row(row) for row in rows])
        temporary = path.with_suffix(".tmp.parquet")
        frame.write_parquet(temporary)
        for file in target.glob("*.parquet"):
            if file != temporary:
                file.unlink(missing_ok=True)
        temporary.replace(path)
        return path

    def read_country_dataset(self, country: str, dataset_path: str) -> list[dict[str, Any]]:
        target = self.settings.parquet_dir / f"country={country}" / dataset_path
        files = sorted(target.glob("*.parquet")) if target.exists() else []
        if not files:
            return []
        frame = self._read_parquet_files(files)
        return [_parquet_rich_row(row) for row in frame.to_dicts()]

    def list_country_entities(
        self, country: str, dashboard_id: str | None = None
    ) -> list[dict[str, Any]]:
        root = self.settings.parquet_dir / f"country={country}"
        entities: list[dict[str, Any]] = []
        if not root.exists():
            return entities
        for dataset_dir in sorted({file.parent for file in root.rglob("*.parquet")}):
            files = sorted(dataset_dir.glob("*.parquet"))
            if not files:
                continue
            scan = pl.scan_parquet([str(file) for file in files])
            if dashboard_id:
                scoped_scan = _dashboard_scoped_scan(scan, dashboard_id)
                if scoped_scan is None:
                    continue
                scan = scoped_scan
            rows = int(scan.select(pl.len()).collect().item())
            if rows == 0:
                continue
            relative = str(dataset_dir.relative_to(root))
            sample = _sample_row(scan)
            entities.append(
                {
                    "id": relative,
                    "label": relative.replace("_", " "),
                    "category": _entity_category(relative),
                    "dashboard_id": _text_or_none(sample.get("dashboard_id")),
                    "dashboard_name": _text_or_none(sample.get("dashboard_name")),
                    "widget_id": _text_or_none(sample.get("widget_id")),
                    "widget_role": _text_or_none(
                        sample.get("card_role") or sample.get("visual_role")
                    ),
                    "rows": rows,
                    "files": len(files),
                    "bytes": sum(file.stat().st_size for file in files),
                    "updated_at": max((file.stat().st_mtime for file in files), default=0),
                }
            )
        return entities

    def country_entity_schema(self, country: str, dataset_path: str) -> dict[str, str]:
        files = self._country_dataset_files(country, dataset_path)
        if not files:
            return {}
        schema = pl.scan_parquet([str(file) for file in files]).collect_schema()
        return {name: str(dtype) for name, dtype in schema.items()}

    def read_country_entity_page(
        self,
        country: str,
        dataset_path: str,
        *,
        search: str | None = None,
        sort: str | None = None,
        direction: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        files = self._country_dataset_files(country, dataset_path)
        bounded_limit = max(1, min(limit, 500))
        bounded_offset = max(0, offset)
        if not files:
            return {
                "rows": [],
                "columns": [],
                "total": 0,
                "offset": bounded_offset,
                "limit": bounded_limit,
            }
        frame = pl.scan_parquet([str(file) for file in files])
        schema = frame.collect_schema()
        columns = list(schema.names())
        if search:
            predicates = [
                pl.col(column).cast(pl.Utf8).str.contains(search, literal=True)
                for column in columns
            ]
            if predicates:
                frame = frame.filter(pl.any_horizontal(predicates))
        total = int(frame.select(pl.len()).collect().item())
        if sort and sort in columns:
            frame = frame.sort(sort, descending=direction == "desc")
        page = frame.slice(bounded_offset, bounded_limit).collect()
        return {
            "rows": [_parquet_rich_row(row) for row in page.to_dicts()],
            "columns": columns,
            "total": total,
            "offset": bounded_offset,
            "limit": bounded_limit,
        }

    def country_dataset_exists(self, country: str, dataset_path: str) -> bool:
        target = self.settings.parquet_dir / f"country={country}" / dataset_path
        return target.exists() and any(target.glob("*.parquet"))

    def list_ingestions(self) -> list[dict[str, Any]]:
        path = self.settings.manifests_dir / "ingestion_manifest.parquet"
        if not path.exists():
            return []
        try:
            return pl.read_parquet(path).sort("started_at", descending=True).to_dicts()
        except Exception:
            return []

    def delete_ingestion_history(self, country: str | None = None) -> int:
        path = self.settings.manifests_dir / "ingestion_manifest.parquet"
        if not path.exists():
            return 0
        try:
            frame = pl.read_parquet(path)
        except Exception:
            path.unlink(missing_ok=True)
            return 0
        if frame.is_empty():
            path.unlink(missing_ok=True)
            return 0
        if country is None:
            removed = frame.height
            path.unlink(missing_ok=True)
            return removed
        if "country" not in frame.columns:
            return 0
        keep = frame.filter(pl.col("country").cast(pl.Utf8) != country)
        removed = frame.height - keep.height
        if removed <= 0:
            return 0
        if keep.is_empty():
            path.unlink(missing_ok=True)
            return removed
        temporary = path.with_suffix(".tmp.parquet")
        keep.write_parquet(temporary)
        temporary.replace(path)
        return removed

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
        deleted = False
        if not target.exists():
            deleted = False
        else:
            shutil.rmtree(target)
            deleted = True
        removed_history = self.delete_ingestion_history(country)
        return deleted or removed_history > 0

    def export_countries(self, countries: list[str], *, target_dir: Path | None = None) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_countries = "_".join(sorted(countries)) or "all"
        export_dir = target_dir or self.settings.qm_export_dir
        export_dir.mkdir(parents=True, exist_ok=True)
        target = export_dir / f"sds-quantum-metric-export-{safe_countries}-{timestamp}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest = {
                "schema_version": "1.3",
                "created_at": datetime.now(UTC).isoformat(),
                "countries": countries,
                "includes": [
                    "manifest.json",
                    "config/quantum_config.json",
                    "parquet",
                    "reports",
                    "schemas",
                ],
                "checksum": "",
            }
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            quantum_config = self.settings.config_dir / "quantum_config.json"
            if not quantum_config.exists():
                quantum_config = self.settings.config_dir / "quantum.json"
            if quantum_config.exists():
                archive.writestr(
                    "config/quantum_config.json",
                    json.dumps(_safe_json_file(quantum_config), indent=2),
                )
                archive.writestr(
                    "config/dashboards.json",
                    json.dumps(_dashboards_manifest(_safe_json_file(quantum_config)), indent=2),
                )
            for country in countries:
                root = self.settings.parquet_dir / f"country={country}"
                if not root.exists():
                    continue
                for file in root.rglob("*.parquet"):
                    archive.write(file, file.relative_to(self.settings.qm_data_dir))
            reports = self.settings.reports_dir
            if reports.exists():
                for file in reports.rglob("*"):
                    if file.is_file():
                        archive.write(file, file.relative_to(self.settings.qm_data_dir))
            archive.writestr(
                "schemas/export_contract.json",
                json.dumps(
                    {
                        "schema_version": "1.3",
                        "redaction_policy": "browser session material is excluded",
                    },
                    indent=2,
                ),
            )
        self._write_latest_export(target)
        return target

    def latest_export(self) -> dict[str, Any] | None:
        path = self.settings.exports_dir / "latest_export.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def import_zip(self, zip_path: Path) -> dict[str, Any]:
        raw_rows_by_country: dict[str, list[dict[str, Any]]] = {}
        dataset_files: list[tuple[Path, bytes]] = []
        config_files: list[tuple[Path, bytes]] = []
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            if "manifest.json" not in names:
                raise ValueError("ZIP does not include manifest.json.")
            manifest = json.loads(archive.read("manifest.json"))
            countries = set(manifest.get("countries") or [])
            for name in names:
                if name.startswith("config/"):
                    relative = PurePosixPath(name)
                    if ".." in relative.parts or relative.is_absolute():
                        raise ValueError(f"Unsafe ZIP path: {name}")
                    if name == "config/dashboards.json":
                        _reject_secret_config(json.loads(archive.read(name)))
                        continue
                    if name not in {"config/quantum.json", "config/quantum_config.json"}:
                        raise ValueError(f"Unexpected config path: {name}")
                    config_payload = json.loads(archive.read(name))
                    _reject_secret_config(config_payload)
                    config_files.append(
                        (
                            self.settings.config_dir / "quantum_config.json",
                            json.dumps(config_payload, indent=2).encode(),
                        )
                    )
                    continue
                if not name.startswith("parquet/") or not name.endswith(".parquet"):
                    continue
                relative = PurePosixPath(name)
                if ".." in relative.parts or relative.is_absolute():
                    raise ValueError(f"Unsafe ZIP path: {name}")
                if len(relative.parts) < 4 or not relative.parts[1].startswith("country="):
                    raise ValueError(f"Unexpected dataset path: {name}")

                country = relative.parts[1].split("=", 1)[1]
                if countries and country not in countries:
                    raise ValueError(f"Dataset country {country} is not listed in manifest.")

                data = archive.read(name)
                frame = pl.read_parquet(io.BytesIO(data))
                dataset_path = "/".join(relative.parts[2:-1])
                if dataset_path == "raw_api_calls":
                    raw_rows_by_country.setdefault(country, []).extend(frame.to_dicts())
                    continue

                destination = (self.settings.qm_data_dir / Path(*relative.parts)).resolve()
                destination.relative_to(self.settings.qm_data_dir.resolve())
                dataset_files.append((destination, data))

        imported_raw_files = 0
        for country, rows in raw_rows_by_country.items():
            self.merge_raw_calls(country, rows)
            imported_raw_files += 1
        for destination, data in dataset_files:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        for destination, data in config_files:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        return {
            "imported_files": imported_raw_files + len(dataset_files) + len(config_files),
            "manifest": manifest,
        }

    def migrate_legacy_data(self, legacy_root: Path) -> dict[str, Any]:
        source = legacy_root / "parquet"
        if not source.exists():
            return {"migrated_files": 0, "source": str(legacy_root)}
        migrated = 0
        for file in source.glob("country=*"):
            if not file.is_dir():
                continue
            country = file.name.split("=", 1)[1]
            for parquet_file in file.rglob("*.parquet"):
                entity = str(parquet_file.parent.relative_to(file))
                frame = pl.read_parquet(parquet_file)
                if entity == "raw_api_calls":
                    self.merge_raw_calls(country, frame.to_dicts())
                elif not frame.is_empty():
                    destination = (
                        self.settings.parquet_dir
                        / f"country={country}"
                        / entity
                        / parquet_file.name
                    )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if not destination.exists():
                        shutil.copy2(parquet_file, destination)
                migrated += 1
        return {"migrated_files": migrated, "source": str(legacy_root)}

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
        if frame.is_empty():
            return None
        timestamps = [
            value
            for value in (_row_range_end(row) for row in frame.to_dicts())
            if value is not None
        ]
        return max(timestamps) if timestamps else None

    def covered_source_ranges(self, country: str) -> list[tuple[datetime, datetime]]:
        files = self._raw_call_files(country)
        if not files:
            return []
        try:
            frame = self._read_parquet_files(files)
        except Exception:
            return []
        ranges = [
            (start, end)
            for start, end in (
                (_row_range_start(row), _row_range_end(row)) for row in frame.to_dicts()
            )
            if start is not None and end is not None and start <= end
        ]
        return _merge_source_ranges(ranges)

    def day_coverage(
        self,
        country: str,
        start: str | date | datetime | None,
        end: str | date | datetime | None,
    ) -> dict[str, Any]:
        start_day = parse_date(start)
        end_day = parse_date(end)
        if start_day is None and end_day is None:
            return {
                "country": country,
                "start": None,
                "end": None,
                "complete": True,
                "covered_days": [],
                "missing_days": [],
                "message": "Sin rango seleccionado.",
            }
        start_day = start_day or end_day
        end_day = end_day or start_day
        if start_day is None or end_day is None:
            raise ValueError("Invalid coverage date range.")
        if end_day < start_day:
            start_day, end_day = end_day, start_day
        requested_days = _days_between(start_day, end_day)
        covered = self._manifest_covered_days(country)
        if not covered:
            covered = self._covered_days_from_source_ranges(country, requested_days)
        covered_days = [day for day in requested_days if day in covered]
        missing_days = [day for day in requested_days if day not in covered]
        return {
            "country": country,
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "complete": not missing_days,
            "covered_days": [day.isoformat() for day in covered_days],
            "missing_days": [day.isoformat() for day in missing_days],
            "message": _coverage_message(missing_days),
        }

    def _raw_call_files(self, country: str) -> list[Path]:
        daily = self._daily_raw_call_files(country)
        if daily:
            return daily
        return self._legacy_raw_call_files(country)

    def _legacy_raw_call_files(self, country: str) -> list[Path]:
        root = self.settings.parquet_dir / f"country={country}" / "raw_api_calls"
        return sorted(root.glob("*.parquet")) if root.exists() else []

    def _daily_raw_call_files(self, country: str) -> list[Path]:
        root = self.settings.parquet_dir / f"country={country}"
        return sorted(root.glob("day=*/raw_api_calls/*.parquet")) if root.exists() else []

    def _country_dataset_files(self, country: str, dataset_path: str) -> list[Path]:
        root = self.settings.parquet_dir / f"country={country}" / dataset_path
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
        new_range_keys = {_row_range_key(row) for row in new_rows}
        kept: list[dict[str, Any]] = []
        replaced = 0
        for row in frame.to_dicts():
            if _row_range_key(row) in new_range_keys and _row_overlaps(row, bounds):
                replaced += 1
            else:
                kept.append(row)
        if kept:
            return pl.DataFrame(kept, infer_schema_length=None), replaced
        return pl.DataFrame(schema=frame.schema), replaced

    def _publish_daily_raw_calls(self, country: str, frame: pl.DataFrame) -> None:
        if frame.is_empty():
            return
        root = self.settings.parquet_dir / f"country={country}"
        for day_dir in root.glob("day=*"):
            if day_dir.is_dir():
                shutil.rmtree(day_dir)
        rows_by_day: dict[date, list[dict[str, Any]]] = {}
        for row in frame.to_dicts():
            day = _row_source_day(row)
            if day is None:
                continue
            rows_by_day.setdefault(day, []).append(row)
        if not rows_by_day:
            return
        coverage_rows: list[dict[str, Any]] = []
        for day, rows in sorted(rows_by_day.items()):
            target = root / f"day={day.isoformat()}" / "raw_api_calls"
            target.mkdir(parents=True, exist_ok=True)
            path = target / COMPACTED_RAW_CALLS_FILE
            temporary = path.with_suffix(".tmp.parquet")
            pl.DataFrame(
                [_parquet_safe_row(row) for row in rows],
                infer_schema_length=None,
            ).write_parquet(temporary)
            temporary.replace(path)
            starts = [_row_range_start(row) for row in rows]
            ends = [_row_range_end(row) for row in rows]
            coverage_rows.append(
                {
                    "country": country,
                    "day": day.isoformat(),
                    "status": "complete",
                    "raw_calls": len(rows),
                    "source_start": min(value for value in starts if value is not None)
                    if any(starts)
                    else None,
                    "source_end": max(value for value in ends if value is not None)
                    if any(ends)
                    else None,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
        manifests = root / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        path = manifests / DAY_COVERAGE_FILE
        temporary = path.with_suffix(".tmp.parquet")
        pl.DataFrame(coverage_rows).write_parquet(temporary)
        temporary.replace(path)

    def _manifest_covered_days(self, country: str) -> set[date]:
        path = self.settings.parquet_dir / f"country={country}" / "manifests" / DAY_COVERAGE_FILE
        if not path.exists():
            return set()
        try:
            rows = pl.read_parquet(path).to_dicts()
        except Exception:
            return set()
        days: set[date] = set()
        for row in rows:
            if row.get("status") != "complete":
                continue
            parsed = parse_date(row.get("day"))
            if parsed:
                days.add(parsed)
        return days

    def _covered_days_from_source_ranges(
        self, country: str, requested_days: list[date]
    ) -> set[date]:
        ranges = self.covered_source_ranges(country)
        covered: set[date] = set()
        for day in requested_days:
            start, end = _day_bounds(day)
            if any(range_start <= start and range_end >= end for range_start, range_end in ranges):
                covered.add(day)
        return covered

    def _write_latest_export(self, path: Path) -> None:
        self.settings.exports_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "exported",
            "path": str(path),
            "filename": path.name,
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        target = self.settings.exports_dir / "latest_export.json"
        temporary = target.with_suffix(".tmp.json")
        temporary.write_text(json.dumps(payload, indent=2))
        temporary.replace(target)


def hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _parquet_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple)):
            safe[key] = json.dumps(sanitize(value), ensure_ascii=False, default=str)
        else:
            safe[key] = sanitize(value)
    return safe


def _parquet_rich_row(row: dict[str, Any]) -> dict[str, Any]:
    rich: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str) and value[:1] in {"{", "["}:
            try:
                rich[key] = json.loads(value)
                continue
            except json.JSONDecodeError:
                pass
        rich[key] = value
    return rich


def _safe_json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Config payload must be a JSON object.")
    _reject_secret_config(payload)
    return cast(dict[str, Any], sanitize(payload))


def _reject_secret_config(payload: Any) -> None:
    serialized = json.dumps(payload, sort_keys=True, default=str).casefold()
    forbidden = ("cookie", "authorization", "secret", "token")
    if any(item in serialized for item in forbidden):
        raise ValueError("Config import/export payload contains secret-looking fields.")


def _dashboards_manifest(config: dict[str, Any]) -> dict[str, Any]:
    countries = config.get("countries")
    return {
        "schema_version": "1.4",
        "countries": [
            {
                "country": country.get("country"),
                "dashboards": country.get("dashboards") or [],
            }
            for country in countries
            if isinstance(country, dict)
        ]
        if isinstance(countries, list)
        else [],
    }


def _source_bounds(rows: list[dict[str, Any]]) -> tuple[datetime, datetime] | None:
    starts = [_row_range_start(row) for row in rows]
    ends = [_row_range_end(row) for row in rows]
    valid_starts = [value for value in starts if value is not None]
    valid_ends = [value for value in ends if value is not None]
    if not valid_starts or not valid_ends:
        return None
    return min(valid_starts), max(valid_ends)


def _row_overlaps(row: dict[str, Any], bounds: tuple[datetime, datetime]) -> bool:
    start = _row_range_start(row)
    end = _row_range_end(row)
    if start is None or end is None:
        return False
    lower, upper = bounds
    return start <= upper and end >= lower


def _row_range_key(row: dict[str, Any]) -> str:
    value = row.get("range_key")
    if value is None or str(value).strip() == "":
        return "today"
    return str(value).strip()


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


def _row_source_day(row: dict[str, Any]) -> date | None:
    source = _row_range_start(row) or _parse_source_ts(row.get("ingestion_ts"))
    if source is None:
        return None
    return source.astimezone(zoneinfo_for("CST")).date()


def _row_range_start(row: dict[str, Any]) -> datetime | None:
    return _parse_source_ts(row.get("source_ts_start")) or _parse_source_ts(
        row.get("capture_chunk_start")
    )


def _row_range_end(row: dict[str, Any]) -> datetime | None:
    return _parse_source_ts(row.get("source_ts_end")) or _parse_source_ts(
        row.get("capture_chunk_end")
    )


def _days_between(start: date, end: date) -> list[date]:
    total_days = (end - start).days
    return [start + timedelta(days=index) for index in range(total_days + 1)]


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    zone = zoneinfo_for("CST")
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day, time.max.replace(microsecond=0), tzinfo=zone).astimezone(UTC)
    return start, end


def _coverage_message(missing_days: list[date]) -> str:
    if not missing_days:
        return "Periodo completo en Parquet."
    if len(missing_days) == 1:
        return f"Falta 1 dia para completar el periodo: {missing_days[0].isoformat()}."
    return f"Faltan {len(missing_days)} dias para completar el periodo."


def _dashboard_scoped_scan(
    scan: pl.LazyFrame,
    dashboard_id: str,
) -> pl.LazyFrame | None:
    try:
        columns = set(scan.collect_schema().names())
    except Exception:
        return None
    if "dashboard_id" not in columns:
        return None
    dashboard_col = pl.col("dashboard_id").cast(pl.Utf8)
    scoped = scan.filter(dashboard_col == dashboard_id)
    matching_rows = int(scoped.select(pl.len()).collect().item())
    return scoped if matching_rows else None


def _sample_row(scan: pl.LazyFrame) -> dict[str, Any]:
    try:
        rows = scan.head(1).collect().to_dicts()
    except Exception:
        return {}
    return rows[0] if rows else {}


def _entity_category(relative: str) -> str:
    if relative == "raw_api_calls" or "/raw_api_calls" in relative:
        return "RAW"
    if relative == "visual_contracts":
        return "Visual Contracts"
    if relative == "dashboard_cards":
        return "Dashboard Metadata"
    if relative.startswith("derived/"):
        return "Derived"
    if relative.startswith("regression/"):
        return "Regression"
    if relative.startswith("manifests"):
        return "Manifest"
    return "Config"


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _merge_source_ranges(
    ranges: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = []
    for start, end in ordered:
        if not merged:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged
