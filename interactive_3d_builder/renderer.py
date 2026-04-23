from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import TEMPLATE_FILE


def template_path() -> Path:
    return Path(__file__).resolve().parent.parent / TEMPLATE_FILE


def build_html(data_columns: dict[str, list[Any]], meta: dict[str, Any]) -> str:
    template = template_path().read_text(encoding="utf-8")
    html = template.replace("__DATA_JSON__", json.dumps(data_columns, separators=(",", ":")))
    return html.replace("__META_JSON__", json.dumps(meta, separators=(",", ":")))
