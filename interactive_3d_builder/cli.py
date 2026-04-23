from __future__ import annotations

import argparse
from pathlib import Path

from .config import DEFAULT_INPUT_CANDIDATES, DEFAULT_MAX_POINTS, DEFAULT_OUTPUT
from .loader import load_sources
from .renderer import build_html


def default_input_paths() -> list[Path]:
    existing = [path for path in DEFAULT_INPUT_CANDIDATES if path.exists()]
    return existing or [DEFAULT_INPUT_CANDIDATES[0]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a large-format interactive 3D HTML visualization from one or more CSV files."
    )
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=default_input_paths(),
        help="One or more input CSV paths. Defaults to fixed_output.csv through fixed_output_4.csv when present.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML path.")
    parser.add_argument(
        "--max-points",
        type=int,
        default=DEFAULT_MAX_POINTS,
        help="Max rows embedded in the HTML. Use 0 for all rows. Default: 0.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_columns, meta = load_sources(args.input, args.max_points)
    html = build_html(data_columns, meta)
    args.output.write_text(html, encoding="utf-8")

    sources = ", ".join(str(path.expanduser()) for path in args.input)
    print(f"Saved interactive 3D HTML to: {args.output.resolve()}")
    print(f"Loaded {meta['rows_total']:,} rows from {len(meta['dataset_labels'])} dataset(s).")
    print(f"Embedded {meta['rows_embedded']:,} rows from: {sources}")
