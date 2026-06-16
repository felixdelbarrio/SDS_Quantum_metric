from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.config.settings import Settings, get_settings
from backend.app.quantum_dashboard.builder import (
    DATASET_ERRORS_APP_NAME,
    DATASET_ERRORS_TOP_ERRORS,
    DATASET_ERRORS_WIDGETS,
    DATASET_REGRESSION_DISCREPANCIES,
    DATASET_REGRESSION_RESULTS,
    DATASET_SUMMARY_TABLE,
    DATASET_SUMMARY_WIDGETS,
    DATASET_VISUAL_CONTRACTS,
    DATASET_WEB_SNAPSHOTS,
)
from backend.app.quantum_dashboard.catalog import MANDATORY_CARDS, ROLE_SPECS
from backend.app.quantum_dashboard.models import (
    DashboardTab,
    RegressionCardResult,
    RegressionReport,
    RegressionStatus,
    RegressionVerdict,
    VisualRole,
)
from backend.app.storage.parquet_store import ParquetStore


def run_regression(
    store: ParquetStore,
    country: str,
    *,
    ingestion_id: str | None = None,
    tolerance_percent: float | None = None,
) -> RegressionReport:
    tolerance = (
        store.settings.quantum_regression_tolerance_percent
        if tolerance_percent is None
        else tolerance_percent
    )
    contracts = store.read_country_dataset(country, DATASET_VISUAL_CONTRACTS)
    snapshots = store.read_country_dataset(country, DATASET_WEB_SNAPSHOTS)
    contract_roles = {str(row.get("visual_role")) for row in contracts}
    snapshot_by_role = {str(row.get("card_role")): row for row in snapshots}
    cards: list[RegressionCardResult] = []

    for spec in MANDATORY_CARDS:
        if spec.role not in contract_roles:
            cards.append(
                _card_result(
                    spec.tab,
                    spec.role,
                    spec.title,
                    "failed_missing_card",
                    details="Mandatory card has no visual contract.",
                )
            )
            continue
        local = _local_payload(store, country, spec.role)
        if not local:
            cards.append(
                _card_result(
                    spec.tab,
                    spec.role,
                    spec.title,
                    "failed_missing_api_response",
                    details="Mandatory card has no derived dataset.",
                )
            )
            continue
        snapshot = snapshot_by_role.get(spec.role)
        if not snapshot:
            cards.append(
                _card_result(
                    spec.tab,
                    spec.role,
                    spec.title,
                    "failed_missing_card",
                    details="Mandatory card has no web snapshot.",
                )
            )
            continue
        cards.append(_compare_card(spec.role, snapshot, local, tolerance))

    status = _overall_status(cards)
    verdict: RegressionVerdict = (
        "PASSED"
        if status == "passed"
        else "PASSED_WITH_TOLERANCE"
        if status == "passed_with_tolerance"
        else "FAILED"
    )
    generated_at = datetime.now(UTC).isoformat()
    first_contract = contracts[0] if contracts else {}
    report = RegressionReport(
        ingestion_id=ingestion_id,
        country=country,
        dashboard_id=_text(first_contract.get("dashboard_id")),
        team_id=_text(first_contract.get("team_id")),
        tabs=["summary", "errors"],
        cards=cards,
        verdict=verdict,
        status=status,
        tolerance_percent=tolerance,
        generated_at=generated_at,
    )
    _persist_report(store, report)
    _write_docs_report(store.settings, report)
    return report


def _compare_card(
    role: VisualRole,
    snapshot: dict[str, Any],
    local: dict[str, Any],
    tolerance: float,
) -> RegressionCardResult:
    spec = ROLE_SPECS[role]
    if spec.card_type == "TABLE":
        web_rows = _list(snapshot.get("visible_table_rows"))
        local_rows = _list(local.get("rows"))
        if len(web_rows[:10]) != len(local_rows[:10]):
            return _card_result(
                spec.tab,
                role,
                spec.title,
                "failed_table_mismatch",
                web_value=len(web_rows),
                local_value=len(local_rows),
                details="Visible row counts differ.",
            )
        return _card_result(
            spec.tab,
            role,
            spec.title,
            "passed",
            web_value=len(web_rows),
            local_value=len(local_rows),
        )

    web_value = _number(snapshot.get("visible_value"))
    local_value = _number(local.get("value"))
    if local_value is None:
        local_value = _number(local.get("total"))
    if web_value is None and local_value is None:
        web_value = len(_list(snapshot.get("visible_series")))
        local_value = len(_list(local.get("timeseries") or local.get("series")))
    if web_value is None or local_value is None:
        return _card_result(
            spec.tab,
            role,
            spec.title,
            "failed_parse_error",
            web_value=snapshot.get("visible_value"),
            local_value=local.get("value"),
            details="Could not compare numeric or chart values.",
        )
    difference = round(float(local_value) - float(web_value), 6)
    allowed = abs(float(web_value)) * (tolerance / 100)
    if difference == 0:
        status: RegressionStatus = "passed"
    elif abs(difference) <= allowed:
        status = "passed_with_tolerance"
    else:
        status = "failed_value_mismatch"
    return _card_result(
        spec.tab,
        role,
        spec.title,
        status,
        web_value=web_value,
        local_value=local_value,
        difference=difference,
    )


