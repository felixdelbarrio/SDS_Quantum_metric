# ruff: noqa: E501
from __future__ import annotations

import re
import unicodedata
from typing import Any

_CAPTURE_SCRIPT = r"""
() => {
  const uniqueText = (nodes) => {
    const values = [];
    for (const node of Array.from(nodes)) {
      const value = (node.textContent || "").trim();
      if (value && !values.includes(value)) values.push(value);
    }
    return values;
  };
  const cards = [];
  for (const root of Array.from(document.querySelectorAll("[data-card-id]"))) {
    const widgetId = root.getAttribute("data-card-id");
    const titleNode = root.querySelector('[data-testid="dashboard-card-title-link"]');
    const title = (titleNode?.textContent || "").trim();
    if (!widgetId || !title) continue;
    const kpis = Array.from(root.querySelectorAll(".kpi-segment-comparison"))
      .map((node) => ({
        label: (node.querySelector(".kpi-title")?.textContent || "").trim(),
        formatted: (node.querySelector('[data-testid="kpi-metric-data"]')?.textContent || "").trim(),
      }))
      .filter((item) => item.label && item.formatted);
    const kpiNode = root.querySelector(".sandbox-kpi-value") || root.querySelector('[data-testid="kpi-metric-data"]');
    const formatted = kpis[0]?.formatted || (kpiNode?.textContent || "").trim().split("\n")[0].trim();
    const trend = root.querySelector(".qm-trend");
    const chartNode = root.querySelector("[data-pivot-hook]") || root.querySelector('[data-testid="multi-line-chart"]');
    const chartSvg = chartNode?.querySelector("svg") || null;
    const chartPaths = chartSvg ? Array.from(chartSvg.querySelectorAll("path")) : [];
    const plotDomain = chartSvg?.querySelector("g.x.axis path.domain") || null;
    const plotBounds = plotDomain?.getBBox() || null;
    const legendNodes = root.querySelectorAll(".chart-legend .legend-item");
    const period = (root.querySelector(".panel-date-interior")?.textContent || "").trim();
    const table = root.querySelector("table");
    const emptyTable = !table && /No Results Found\.?/i.test(root.textContent || "");
    const tableHeaders = table
      ? Array.from(table.querySelectorAll("thead th")).map((cell) => ({
          label: (cell.textContent || "").trim(),
          columnId: cell.getAttribute("data-column-id"),
          active: Boolean(cell.querySelector(".Mui-active")),
          direction: cell.getAttribute("aria-sort"),
        }))
      : [];
    const tableRows = table
      ? Array.from(table.querySelectorAll("tbody tr")).map((row) => ({
          cells: Array.from(row.querySelectorAll("td")).map((cell) => ({
            columnId: cell.getAttribute("data-column-id"),
            main: (
              cell.querySelector(".metric-value")?.textContent ||
              cell.querySelector(".item-name")?.textContent ||
              cell.querySelector(".qm--table-cell-content")?.textContent ||
              ""
            ).trim(),
            delta: (cell.querySelector('[data-testid="qm-trend-metric"]')?.textContent || "").trim(),
            intent: String(cell.querySelector(".qm-trend")?.className || ""),
          })),
        }))
      : [];
    cards.push({
      widgetId,
      title,
      formatted,
      kpis,
      comparison: trend
        ? {
            formatted: (trend.querySelector('[data-testid="qm-trend-metric"]')?.textContent || "").trim(),
            label: (trend.querySelector(".qm-trend-baseline")?.textContent || "").trim(),
            className: String(trend.className || ""),
            directionPath: trend.querySelector(".qm-trend-direction-icon path")?.getAttribute("d") || "",
          }
        : null,
      chart: chartNode
        ? {
            pivotHook: chartNode.getAttribute("data-pivot-hook") || chartNode.getAttribute("data-testid") || "",
            xTicks: chartSvg ? uniqueText(chartSvg.querySelectorAll("g.x.axis text")) : [],
            yTicks: chartSvg ? uniqueText(chartSvg.querySelectorAll("g.y.axis text")) : [],
            legends: uniqueText(legendNodes),
            period,
            seriesData: chartPaths
              .filter((path) => Array.isArray(path.__data__?.values))
              .map((path) => ({
                id: path.__data__.id,
                label: path.__data__.text,
                values: path.__data__.values,
                dasharray: getComputedStyle(path).strokeDasharray,
              })),
            bandsData: chartPaths
              .filter((path) => Array.isArray(path.__data__?.points))
              .map((path) => ({ points: path.__data__.points })),
            whiskersData: chartSvg
              ? Array.from(chartSvg.querySelectorAll("g.bar-whisker"))
                  .filter((group) => Array.isArray(group.__data__) && group.__data__.length >= 2)
                  .map((group) => ({ low: group.__data__[0], high: group.__data__[1] }))
              : [],
            highlightsData: chartSvg
              ? Array.from(chartSvg.querySelectorAll("rect.backdrop"))
                  .filter((rect) => rect.__data__?.start != null && rect.__data__?.end != null)
                  .map((rect) => {
                    const x = Number(rect.getAttribute("x") || 0);
                    const width = Number(rect.getAttribute("width") || 0);
                    const plotX = Number(plotBounds?.x || 0);
                    const plotWidth = Number(plotBounds?.width || 0);
                    return {
                      start: rect.__data__.start,
                      end: rect.__data__.end,
                      label: rect.__data__.name || "Anomaly",
                      startX: plotWidth ? (x - plotX) / plotWidth : null,
                      endX: plotWidth ? (x + width - plotX) / plotWidth : null,
                    };
                  })
              : [],
          }
        : null,
      table: table
        ? {
            headers: tableHeaders,
            rows: tableRows,
            period,
          }
        : emptyTable
          ? { headers: [], rows: [], period, empty: true }
          : null,
    });
  }
  return cards;
}
"""


