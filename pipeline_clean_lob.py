"""Streaming parallel pipeline.

Downloads loaded_lob_*.csv.gz URLs, double-gunzips the nested JSON payload,
aggregates each file into a small set of representative rows (per-minute
summary + nearest-the-money samples per side), and appends them to one
CSV that the interactive_3d_builder reads directly.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import re
import sys
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

try:
    import orjson as _json

    def _loads(data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        return _json.loads(data)
except ImportError:
    import json as _json

    def _loads(data):
        if isinstance(data, (bytes, bytearray)):
            data = data.decode("utf-8")
        return _json.loads(data)

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable=None, total=None, **_kwargs):
        class _Dummy:
            def __init__(self, it): self.it = it
            def __iter__(self): return iter(self.it) if self.it is not None else iter(())
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def update(self, _n=1): pass
            def set_postfix(self, **_): pass
        return _Dummy(iterable)


NUMERIC_COLUMNS = [
    "future_strike", "MBO_pulling_stacking", "current_es_price", "spx_strike",
    "t", "spx_price", "call_charm", "call_delta", "call_gamma", "call_rho",
    "call_theta", "call_vanna", "call_vega", "call_vomma", "put_charm",
    "put_delta", "put_gamma", "put_rho", "put_theta", "put_vanna", "put_vega",
    "put_vomma",
]
OUTPUT_COLUMNS = ["timestamp", "Side", *NUMERIC_COLUMNS]


def extract_stem(url: str) -> str:
    match = re.search(r"loaded_lob_(\d{8}__\d{8}_\d{4})\.csv\.gz", url)
    return match.group(1) if match else url.rsplit("/", 1)[-1]


def fetch_records(url: str, timeout: int = 90, retries: int = 3) -> list[dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_exc: Exception | None = None
    for _attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            once = gzip.decompress(raw)
            twice = gzip.decompress(once)
            inner = _loads(twice)
            return _loads(inner)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def aggregate_records(records: list[dict[str, Any]], atm_samples: int) -> list[dict[str, Any]]:
    import pandas as pd

    if not records:
        return []

    df = pd.DataFrame.from_records(records)
    if "Side" not in df.columns:
        return []

    for column in NUMERIC_COLUMNS:
        if column not in df.columns:
            df[column] = None
        else:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    rows: list[dict[str, Any]] = []
    for side, group in df.groupby("Side", sort=False):
        if group.empty:
            continue

        summary_values = group[NUMERIC_COLUMNS].mean(numeric_only=True).round(6)
        summary: dict[str, Any] = {
            "timestamp": group["timestamp"].iloc[0],
            "Side": side,
        }
        for column in NUMERIC_COLUMNS:
            value = summary_values.get(column)
            summary[column] = None if pd.isna(value) else float(value)
        rows.append(summary)

        if atm_samples <= 0:
            continue

        es_series = group["current_es_price"].dropna()
        if es_series.empty:
            continue
        es_strike = float(es_series.iloc[0]) / 100.0

        strikes = group["spx_strike"]
        unique_mask = ~strikes.duplicated() & strikes.notna()
        unique_group = group.loc[unique_mask].copy()
        unique_group["_dist"] = (unique_group["spx_strike"] - es_strike).abs()
        atm_group = unique_group.nsmallest(atm_samples, "_dist")

        for record in atm_group.to_dict("records"):
            row: dict[str, Any] = {
                "timestamp": record.get("timestamp"),
                "Side": side,
            }
            for column in NUMERIC_COLUMNS:
                value = record.get(column)
                row[column] = None if value is None or (isinstance(value, float) and value != value) else float(value)
            rows.append(row)

    return rows


def process_url(url: str, atm_samples: int) -> tuple[bool, str, list[dict[str, Any]] | str]:
    try:
        records = fetch_records(url)
        rows = aggregate_records(records, atm_samples=atm_samples)
        return True, url, rows
    except Exception as exc:  # noqa: BLE001
        return False, url, f"{type(exc).__name__}: {exc}"


def read_urls(path: Path) -> list[str]:
    urls: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("http"):
                urls.append(line)
    return urls


def filter_urls_by_date(urls: list[str], dates: list[str]) -> list[str]:
    if not dates:
        return urls
    normalized = {date.replace("-", "/") for date in dates}
    return [u for u in urls if any(f"/{d}/" in u for d in normalized)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("links_file", type=Path, help="Text file with one URL per line")
    parser.add_argument("--output", type=Path, default=Path("aggregated_lob.csv"),
                        help="Output CSV path (default: aggregated_lob.csv)")
    parser.add_argument("--workers", type=int, default=8,
                        help="Parallel download/parse worker processes (default: 8)")
    parser.add_argument("--atm-samples", type=int, default=20,
                        help="Nearest-the-money strikes to keep per side per minute (default: 20)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N URLs")
    parser.add_argument("--date", action="append", default=[],
                        help="Keep only URLs containing this YYYY/MM/DD (repeatable)")
    parser.add_argument("--log-file", type=Path, default=Path("pipeline_log.txt"))
    args = parser.parse_args()

    urls = read_urls(args.links_file)
    urls = filter_urls_by_date(urls, args.date)
    if args.limit is not None:
        urls = urls[: args.limit]

    if not urls:
        print("No URLs found.", file=sys.stderr)
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    successes = 0
    failures = 0
    rows_written = 0

    with args.output.open("w", newline="", encoding="utf-8") as fout, \
         args.log_file.open("w", encoding="utf-8") as flog:
        writer = csv.DictWriter(fout, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(process_url, url, args.atm_samples) for url in urls]
            with tqdm(total=len(futures), unit="file", desc="aggregating") as bar:
                for future in as_completed(futures):
                    ok, url, payload = future.result()
                    stem = extract_stem(url)
                    if ok:
                        assert isinstance(payload, list)
                        for row in payload:
                            writer.writerow(row)
                        rows_written += len(payload)
                        successes += 1
                        flog.write(f"OK   {stem} ({len(payload)} rows)\n")
                    else:
                        failures += 1
                        flog.write(f"FAIL {stem}: {payload}\n")
                    flog.flush()
                    bar.update(1)
                    bar.set_postfix(ok=successes, fail=failures, rows=rows_written)

    print(f"\nProcessed {len(urls)} URLs: {successes} ok, {failures} failed")
    print(f"Rows written: {rows_written:,}")
    print(f"Output:       {args.output.resolve()}")
    print(f"Log:          {args.log_file.resolve()}")


if __name__ == "__main__":
    main()
