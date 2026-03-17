"""Shared planner helpers without rule-based query templates."""

from typing import Dict, List


def normalize_planner_outputs(
    original_question: str,
    semantic_queries: List[str],
    data_queries: List[str],
) -> Dict[str, List[str]]:
    quantitative_markers = (
        "얼마",
        "금액",
        "지급률",
        "호봉",
        "초봉",
        "국외본봉",
        "연봉상한액",
        "연봉차등액",
        "직책급",
    )

    normalized_semantic: List[str] = []
    normalized_data = list(data_queries)

    for query in semantic_queries:
        if any(marker in query for marker in quantitative_markers):
            normalized_data.append(query)
        else:
            normalized_semantic.append(query)

    if not normalized_semantic and not normalized_data:
        normalized_data.append(original_question)

    return {
        "semantic_queries": normalized_semantic,
        "data_queries": normalized_data,
    }