def collect_visible_widget_contracts(page: Any, *, timezone: str) -> dict[str, dict[str, Any]]:
    captured = page.evaluate(_CAPTURE_SCRIPT)
    if not isinstance(captured, list):
        return {}
    contracts: dict[str, dict[str, Any]] = {}
    for item in captured:
        if not isinstance(item, dict):
            continue
        widget_id = _text(item.get("widgetId"))
        if not widget_id:
            continue
        contract = _contract_from_dom(item, timezone=timezone)
        if contract:
            contracts[widget_id] = contract
    return contracts


def merge_visual_contract_maps(
    current: dict[str, dict[str, Any]],
    captured: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    for widget_id, contract in captured.items():
        current[widget_id] = merge_visual_contracts(current.get(widget_id, {}), contract)
    return current


def merge_visual_contracts(
    configured: dict[str, Any] | None,
    captured: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(configured or {})
    for key, value in (captured or {}).items():
        previous = merged.get(key)
        if isinstance(previous, dict) and isinstance(value, dict):
            merged[key] = merge_visual_contracts(previous, value)
        elif isinstance(value, list):
            if not value:
                continue
            if isinstance(previous, list) and _data_richness(previous) > _data_richness(value):
                continue
            merged[key] = value
        elif value not in (None, ""):
            merged[key] = value
    return merged


def visual_contracts_are_complete(contracts: dict[str, dict[str, Any]]) -> bool:
    for contract in contracts.values():
        chart = contract.get("chart")
        if not isinstance(chart, dict):
            continue
        legend_labels = [
            str(item.get("label") or "").casefold()
            for item in chart.get("legends") or []
            if isinstance(item, dict)
        ]
        series = [item for item in chart.get("series") or [] if isinstance(item, dict)]
        bands = [item for item in chart.get("bands") or [] if isinstance(item, dict)]
        if any("baseline" in label for label in legend_labels) and not any(
            item.get("kind") == "baseline" and item.get("points") for item in series
        ):
            return False
        if any("historical range" in label for label in legend_labels) and not any(
            item.get("kind") == "historical_range"
            and item.get("lower_points")
            and item.get("upper_points")
            for item in bands
        ):
            return False
    return True


def _contract_from_dom(item: dict[str, Any], *, timezone: str) -> dict[str, Any]:
    contract: dict[str, Any] = {}
    formatted = _text(item.get("formatted"))
    if formatted:
        contract.update(_number_display_contract(formatted))
    breakdown = []
    for value in item.get("kpis") or []:
        if not isinstance(value, dict):
            continue
        label = _text(value.get("label"))
        segment_formatted = _text(value.get("formatted"))
        if label and segment_formatted:
            breakdown.append(
                {
                    "label": label,
                    "display": _number_display_contract(segment_formatted),
                }
            )
    if breakdown:
        contract["breakdown"] = breakdown
    comparison = item.get("comparison")
    if isinstance(comparison, dict):
        parsed_comparison = _comparison_contract(comparison)
        if parsed_comparison:
            contract["comparison"] = parsed_comparison
    chart = item.get("chart")
    if isinstance(chart, dict):
        parsed_chart = _chart_contract(chart, contract, timezone=timezone)
        if parsed_chart:
            contract["chart"] = parsed_chart
            contract["visualization_type"] = parsed_chart["chart_type"]
    table = item.get("table")
    if isinstance(table, dict):
        parsed_table = _table_contract(table, timezone=timezone)
        if parsed_table:
            contract["table"] = parsed_table
            contract["visualization_type"] = "table"
    return contract


def _number_display_contract(formatted: str) -> dict[str, Any]:
    normalized = formatted.casefold()
    unit = "percent" if "%" in formatted else "seconds" if "sec" in normalized else "count"
    display_value = _parse_number(formatted)
    scale = 100 if unit == "percent" else 1
    return {
        "raw_value": display_value / scale if display_value is not None else None,
        "display_value": display_value,
        "unit": unit,
        "scale": scale,
        "precision": _display_precision(formatted),
        "suffix": "%" if unit == "percent" else " sec" if unit == "seconds" else None,
        "formatter": "quantum",
        "formatted": formatted,
    }


def _comparison_contract(value: dict[str, Any]) -> dict[str, Any]:
    formatted = _text(value.get("formatted"))
    label = _text(value.get("label"))
    if not formatted or not label:
        return {}
    delta = _parse_number(formatted)
    direction = _trend_direction(_text(value.get("directionPath")) or "")
    if delta is not None and direction:
        delta = abs(delta) * direction
    class_name = str(value.get("className") or "").casefold()
    intent = (
        "positive"
        if " good" in f" {class_name}"
        else "negative"
        if " bad" in f" {class_name}"
        else "neutral"
    )
    signed = formatted
    if delta is not None and not formatted.lstrip().startswith(("+", "-", "<", ">")):
        signed = f"{'+' if delta >= 0 else '-'}{formatted}"
    return {
        "label": label,
        "raw_delta": delta,
        "display_delta": delta,
        "precision": _display_precision(formatted),
        "formatted": signed,
        "semantic_intent": intent,
    }


def _chart_contract(
    value: dict[str, Any],
    display: dict[str, Any],
    *,
    timezone: str,
) -> dict[str, Any]:
    chart_type = _chart_type(_text(value.get("pivotHook")) or "")
    x_labels = _text_list(value.get("xTicks"))
    y_labels = _text_list(value.get("yTicks"))
    legend_labels = _text_list(value.get("legends"))
    period_label = _text(value.get("period"))
    if not chart_type or not period_label:
        return {}
    x_ticks = [
        {
            "value": label,
            "label": label,
            "position": index / max(1, len(x_labels) - 1),
        }
        for index, label in enumerate(x_labels)
    ]
    y_values = [_axis_number(label) for label in y_labels]
    numeric_y = [item for item in y_values if item is not None]
    y_ticks = [
        {
            "value": number if number is not None else label,
            "label": label,
            "position": index / max(1, len(y_labels) - 1),
        }
        for index, (label, number) in enumerate(zip(y_labels, y_values, strict=True))
    ]
    series: list[dict[str, Any]] = []
    bands: list[dict[str, Any]] = []
    legends: list[dict[str, Any]] = []
    series.extend(
        _series_from_dom(
            value.get("seriesData"),
            labels=x_labels,
            scale=float(display.get("scale") or 1),
            chart_type=chart_type,
            legend_labels=legend_labels,
        )
    )
    bands.extend(
        _bands_from_dom(
            value.get("bandsData"),
            whiskers=value.get("whiskersData"),
            labels=x_labels,
            scale=float(display.get("scale") or 1),
        )
    )
    bands.extend(_highlights_from_dom(value.get("highlightsData"), series=series))
    for index, label in enumerate(legend_labels):
        normalized = label.casefold()
        if "historical range" in normalized:
            if not any(item.get("kind") == "historical_range" for item in bands):
                bands.append(
                    {
                        "band_id": f"band-{index}",
                        "label": label,
                        "kind": "historical_range",
                    }
                )
            legends.append({"id": f"legend-{index}", "label": label, "order": index})
            continue
        if "anomaly" in normalized:
            legends.append({"id": f"legend-{index}", "label": label, "order": index})
            continue
        if series:
            legends.append(
                {
                    "id": f"legend-{index}",
                    "label": label,
                    "order": index,
                    "kind": "baseline" if "baseline" in normalized else None,
                    "visible": True,
                }
            )
            continue
        kind = (
            "baseline"
            if "baseline" in normalized
            else "bar"
            if chart_type in {"bar", "stacked_bar"}
            else "line"
        )
        series.append(
            {
                "series_id": f"series-{index}",
                "label": label,
                "kind": kind,
                "order": index,
                "points": [],
                "visible": True,
            }
        )
        legends.append(
            {
                "id": f"legend-{index}",
                "label": label,
                "order": index,
                "kind": kind,
                "visible": True,
            }
        )
    if not series:
        series.append(
            {
                "series_id": "series-0",
                "label": "All Users",
                "kind": "bar" if chart_type in {"bar", "stacked_bar"} else "line",
                "order": 0,
                "points": [],
                "visible": True,
            }
        )
    return {
        "chart_type": chart_type,
        "x_axis": {"ticks": x_ticks},
        "y_axis": {
            "min": min(numeric_y) if numeric_y else None,
            "max": max(numeric_y) if numeric_y else None,
            "unit": display.get("unit"),
            "ticks": y_ticks,
        },
        "series": series,
        "bands": bands,
        "legends": legends,
        "period_label": period_label,
        "timezone": timezone,
        "granularity": "captured",
    }


def _series_from_dom(
    value: Any,
    *,
    labels: list[str],
    scale: float,
    chart_type: str,
    legend_labels: list[str],
) -> list[dict[str, Any]]:
    rows = [item for item in value or [] if isinstance(item, dict)]
    if not rows:
        return []
    ids = [_text(item.get("id")) or _text(item.get("label")) or "All Users" for item in rows]
    baseline_label = next(
        (label for label in legend_labels if "baseline" in label.casefold()),
        "All Users; Baseline",
    )
    series: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        series_id = ids[index]
        dasharray = str(item.get("dasharray") or "").casefold()
        duplicate_before_last = ids.count(series_id) > 1 and index < len(rows) - 1
        is_baseline = dasharray not in {"", "none", "0px"} or duplicate_before_last
        points = _points_from_pairs(item.get("values"), labels=labels, scale=scale)
        if not points:
            continue
        series.append(
            {
                "series_id": f"series-{index}",
                "label": baseline_label if is_baseline else (_text(item.get("label")) or series_id),
                "kind": "baseline"
                if is_baseline
                else "bar"
                if chart_type in {"bar", "stacked_bar"}
                else "line",
                "order": 1 if is_baseline else 0,
                "points": points,
                "visible": True,
                "style": "dashed" if is_baseline else "solid",
            }
        )
    return sorted(series, key=lambda item: int(item["order"]))


def _bands_from_dom(
    value: Any,
    *,
    whiskers: Any,
    labels: list[str],
    scale: float,
) -> list[dict[str, Any]]:
    rows = [item for item in value or [] if isinstance(item, dict)]
    points = [
        item for item in (rows[0].get("points") if rows else []) or [] if isinstance(item, dict)
    ]
    whisker_rows = [item for item in whiskers or [] if isinstance(item, dict)]
    if points:
        pairs_low = [[item.get("x"), item.get("low")] for item in points]
        pairs_high = [[item.get("x"), item.get("high")] for item in points]
    elif whisker_rows:
        pairs_low = [[index, item.get("low")] for index, item in enumerate(whisker_rows)]
        pairs_high = [[index, item.get("high")] for index, item in enumerate(whisker_rows)]
    else:
        return []
    return [
        {
            "band_id": "historical-range",
            "label": "Historical Range",
            "kind": "historical_range",
            "lower_points": _points_from_pairs(pairs_low, labels=labels, scale=scale),
            "upper_points": _points_from_pairs(pairs_high, labels=labels, scale=scale),
        }
    ]


def _data_richness(value: Any) -> int:
    if value in (None, "", [], {}):
        return 0
    if isinstance(value, dict):
        return 1 + sum(_data_richness(item) for item in value.values())
    if isinstance(value, list):
        return len(value) + sum(_data_richness(item) for item in value)
    return 1


def _highlights_from_dom(value: Any, *, series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timestamps = sorted(
        {
            timestamp
            for item in series
            for point in item.get("points") or []
            if isinstance(point, dict)
            if (timestamp := _float(point.get("ts"))) is not None
        }
    )
    domain_start = timestamps[0] if timestamps else None
    domain_end = timestamps[-1] if timestamps else None
    highlights: list[dict[str, Any]] = []
    for index, item in enumerate(value or []):
        if not isinstance(item, dict):
            continue
        start_x = _bounded_ratio(item.get("startX"))
        end_x = _bounded_ratio(item.get("endX"))
        if start_x is None or end_x is None:
            start_x = _domain_ratio(item.get("start"), domain_start, domain_end)
            end_x = _domain_ratio(item.get("end"), domain_start, domain_end)
        if start_x is None or end_x is None or end_x <= start_x:
            continue
        highlights.append(
            {
                "band_id": f"anomaly-{index}",
                "label": _text(item.get("label")) or "Anomaly",
                "kind": "anomaly",
                "start": _text(item.get("start")),
                "end": _text(item.get("end")),
                "start_x": start_x,
                "end_x": end_x,
                "pattern": "diagonal",
            }
        )
    return highlights


def _bounded_ratio(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def _domain_ratio(value: Any, start: float | None, end: float | None) -> float | None:
    number = _float(value)
    if number is None or start is None or end is None or end <= start:
        return None
    return _bounded_ratio((number - start) / (end - start))


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _points_from_pairs(value: Any, *, labels: list[str], scale: float) -> list[dict[str, Any]]:
    pairs = [item for item in value or [] if isinstance(item, list) and len(item) >= 2]
    pairs.sort(key=lambda item: float(item[0] or 0))
    denominator = max(1, len(pairs) - 1)
    return [
        {
            "ts": str(pair[0]),
            "label": labels[index] if index < len(labels) else str(pair[0]),
            "raw_value": float(pair[1]),
            "value": float(pair[1]) * scale,
            "x": index / denominator,
        }
        for index, pair in enumerate(pairs)
        if pair[1] is not None
    ]


def _table_contract(value: dict[str, Any], *, timezone: str) -> dict[str, Any]:
    headers = [item for item in value.get("headers") or [] if isinstance(item, dict)]
    raw_rows = [item for item in value.get("rows") or [] if isinstance(item, dict)]
    period_label = _text(value.get("period")) or ""
    if not headers and value.get("empty") is True:
        return {
            "columns": [],
            "rows": [],
            "empty": True,
            "default_sort_column": None,
            "default_sort_direction": None,
            "period_label": period_label,
            "timezone": timezone,
        }
    if not headers:
        return {}
    columns: list[dict[str, Any]] = []
    for index, header in enumerate(headers):
        label = _text(header.get("label"))
        if not label:
            continue
        key = "name" if index == 0 else f"metric_{index}"
        sample = _table_cell(raw_rows, index)
        data_type = "text" if index == 0 else "number"
        columns.append(
            {
                "key": key,
                "label": label,
                "data_type": data_type,
                "precision": None if data_type == "text" else _display_precision(sample),
                "sortable": True,
                "default_sort": _sort_direction(header) if header.get("active") else None,
            }
        )
    rows: list[dict[str, Any]] = []
    for row_index, raw_row in enumerate(raw_rows):
        cells = [item for item in raw_row.get("cells") or [] if isinstance(item, dict)]
        parsed: dict[str, Any] = {"row_index": row_index}
        for index, column in enumerate(columns):
            cell = cells[index] if index < len(cells) else {}
            main = _text(cell.get("main")) or ""
            parsed[column["key"]] = main if index == 0 else _parse_number(main)
            parsed[f"{column['key']}_formatted"] = main
            delta = _text(cell.get("delta"))
            if delta:
                parsed[f"{column['key']}_delta_formatted"] = delta
                parsed[f"{column['key']}_delta_intent"] = _cell_intent(cell)
        rows.append(parsed)
    active_column = next(
        (
            columns[index]["key"]
            for index, header in enumerate(headers[: len(columns)])
            if header.get("active")
        ),
        None,
    )
    active_header = next((header for header in headers if header.get("active")), None)
    return {
        "columns": columns,
        "rows": rows,
        "empty": False,
        "default_sort_column": active_column,
        "default_sort_direction": _sort_direction(active_header or {}),
        "period_label": period_label,
        "timezone": timezone,
    }


def _chart_type(value: str) -> str | None:
    normalized = value.casefold()
    if "stacked-bar" in normalized:
        return "stacked_bar"
    if "bar" in normalized:
        return "bar"
    if "donut" in normalized:
        return "donut"
    if "line" in normalized:
        return "line"
    return None


def _display_precision(value: str | None) -> int:
    if not value:
        return 0
    numeric = _numeric_token(value)
    if not numeric:
        return 0
    if "." in numeric:
        tail = numeric.rsplit(".", 1)[1]
        if numeric.count(".") == 1 and len(tail) != 3:
            return len(tail)
        return 0
    if "," in numeric and len(numeric.rsplit(",", 1)[1]) != 3:
        return len(numeric.rsplit(",", 1)[1])
    return 0


def _parse_number(value: str | None) -> float | None:
    token = _numeric_token(value or "")
    if not token:
        return None
    if "," in token and "." in token:
        decimal = "." if token.rfind(".") > token.rfind(",") else ","
        grouping = "," if decimal == "." else "."
        token = token.replace(grouping, "").replace(decimal, ".")
    elif "," in token:
        tail = token.rsplit(",", 1)[1]
        token = token.replace(",", "." if len(tail) != 3 else "")
    elif "." in token:
        tail = token.rsplit(".", 1)[1]
        if token.count(".") > 1 or len(tail) == 3:
            token = token.replace(".", "")
    try:
        return float(token)
    except ValueError:
        return None


def _axis_number(value: str) -> float | None:
    parsed = _parse_number(value)
    if parsed is None:
        return None
    normalized = value.strip().casefold()
    if normalized.endswith("k"):
        return parsed * 1_000
    if normalized.endswith("m"):
        return parsed * 1_000_000
    if normalized.endswith("b"):
        return parsed * 1_000_000_000
    return parsed


def _numeric_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\u200e", "")
    match = re.search(r"[-+]?\d[\d.,\s]*", normalized)
    return match.group(0).replace(" ", "") if match else ""


def _trend_direction(path: str) -> int:
    if "V64" in path or "v144" in path:
        return 1
    if "M416 208H32" in path or "M416,208H32" in path:
        return -1
    return 0


def _table_cell(rows: list[dict[str, Any]], index: int) -> str:
    for row in rows:
        cells = [item for item in row.get("cells") or [] if isinstance(item, dict)]
        if index < len(cells):
            value = _text(cells[index].get("main"))
            if value:
                return value
    return ""


def _sort_direction(header: dict[str, Any]) -> str:
    direction = str(header.get("direction") or "").casefold()
    return "asc" if "asc" in direction else "desc"


def _cell_intent(cell: dict[str, Any]) -> str:
    value = str(cell.get("intent") or "").casefold()
    if "good" in value:
        return "positive"
    if "bad" in value:
        return "negative"
    return "neutral"


def _text_list(value: Any) -> list[str]:
    return [text for item in value or [] if (text := _text(item))]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
