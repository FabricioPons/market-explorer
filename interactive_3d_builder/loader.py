from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DEFAULT_RENDER_POINTS
from .sampling import stratified_sample_indices
from .schema import NUMERIC_SPECS, SUMMARY_METRICS
from .transforms import average_or_none, clean_number, title_from_path


RowColumns = dict[str, list[Any]]


def _cell(row: list[str], index: int | None) -> str | None:
    if index is None or index >= len(row):
        return None
    return row[index]


def _column_index(header_lookup: dict[str, int], name: str) -> int | None:
    return header_lookup.get(name)


def _seconds_from_datetime(value: datetime) -> float:
    if value.tzinfo is None:
        epoch = datetime(1970, 1, 1)
        return (value - epoch).total_seconds()

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (value.astimezone(timezone.utc) - epoch).total_seconds()


def _new_dataset_entry(path: Path) -> dict[str, Any]:
    return {
        "source_name": path.name,
        "source_path": str(path),
        "display_name": title_from_path(path),
        "rows_source": 0,
        "timestamp_start": None,
        "timestamp_end": None,
        "side_counts": {},
        "metric_sums": {metric.name: 0.0 for metric in SUMMARY_METRICS},
        "metric_counts": {metric.name: 0 for metric in SUMMARY_METRICS},
    }


def _empty_raw_columns() -> RowColumns:
    columns: RowColumns = {
        "dataset": [],
        "side": [],
        "timestamp": [],
        "timestamp_seconds": [],
    }
    for spec in NUMERIC_SPECS:
        columns[spec.output_name] = []
    return columns


def _append_selected_columns(
    raw_columns: RowColumns,
    selected_indices: list[int],
    min_timestamp_seconds: float,
    dataset_count: int,
) -> tuple[RowColumns, list[int]]:
    data_columns: RowColumns = {
        "dataset": [],
        "side": [],
        "timestamp": [],
        "elapsed_sec": [],
    }
    for spec in NUMERIC_SPECS:
        data_columns[spec.output_name] = []

    dataset_counts_embedded = [0 for _ in range(dataset_count)]
    for row_index in selected_indices:
        dataset_index = raw_columns["dataset"][row_index]
        data_columns["dataset"].append(dataset_index)
        data_columns["side"].append(raw_columns["side"][row_index])
        data_columns["timestamp"].append(raw_columns["timestamp"][row_index])
        data_columns["elapsed_sec"].append(
            round(raw_columns["timestamp_seconds"][row_index] - min_timestamp_seconds, 6)
        )
        for spec in NUMERIC_SPECS:
            data_columns[spec.output_name].append(raw_columns[spec.output_name][row_index])
        dataset_counts_embedded[dataset_index] += 1

    return data_columns, dataset_counts_embedded


def _all_columns(
    raw_columns: RowColumns,
    min_timestamp_seconds: float,
    dataset_stats: list[dict[str, Any]],
) -> tuple[RowColumns, list[int]]:
    data_columns: RowColumns = {
        "dataset": raw_columns["dataset"],
        "side": raw_columns["side"],
        "timestamp": raw_columns["timestamp"],
        "elapsed_sec": [
            round(timestamp_seconds - min_timestamp_seconds, 6)
            for timestamp_seconds in raw_columns["timestamp_seconds"]
        ],
    }
    for spec in NUMERIC_SPECS:
        data_columns[spec.output_name] = raw_columns[spec.output_name]

    dataset_counts_embedded = [int(entry["rows_source"]) for entry in dataset_stats]
    return data_columns, dataset_counts_embedded


def _build_meta(
    raw_count: int,
    embedded_count: int,
    min_timestamp: datetime,
    max_timestamp: datetime,
    dataset_stats: list[dict[str, Any]],
    dataset_counts_embedded: list[int],
    side_labels: list[str],
) -> dict[str, Any]:
    dataset_labels: list[str] = []
    dataset_summaries: list[dict[str, Any]] = []
    overall_side_counts = {side_label: 0 for side_label in side_labels}

    for dataset_index, dataset_entry in enumerate(dataset_stats):
        label = f"Session {dataset_index + 1} - {dataset_entry['display_name']}"
        dataset_labels.append(label)

        side_counts = {
            side_label: int(dataset_entry["side_counts"].get(side_label, 0))
            for side_label in side_labels
        }
        for side_label, count in side_counts.items():
            overall_side_counts[side_label] += count

        start_ts = dataset_entry["timestamp_start"]
        end_ts = dataset_entry["timestamp_end"]
        summary = {
            "label": label,
            "source_name": dataset_entry["source_name"],
            "source_path": dataset_entry["source_path"],
            "rows_source": int(dataset_entry["rows_source"]),
            "rows_embedded": int(dataset_counts_embedded[dataset_index]),
            "timestamp_start": start_ts.isoformat() if start_ts is not None else "",
            "timestamp_end": end_ts.isoformat() if end_ts is not None else "",
            "duration_seconds": round((end_ts - start_ts).total_seconds(), 6)
            if start_ts is not None and end_ts is not None
            else 0.0,
            "side_counts": side_counts,
        }

        for metric in SUMMARY_METRICS:
            summary[f"avg_{metric.name}"] = average_or_none(
                dataset_entry["metric_sums"][metric.name],
                dataset_entry["metric_counts"][metric.name],
                metric.digits,
            )

        dataset_summaries.append(summary)

    return {
        "rows_total": raw_count,
        "rows_embedded": embedded_count,
        "time_span_seconds": round((max_timestamp - min_timestamp).total_seconds(), 6),
        "timestamp_start": min_timestamp.isoformat(),
        "timestamp_end": max_timestamp.isoformat(),
        "dataset_labels": dataset_labels,
        "dataset_counts_source": [summary["rows_source"] for summary in dataset_summaries],
        "dataset_counts_embedded": dataset_counts_embedded,
        "dataset_summaries": dataset_summaries,
        "overall_side_counts": overall_side_counts,
        "side_labels": side_labels,
        "default_render_points": min(DEFAULT_RENDER_POINTS, embedded_count),
        "source_files": [summary["source_path"] for summary in dataset_summaries],
    }