def _local_payload(store: ParquetStore, country: str, role: VisualRole) -> dict[str, Any] | None:
    if role.startswith("summary.") and role != "summary.detail_by_app_name_os":
        rows = store.read_country_dataset(country, DATASET_SUMMARY_WIDGETS)
        return _first_role(rows, role)
    if role == "summary.detail_by_app_name_os":
        rows = store.read_country_dataset(country, DATASET_SUMMARY_TABLE)
        return {"rows": [row for row in rows if row.get("card_role") == role]}
    if role in {
        "errors.error_sessions_percentage_evolution",
        "errors.error_sessions_by_app_name_comparison",
    }:
        rows = store.read_country_dataset(country, DATASET_ERRORS_WIDGETS)
        return _first_role(rows, role)
    if role == "errors.top_errors_by_error_name":
        rows = store.read_country_dataset(country, DATASET_ERRORS_TOP_ERRORS)
        return {"rows": [row for row in rows if row.get("card_role") == role]}
    if role == "errors.error_session_percentage_by_app_name":
        rows = store.read_country_dataset(country, DATASET_ERRORS_APP_NAME)
        return {"rows": [row for row in rows if row.get("card_role") == role]}
    return None


def _first_role(rows: list[dict[str, Any]], role: VisualRole) -> dict[str, Any] | None:
    return next((row for row in rows if row.get("card_role") == role), None)


def _overall_status(cards: list[RegressionCardResult]) -> RegressionStatus:
    statuses = {card.status for card in cards}
    failures = [status for status in statuses if not status.startswith("passed")]
    if failures:
        return failures[0]
    if "passed_with_tolerance" in statuses:
        return "passed_with_tolerance"
    return "passed"


def _persist_report(store: ParquetStore, report: RegressionReport) -> None:
    rows = []
    for card in report.cards:
        rows.append(
            {
                **card.model_dump(mode="json"),
                "country": report.country,
                "ingestion_id": report.ingestion_id,
                "generated_at": report.generated_at,
                "verdict": report.verdict,
            }
        )
    store.write_country_dataset(
        report.country,
        DATASET_REGRESSION_RESULTS,
        rows,
        file_name="web_vs_local_results.parquet",
    )
    discrepancies = [row for row in rows if not str(row["status"]).startswith("passed")]
    store.write_country_dataset(
        report.country,
        DATASET_REGRESSION_DISCREPANCIES,
        discrepancies,
        file_name="discrepancies.parquet",
    )


def _write_docs_report(settings: Settings, report: RegressionReport) -> None:
    docs_dir = Path("docs/regression")
    docs_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = docs_dir / "latest-web-vs-local.md"
    json_path = docs_dir / "latest-web-vs-local.json"
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    _ = settings


def _markdown(report: RegressionReport) -> str:
    rows = [
        "| Tab | Card | Web value | Local value | Status | Difference |",
        "| --- | --- | ---: | ---: | --- | ---: |",
    ]
    for card in report.cards:
        rows.append(
            f"| {card.tab} | {card.card_title} | {_format_cell(card.web_value)} | "
            f"{_format_cell(card.local_value)} | {card.status} | "
            f"{_format_cell(card.difference)} |"
        )
    discrepancies = [
        f"- {card.card_title}: {card.details or card.status}"
        for card in report.cards
        if not card.status.startswith("passed")
    ]
    if not discrepancies:
        discrepancies = ["- None"]
    return "\n".join(
        [
            "# Quantum Web vs Local Regression",
            "",
            "## Summary",
            "",
            f"- Final verdict: {report.verdict}",
            f"- Regression status: {report.status}",
            f"- Country: {report.country}",
            f"- Ingestion ID: {report.ingestion_id or '-'}",
            f"- Generated at: {report.generated_at}",
            f"- Tolerance: {report.tolerance_percent}%",
            "",
            "## Environment",
            "",
            "- Source: local Parquet visual contracts and web snapshots",
            "- Dashboard: general",
            "",
            "## Dashboard Resolved",
            "",
            f"- Dashboard ID: {report.dashboard_id or '-'}",
            f"- Team ID: {report.team_id or '-'}",
            "",
            "## Captured APIs",
            "",
            "- See data/parquet/country=*/raw_api_calls",
            "",
            "## Mandatory Cards",
            "",
            *rows,
            "",
            "## Widget Comparison",
            "",
            "Widget values are compared against the captured web snapshot values.",
            "",
            "## Table Comparison",
            "",
            "Tables compare visible row counts and first visible rows when snapshots include rows.",
            "",
            "## Chart Comparison",
            "",
            "Charts compare totals, point counts, and visible values where available.",
            "",
            "## Discrepancies",
            "",
            *discrepancies,
            "",
            "## Final Verdict",
            "",
            report.verdict,
            "",
        ]
    )


def _card_result(
    tab: DashboardTab,
    role: VisualRole,
    title: str,
    status: RegressionStatus,
    *,
    web_value: float | str | None = None,
    local_value: float | str | None = None,
    difference: float | None = None,
    details: str | None = None,
) -> RegressionCardResult:
    return RegressionCardResult(
        tab=tab,
        card_role=role,
        card_title=title,
        web_value=web_value,
        local_value=local_value,
        status=status,
        difference=difference,
        details=details,
    )


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return float(value.replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_cell(value: object) -> str:
    return "-" if value is None else str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", default="MX")
    parser.add_argument("--dashboard", default="general")
    args = parser.parse_args()
    settings = get_settings()
    report = run_regression(ParquetStore(settings), str(args.country))
    print(f"{args.dashboard}: {report.verdict}")


if __name__ == "__main__":
    main()
