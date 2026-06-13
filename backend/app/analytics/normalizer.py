from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

SUMMARY_METRICS = (
    "page_views",
    "sessions",
    "converted_sessions",
    "avg_session_time",
)

ERROR_METRICS = ("sessions_with_error", "error_session_percent")

KNOWN_DIMENSIONS = (
    "application_type",
    "application_version",
    "ai_detected",
    "browser",
    "active_fix",
    "active_test",
    "app_name",
    "operating_system",
    "platform",
    "device_type",
)

METRIC_ALIASES: dict[str, set[str]] = {
    "page_views": {
        "page_views",
        "pageviews",
        "page_view_count",
        "page view count",
        "page views",
        "paginas vistas",
        "páginas vistas",
        "views",
    },
    "sessions": {
        "sessions",
        "session_count",
        "sesiones",
        "total_sessions",
    },
    "converted_sessions": {
        "converted_sessions",
        "conversion_sessions",
        "sessions_with_conversion",
        "sessions with conversion",
        "sesiones con conversion",
        "sesiones con conversión",
        "general conversiones",
        "general - conversiones",
        "conversiones",
        "conversions",
    },
    "avg_session_time": {
        "avg_session_time",
        "average_session_duration",
        "avg_session_duration",
        "average session duration",
        "average_session_time",
        "session_duration",
        "tiempo medio de sesion",
        "tiempo medio de sesión",
    },
    "sessions_with_error": {
        "sessions_with_error",
        "error_sessions",
        "sessions with error",
        "sesiones con error",
        "errored_sessions",
        "sessions_error",
    },
    "error_session_percent": {
        "error_session_percent",
        "error_session_percentage",
        "sessions_with_error_percent",
        "percent_sessions_with_error",
        "error rate",
        "error_rate",
        "% sesiones con error",
        "porcentaje sesiones con error",
    },
    "page_views_delta_percent": {
        "page_views_delta_percent",
        "page_views_delta",
        "page views delta percent",
        "page views historical delta",
    },
    "conversions_delta_percent": {
        "conversions_delta_percent",
        "converted_sessions_delta_percent",
        "conversiones_delta_percent",
        "conversions historical delta",
    },
}

DIMENSION_ALIASES: dict[str, set[str]] = {
    "application_type": {"application_type", "application type", "app_type"},
    "application_version": {"application_version", "application version", "app_version"},
    "ai_detected": {"ai_detected", "ai detected"},
    "browser": {"browser", "browser_name"},
    "active_fix": {"active_fix", "active fix"},
    "active_test": {"active_test", "active test"},
    "app_name": {"app_name", "app name", "application_name", "application name", "name"},
    "operating_system": {"operating_system", "operating system", "os", "os_name"},
    "platform": {"platform"},
    "device_type": {"device_type", "device type", "device"},
}

INTERNAL_KEYS = {
    "id",
    "uuid",
    "query_id",
    "dashboard_id",
    "card_id",
    "row_count",
}


@dataclass(frozen=True)
class NormalizedRecord:
    country: str
    ingestion_id: str
    ingestion_ts: str | None
    dashboard_id: str | None
    card_id: str | None
    card_type: str | None
    view_name: str | None
    metric_ids: tuple[str, ...]
    query_hash: str | None
    response_hash: str | None
    source_endpoint: str | None
    period_start: str | None
    period_end: str | None
    dimensions: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    raw_evidence_path: str | None = None

    def dimension(self, key: str) -> str | None:
        value = self.dimensions.get(key)
        if value in {None, ""}:
            return None
        return value

    def metric(self, key: str) -> float | None:
        return self.metrics.get(key)


@dataclass(frozen=True)
class NormalizedDataset:
    country: str
    records: list[NormalizedRecord]
    raw_calls: int
    response_rows: int
    last_ingestion_at: str | None
    discovered_dimensions: dict[str, str]
    available_datasets: list[str]

    @property
    def has_parseable_rows(self) -> bool:
        return bool(self.records)


