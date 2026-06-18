from __future__ import annotations

from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.quantum_dashboard.builder import (
    DATASET_SUMMARY_WIDGETS,
    DATASET_VISUAL_CONTRACTS,
    DATASET_WEB_SNAPSHOTS,
)
from backend.app.quantum_dashboard.evidence import build_evidence_report
from backend.app.storage.parquet_store import ParquetStore


def test_evidence_report_identifies_match(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _seed_widget(store, local_value=100, web_value=100)

    report = build_evidence_report(store, "MX", roles=["summary.page_views"])

    assert report[0].status == "matched"
    assert report[0].first_divergence is None
    assert report[0].raw_query_hash == "query-hash"


def test_evidence_report_identifies_aggregation_divergence(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _seed_widget(store, local_value=90, web_value=100)

    report = build_evidence_report(store, "MX", roles=["summary.page_views"])

    assert report[0].status == "diverged_aggregation"
    assert report[0].first_divergence == "Derived -> Local API"


def _seed_widget(store: ParquetStore, *, local_value: int, web_value: int) -> None:
    store.write_country_dataset(
        "MX",
        DATASET_VISUAL_CONTRACTS,
        [
            {
                "visual_role": "summary.page_views",
                "request_hash": "query-hash",
                "response_hash": "response-hash",
            }
        ],
    )
    store.write_country_dataset(
        "MX",
        DATASET_WEB_SNAPSHOTS,
        [{"card_role": "summary.page_views", "visible_value": web_value}],
    )
    store.write_country_dataset(
        "MX",
        DATASET_SUMMARY_WIDGETS,
        [{"card_role": "summary.page_views", "value": local_value}],
    )
