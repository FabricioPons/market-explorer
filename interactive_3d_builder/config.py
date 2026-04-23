from __future__ import annotations

from pathlib import Path

DEFAULT_OUTPUT = Path("interactive_3d_visualization.html")
DEFAULT_MAX_POINTS = 0
DEFAULT_RENDER_POINTS = 30_000
DEFAULT_INPUT_CANDIDATES = (
    Path("aggregated_lob.csv"),
)
TEMPLATE_FILE = "interactive_3d_template.html"