def normalize_raw_calls(
    country: str,
    raw_calls: list[dict[str, Any]],
    available_datasets: list[str],
) -> NormalizedDataset:
    records: list[NormalizedRecord] = []
    discovered_dimensions: dict[str, str] = {}
    response_rows = 0
    last_ingestion_at: str | None = None

    for call in raw_calls:
        ingestion_ts = _optional_string(call.get("ingestion_ts"))
        if ingestion_ts and (last_ingestion_at is None or ingestion_ts > last_ingestion_at):
            last_ingestion_at = ingestion_ts

        request_json = parse_json_object(call.get("request_json"))
        response_json = parse_json_object(call.get("response_json"))
        query = _query_from_request(request_json)
        metadata_value = query.get("metadata")
        metadata = metadata_value if isinstance(metadata_value, dict) else {}

        for key, label in extract_query_dimensions(query).items():
            discovered_dimensions.setdefault(key, label)

        metric_ids = _metric_ids(call.get("metric_ids"), metadata.get("metricIds"))
        rows = extract_response_rows(response_json)
        response_rows += len(rows)
        if not rows:
            rows = _stats_as_rows(response_json)

        for row_index, row in enumerate(rows):
            flat_row = flatten_row(row)
            dimensions = extract_dimensions(flat_row)
            for key in dimensions:
                discovered_dimensions.setdefault(key, humanize_key(key))

            metrics = extract_metrics(flat_row)
            if not dimensions and not metrics:
                continue

            for key in dimensions:
                discovered_dimensions.setdefault(key, humanize_key(key))

            records.append(
                NormalizedRecord(
                    country=country,
                    ingestion_id=str(call.get("ingestion_id") or ""),
                    ingestion_ts=ingestion_ts,
                    dashboard_id=_optional_string(
                        call.get("dashboard_id") or metadata.get("dashboardId")
                    ),
                    card_id=_optional_string(call.get("card_id") or metadata.get("cardId")),
                    card_type=_optional_string(call.get("card_type") or metadata.get("cardType")),
                    view_name=_optional_string(call.get("view_name") or metadata.get("viewName")),
                    metric_ids=metric_ids,
                    query_hash=_optional_string(call.get("query_hash")),
                    response_hash=_optional_string(call.get("response_hash")),
                    source_endpoint=_optional_string(call.get("source_endpoint")),
                    period_start=_optional_string(call.get("source_ts_start")),
                    period_end=_optional_string(call.get("source_ts_end")),
                    dimensions=dimensions,
                    metrics=metrics,
                    raw_evidence_path=f"response_json.rows[{row_index}]",
                )
            )

    return NormalizedDataset(
        country=country,
        records=records,
        raw_calls=len(raw_calls),
        response_rows=response_rows,
        last_ingestion_at=last_ingestion_at,
        discovered_dimensions=discovered_dimensions,
        available_datasets=available_datasets,
    )


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def extract_response_rows(response_json: dict[str, Any]) -> list[Any]:
    rows = _find_rows(response_json)
    if rows is None:
        return []
    columns = _find_columns(response_json)
    normalized_rows: list[Any] = []
    for row in rows:
        if isinstance(row, list) and columns and len(columns) == len(row):
            normalized_rows.append(dict(zip(columns, row, strict=True)))
        else:
            normalized_rows.append(row)
    return normalized_rows


def flatten_row(value: Any) -> dict[str, Any]:
    flat: dict[str, Any] = {}

    def visit(current: Any, prefix: str) -> None:
        if isinstance(current, dict):
            for raw_key, nested in current.items():
                key = str(raw_key)
                canonical = canonicalize_key(key)
                full_key = f"{prefix}_{canonical}" if prefix else canonical
                visit(nested, full_key)
                if not isinstance(nested, (dict, list)) and canonical not in flat:
                    flat[canonical] = nested
        elif isinstance(current, list):
            if all(not isinstance(item, (dict, list)) for item in current):
                flat[prefix] = ", ".join(str(item) for item in current)
        elif prefix:
            flat[prefix] = current

    visit(value, "")
    return flat


def extract_dimensions(flat_row: dict[str, Any]) -> dict[str, str]:
    dimensions: dict[str, str] = {}
    canonical_to_alias = _alias_lookup(DIMENSION_ALIASES)
    canonical_row = {canonicalize_key(key): value for key, value in flat_row.items()}

    for canonical_key, value in canonical_row.items():
        dimension_key = canonical_to_alias.get(canonical_key)
        if dimension_key and (text := _clean_text(value)):
            dimensions[dimension_key] = text

    for key, value in canonical_row.items():
        if key in dimensions or key in INTERNAL_KEYS or key in canonical_to_alias:
            continue
        if _to_number(value) is not None:
            continue
        text = _clean_text(value)
        if text:
            dimensions.setdefault(key, text)

    if "app_name" not in dimensions and (name := _clean_text(canonical_row.get("name"))):
        dimensions["app_name"] = name

    return dimensions