def load_sources(input_paths: list[Path], max_points: int) -> tuple[RowColumns, dict[str, Any]]:
    side_labels: list[str] = []
    side_lookup: dict[str, int] = {}
    dataset_stats: list[dict[str, Any]] = []
    raw_columns = _empty_raw_columns()

    min_timestamp: datetime | None = None
    max_timestamp: datetime | None = None
    min_timestamp_seconds: float | None = None

    summary_metric_names = {metric.name for metric in SUMMARY_METRICS}

    for input_path in input_paths:
        resolved = input_path.expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Input CSV not found: {resolved}")

        dataset_stats.append(_new_dataset_entry(resolved))
        dataset_index = len(dataset_stats) - 1
        dataset_entry = dataset_stats[dataset_index]

        with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                continue

            header_lookup = {name.strip(): index for index, name in enumerate(header)}
            timestamp_index = _column_index(header_lookup, "timestamp")
            side_index = _column_index(header_lookup, "Side")
            numeric_indices = [
                _column_index(header_lookup, spec.source_name)
                for spec in NUMERIC_SPECS
            ]

            for row in reader:
                timestamp_text = (_cell(row, timestamp_index) or "").strip()
                side_label = (_cell(row, side_index) or "").strip()
                if not timestamp_text or not side_label:
                    continue

                try:
                    timestamp_value = datetime.fromisoformat(timestamp_text)
                except ValueError:
                    continue

                if side_label not in side_lookup:
                    side_lookup[side_label] = len(side_labels)
                    side_labels.append(side_label)
                side_id = side_lookup[side_label]

                raw_columns["dataset"].append(dataset_index)
                raw_columns["side"].append(side_id)
                raw_columns["timestamp"].append(timestamp_value.isoformat())
                timestamp_seconds = _seconds_from_datetime(timestamp_value)
                raw_columns["timestamp_seconds"].append(timestamp_seconds)

                dataset_entry["rows_source"] += 1
                side_counts = dataset_entry["side_counts"]
                side_counts[side_label] = side_counts.get(side_label, 0) + 1

                if dataset_entry["timestamp_start"] is None or timestamp_value < dataset_entry["timestamp_start"]:
                    dataset_entry["timestamp_start"] = timestamp_value
                if dataset_entry["timestamp_end"] is None or timestamp_value > dataset_entry["timestamp_end"]:
                    dataset_entry["timestamp_end"] = timestamp_value

                for spec, column_index in zip(NUMERIC_SPECS, numeric_indices):
                    value = clean_number(_cell(row, column_index), spec.digits)
                    raw_columns[spec.output_name].append(value)
                    if spec.output_name in summary_metric_names and value is not None:
                        dataset_entry["metric_sums"][spec.output_name] += value
                        dataset_entry["metric_counts"][spec.output_name] += 1

                if min_timestamp is None or timestamp_value < min_timestamp:
                    min_timestamp = timestamp_value
                    min_timestamp_seconds = timestamp_seconds
                if max_timestamp is None or timestamp_value > max_timestamp:
                    max_timestamp = timestamp_value

    if min_timestamp is None or max_timestamp is None or min_timestamp_seconds is None:
        raise ValueError("No rows with both timestamp and Side were found in the provided CSV files.")

    raw_count = len(raw_columns["dataset"])
    if max_points <= 0 or raw_count <= max_points:
        data_columns, dataset_counts_embedded = _all_columns(
            raw_columns,
            min_timestamp_seconds,
            dataset_stats,
        )
    else:
        selected_indices = stratified_sample_indices(
            raw_columns["dataset"],
            raw_columns["side"],
            max_points,
        )
        data_columns, dataset_counts_embedded = _append_selected_columns(
            raw_columns,
            selected_indices,
            min_timestamp_seconds,
            len(dataset_stats),
        )

    meta = _build_meta(
        raw_count=raw_count,
        embedded_count=len(data_columns["timestamp"]),
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
        dataset_stats=dataset_stats,
        dataset_counts_embedded=dataset_counts_embedded,
        side_labels=side_labels,
    )
    return data_columns, meta
