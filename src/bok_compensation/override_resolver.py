from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .override_utils import is_effective_on, normalize_date_value


@dataclass(frozen=True)
class OverrideResolution:
    effective_date: Optional[str]
    active_rows: List[Dict[str, Any]]

    @property
    def applied(self) -> bool:
        return bool(self.active_rows)

    @property
    def primary_row(self) -> Optional[Dict[str, Any]]:
        return self.active_rows[0] if self.active_rows else None


def dedupe_override_rows(rows: Sequence[Dict[str, Any]], keys: Sequence[str]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for row in rows:
        marker = tuple(row.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(dict(row))
    return deduped


def select_effective_row(
    rows: Sequence[Dict[str, Any]],
    *,
    effective_date: Optional[str],
    dedupe_keys: Sequence[str],
    start_key: str = "start",
    end_key: str = "end",
    recency_keys: Sequence[str] = ("start",),
) -> Optional[Dict[str, Any]]:
    applicable_rows = [
        dict(row)
        for row in rows
        if effective_date is None
        or row.get(start_key) is None
        or is_effective_on(effective_date, row.get(start_key), row.get(end_key))
    ]
    applicable_rows = dedupe_override_rows(applicable_rows, dedupe_keys)

    def sort_key(row: Dict[str, Any]) -> tuple:
        values = []
        for key in recency_keys:
            normalized = normalize_date_value(row.get(key))
            values.append(normalized.toordinal() if normalized is not None else date.min.toordinal())
        return tuple(values)

    applicable_rows.sort(key=sort_key, reverse=True)
    return applicable_rows[0] if applicable_rows else None


def resolve_active_overrides(
    rows: Sequence[Dict[str, Any]],
    *,
    effective_date: Optional[str],
    dedupe_keys: Sequence[str],
    priority_keys: Sequence[str] = ("priority", "buchik_jo"),
    start_key: str = "start",
    end_key: str = "end",
) -> OverrideResolution:
    active_rows = [
        dict(row)
        for row in rows
        if effective_date is None or is_effective_on(effective_date, row.get(start_key), row.get(end_key))
    ]
    active_rows = dedupe_override_rows(active_rows, dedupe_keys)
    active_rows.sort(key=lambda row: tuple(row.get(key) if row.get(key) is not None else 999 for key in priority_keys))
    return OverrideResolution(effective_date=effective_date, active_rows=active_rows)


def render_article_override_lines(rows: Sequence[Dict[str, Any]]) -> List[str]:
    return [
        f"[활성 오버라이드] 부칙 제{row['buchik_jo']}조: {row['content']} (사유: {row['reason']})"
        for row in rows
    ]