def extract_metrics(flat_row: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    canonical_to_alias = _alias_lookup(METRIC_ALIASES)
    for raw_key, value in flat_row.items():
        canonical_key = canonicalize_key(raw_key)
        metric_key = canonical_to_alias.get(canonical_key)
        if not metric_key:
            continue
        number = _to_number(value)
        if number is not None:
            metrics[metric_key] = number

    metric_name = _clean_text(flat_row.get("metric_name") or flat_row.get("name"))
    metric_value = _to_number(flat_row.get("metric_value") or flat_row.get("value"))
    if metric_name and metric_value is not None:
        metric_key = canonical_to_alias.get(canonicalize_key(metric_name))
        if metric_key:
            metrics[metric_key] = metric_value

    return metrics


def extract_query_dimensions(query: dict[str, Any]) -> dict[str, str]:
    discovered: dict[str, str] = {}
    for container_key in ("dimensions", "dimensionFills"):
        container = query.get(container_key)
        if not isinstance(container, dict):
            continue
        values = container.get(container_key)
        if not isinstance(values, list):
            values = container.get("dimensions") or container.get("dimensionFills")
        if not isinstance(values, list):
            continue
        for item in values:
            key, label = _dimension_from_query_item(item)
            if key:
                discovered.setdefault(key, label or humanize_key(key))

    metadata = query.get("metadata")
    if isinstance(metadata, dict):
        for raw_key, raw_value in metadata.items():
            key = canonicalize_key(str(raw_key))
            if key.endswith("dimension") or key.endswith("dimension_id"):
                text = _clean_text(raw_value)
                if text:
                    discovered.setdefault(canonicalize_key(text), humanize_key(text))

    return discovered


def canonicalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.replace("%", " percent ")
    ascii_value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", ascii_value)
    ascii_value = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value).strip("_")
    return ascii_value.lower()


def humanize_key(value: str) -> str:
    text = canonicalize_key(value).replace("_", " ").strip()
    if not text:
        return value
    return " ".join(word.capitalize() for word in text.split())


def _query_from_request(request_json: dict[str, Any]) -> dict[str, Any]:
    query = request_json.get("query")
    return query if isinstance(query, dict) else request_json


def _find_rows(value: Any, depth: int = 0) -> list[Any] | None:
    if depth > 4:
        return None
    if isinstance(value, dict):
        rows = value.get("rows")
        if isinstance(rows, list):
            return rows
        for nested in value.values():
            found = _find_rows(nested, depth + 1)
            if found is not None:
                return found
    return None


def _stats_as_rows(response_json: dict[str, Any]) -> list[Any]:
    stats = response_json.get("stats")
    if isinstance(stats, dict) and any(_to_number(value) is not None for value in stats.values()):
        return [stats]
    return []


def _find_columns(value: Any, depth: int = 0) -> list[str] | None:
    if depth > 4:
        return None
    if isinstance(value, dict):
        columns = value.get("columns") or value.get("columnNames")
        if isinstance(columns, list):
            parsed = [_column_name(column) for column in columns]
            if all(parsed):
                return [column for column in parsed if column]
        for nested in value.values():
            found = _find_columns(nested, depth + 1)
            if found is not None:
                return found
    return None


def _column_name(value: Any) -> str | None:
    if isinstance(value, str):
        return canonicalize_key(value)
    if isinstance(value, dict):
        for key in ("key", "name", "id", "label"):
            text = _clean_text(value.get(key))
            if text:
                return canonicalize_key(text)
    return None


def _alias_lookup(aliases: dict[str, set[str]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, names in aliases.items():
        lookup[canonicalize_key(canonical)] = canonical
        for name in names:
            lookup[canonicalize_key(name)] = canonical
    return lookup


def _dimension_from_query_item(item: Any) -> tuple[str | None, str | None]:
    if isinstance(item, str):
        return canonicalize_key(item), humanize_key(item)
    if not isinstance(item, dict):
        return None, None
    raw_key = (
        item.get("id")
        or item.get("key")
        or item.get("name")
        or item.get("dimension")
        or item.get("field")
    )
    raw_label = item.get("label") or item.get("displayName") or item.get("name")
    key_text = _clean_text(raw_key)
    if not key_text:
        return None, None
    label = _clean_text(raw_label) or humanize_key(key_text)
    return canonicalize_key(key_text), label


def _metric_ids(raw_value: Any, metadata_value: Any) -> tuple[str, ...]:
    value = raw_value if raw_value not in (None, "", "[]") else metadata_value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
        if isinstance(parsed, list):
            return tuple(str(item) for item in parsed)
        return (str(parsed),)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _clean_text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return None
    return text


def _to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    clean = value.strip().replace("%", "").replace(",", "")
    if not clean:
        return None
    try:
        return float(clean)
    except ValueError:
        return None
