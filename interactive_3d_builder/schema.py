from __future__ import annotations

from typing import NamedTuple


class NumericSpec(NamedTuple):
    output_name: str
    source_name: str
    digits: int


class SummaryMetric(NamedTuple):
    name: str
    digits: int


NUMERIC_SPECS = (
    NumericSpec("spx_strike", "spx_strike", 4),
    NumericSpec("future_strike", "future_strike", 4),
    NumericSpec("mbo_pull", "MBO_pulling_stacking", 4),
    NumericSpec("current_es_price", "current_es_price", 4),
    NumericSpec("call_delta", "call_delta", 6),
    NumericSpec("put_delta", "put_delta", 6),
    NumericSpec("call_gamma", "call_gamma", 8),
    NumericSpec("call_vega", "call_vega", 6),
    NumericSpec("call_theta", "call_theta", 6),
)

SUMMARY_METRICS = (
    SummaryMetric("current_es_price", 2),
    SummaryMetric("mbo_pull", 4),
    SummaryMetric("spx_strike", 2),
    SummaryMetric("call_delta", 6),
    SummaryMetric("call_theta", 6),
)
