from bok_compensation.override_resolver import render_article_override_lines, resolve_active_overrides, select_effective_row


def test_resolve_active_overrides_filters_by_effective_date_and_priority():
    rows = [
        {
            "buchik_jo": 2,
            "priority": 2,
            "reason": "open-ended",
            "content": "부칙 제2조",
            "start": "2025-01-01",
            "end": None,
        },
        {
            "buchik_jo": 3,
            "priority": 1,
            "reason": "2025 only",
            "content": "부칙 제3조",
            "start": "2025-01-01",
            "end": "2025-12-31",
        },
    ]

    resolution_2025 = resolve_active_overrides(rows, effective_date="2025-06-01", dedupe_keys=["buchik_jo", "reason"])
    resolution_2026 = resolve_active_overrides(rows, effective_date="2026-01-01", dedupe_keys=["buchik_jo", "reason"])

    assert resolution_2025.applied is True
    assert [row["buchik_jo"] for row in resolution_2025.active_rows] == [3, 2]
    assert resolution_2026.applied is True
    assert [row["buchik_jo"] for row in resolution_2026.active_rows] == [2]


def test_resolve_active_overrides_dedupes_duplicate_rows():
    rows = [
        {
            "buchik_jo": 2,
            "priority": 2,
            "reason": "same",
            "content": "부칙 제2조",
            "start": "2025-01-01",
            "end": None,
        },
        {
            "buchik_jo": 2,
            "priority": 2,
            "reason": "same",
            "content": "부칙 제2조",
            "start": "2025-01-01",
            "end": None,
        },
    ]

    resolution = resolve_active_overrides(rows, effective_date="2025-06-01", dedupe_keys=["buchik_jo", "reason", "content"])

    assert len(resolution.active_rows) == 1


def test_render_article_override_lines_formats_user_facing_lines():
    lines = render_article_override_lines([
        {"buchik_jo": 3, "content": "부칙 내용", "reason": "오버라이드 사유"},
    ])

    assert lines == ["[활성 오버라이드] 부칙 제3조: 부칙 내용 (사유: 오버라이드 사유)"]


def test_select_effective_row_prefers_latest_active_start_date():
    row = select_effective_row(
        [
            {"code": "CAP-1", "amount": 100.0, "start": "2025-01-01"},
            {"code": "CAP-1", "amount": 120.0, "start": "2026-01-01"},
        ],
        effective_date="2026-03-01",
        dedupe_keys=["code", "start"],
    )

    assert row == {"code": "CAP-1", "amount": 120.0, "start": "2026-01-01"}


def test_select_effective_row_keeps_startless_rows_available():
    row = select_effective_row(
        [{"code": "BONUS-EVAL-TM-EX", "rate": 0.85}],
        effective_date="2025-06-01",
        dedupe_keys=["code"],
    )

    assert row == {"code": "BONUS-EVAL-TM-EX", "rate": 0.85}