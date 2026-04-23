from __future__ import annotations

import math
from pathlib import Path


def clean_number(value: str | float | int | None, digits: int) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def title_from_path(path: Path) -> str:
    words = path.stem.replace("-", " ").replace("_", " ").split()
    return " ".join(word.capitalize() if not word.isdigit() else word for word in words)


def average_or_none(total: float, count: int, digits: int) -> float | None:
    if count <= 0:
        return None
    return round(total / count, digits)
