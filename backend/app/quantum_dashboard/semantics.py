from __future__ import annotations

from typing import Literal

SemanticIntent = Literal["good", "bad", "neutral"]
SemanticState = Literal["positive", "negative", "neutral"]

METRIC_SEMANTICS = {
    "page_views": "neutral",
    "sessions": "neutral",
    "converted_sessions": "higher_is_good",
    "conversions": "higher_is_good",
    "avg_session_duration": "neutral",
    "error_sessions": "lower_is_good",
    "error_session_percent": "lower_is_good",
}


def semantic_state(metric: str, delta_percent: float | None) -> SemanticState:
    if delta_percent is None or delta_percent == 0:
        return "neutral"
    rule = METRIC_SEMANTICS.get(metric, "neutral")
    if rule == "higher_is_good":
        return "positive" if delta_percent > 0 else "negative"
    if rule == "lower_is_good":
        return "positive" if delta_percent < 0 else "negative"
    return "neutral"


def semantic_intent(metric: str, delta_percent: float | None) -> SemanticIntent:
    state = semantic_state(metric, delta_percent)
    if state == "positive":
        return "good"
    if state == "negative":
        return "bad"
    return "neutral"
