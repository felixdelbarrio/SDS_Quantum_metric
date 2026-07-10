from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.analytics.normalizer import parse_json_object
from backend.app.quantum_dashboard.widget_roles import WidgetRoleDescriptor
from backend.app.storage.parquet_store import hash_json

MINIMUM_AUTOMATIC_CONFIDENCE = 0.9


class CorrelationCandidate(BaseModel):
    widget_id: str
    card_id: str | None = None
    request_id: str | None = None
    request_hash: str
    response_hash: str
    tab_id: str | None = None
    section_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class CorrelationResult(BaseModel):
    status: str
    candidate: CorrelationCandidate | None = None
    candidates: list[CorrelationCandidate] = Field(default_factory=list)
    error_code: str | None = None


def correlate_call_to_widget(
    call: dict[str, Any],
    descriptors: list[WidgetRoleDescriptor],
) -> CorrelationResult:
    request = parse_json_object(call.get("request_json"))
    response = parse_json_object(call.get("response_json"))
    metadata_value = request.get("metadata")
    metadata: dict[str, Any] = metadata_value if isinstance(metadata_value, dict) else {}
    call_widget_id = _text(call.get("widget_id") or metadata.get("widgetId"))
    call_card_id = _text(call.get("card_id") or metadata.get("cardId"))
    call_tab_id = _text(call.get("tab_id") or metadata.get("tabId"))
    call_section_id = _text(call.get("section_id") or metadata.get("sectionId"))
    request_id = _text(call.get("request_id") or request.get("id"))
    request_hash = _text(call.get("query_hash")) or hash_json(request)
    response_hash = _text(call.get("response_hash")) or hash_json(response)

    candidates: list[CorrelationCandidate] = []
    for descriptor in descriptors:
        if not descriptor.enabled or not descriptor.supported:
            continue
        evidence: list[str] = []
        confidence = 0.0
        if call_widget_id and descriptor.widget_id == call_widget_id:
            confidence += 0.95
            evidence.append("exact_widget_id")
        if call_card_id and descriptor.card_id == call_card_id:
            confidence += 0.9
            evidence.append("exact_card_id")
        if call_tab_id and descriptor.tab_id == call_tab_id:
            confidence += 0.05
            evidence.append("exact_tab_id")
        if call_section_id and descriptor.section_id == call_section_id:
            confidence += 0.05
            evidence.append("exact_section_id")
        if not evidence:
            continue
        candidates.append(
            CorrelationCandidate(
                widget_id=descriptor.widget_id or descriptor.role,
                card_id=descriptor.card_id,
                request_id=request_id,
                request_hash=request_hash,
                response_hash=response_hash,
                tab_id=descriptor.tab_id,
                section_id=descriptor.section_id,
                confidence=min(confidence, 1.0),
                evidence=evidence,
            )
        )

    accepted = [item for item in candidates if item.confidence >= MINIMUM_AUTOMATIC_CONFIDENCE]
    accepted.sort(key=lambda item: item.confidence, reverse=True)
    if len(accepted) == 1:
        return CorrelationResult(status="resolved", candidate=accepted[0], candidates=candidates)
    if len(accepted) > 1:
        return CorrelationResult(
            status="ambiguous",
            candidates=candidates,
            error_code="failed_ambiguous_widget_correlation",
        )
    return CorrelationResult(
        status="missing",
        candidates=candidates,
        error_code="failed_missing_widget_correlation",
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
