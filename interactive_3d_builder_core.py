"""Compatibility wrapper for the modular interactive_3d_builder package."""

from interactive_3d_builder.cli import default_input_paths, main, parse_args
from interactive_3d_builder.config import DEFAULT_MAX_POINTS, DEFAULT_OUTPUT, DEFAULT_RENDER_POINTS
from interactive_3d_builder.loader import load_sources
from interactive_3d_builder.renderer import build_html
from interactive_3d_builder.sampling import evenly_spaced_subset, stratified_sample_indices
from interactive_3d_builder.transforms import average_or_none, clean_number, title_from_path

__all__ = [
    "DEFAULT_MAX_POINTS",
    "DEFAULT_OUTPUT",
    "DEFAULT_RENDER_POINTS",
    "average_or_none",
    "build_html",
    "clean_number",
    "default_input_paths",
    "evenly_spaced_subset",
    "load_sources",
    "main",
    "parse_args",
    "stratified_sample_indices",
    "title_from_path",
]
