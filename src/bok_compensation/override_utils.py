from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Optional


def normalize_date_value(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if all(hasattr(value, attr) for attr in ("year", "month", "day")):
        try:
            return date(int(value.year), int(value.month), int(value.day))
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if "T" in text:
                return datetime.fromisoformat(text).date()
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def resolve_effective_date(question: str, default: Optional[date] = None) -> date:
    default_date = default or date.today()

    full_date_patterns = [
        r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})",
        r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일",
    ]
    for pattern in full_date_patterns:
        match = re.search(pattern, question)
        if match:
            year, month, day = (int(part) for part in match.groups())
            return date(year, month, day)

    year_match = re.search(r"(20\d{2})\s*(?:년도|년)", question)
    if year_match:
        return date(int(year_match.group(1)), 1, 1)

    return default_date


def is_effective_on(effective_date: Any, start_date: Any, end_date: Any = None) -> bool:
    resolved_effective = normalize_date_value(effective_date)
    resolved_start = normalize_date_value(start_date)
    resolved_end = normalize_date_value(end_date)
    if resolved_effective is None or resolved_start is None:
        return False
    if resolved_effective < resolved_start:
        return False
    if resolved_end is not None and resolved_effective > resolved_end:
        return False
    return True