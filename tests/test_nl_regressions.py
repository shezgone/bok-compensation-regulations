import json
from pathlib import Path

import pytest

from bok_compensation import nl_query as typedb_nl_query
from bok_compensation_neo4j import nl_query as neo4j_nl_query


CASES = [
    {
        "question": "3급 부장 직책급은?",
        "kind": "position_pay",
        "expected_values": {"amount": 2868000.0},
    },
    {
        "question": "2025년 기준 팀장의 EX 평가상여금 지급률은 몇 %인가?",
        "kind": "bonus_rate",
        "expected_values": {"rate": 0.85},
    },
    {
        "question": "5급 11호봉 기본급은 얼마인가?",
        "kind": "step_salary",
        "expected_values": {"step_no": 11, "amount": 1554000.0},
    },
    {
        "question": "2025년 기준 1급 연봉상한액은 얼마인가?",
        "kind": "salary_cap",
        "expected_values": {"cap": 85728000.0},
    },
    {
        "question": "미국 2급 직원의 국외본봉은 얼마인가?",
        "kind": "foreign_salary",
        "expected_values": {"country": "미국", "grade": "2급", "amount": 9760.0, "currency": "USD"},
    },
    {
        "question": "해외직원은 누구를 말하나?",
        "kind": "regulation_definition",
        "expected_values": {"article": "제2조", "topic": "해외직원 정의"},
    },
    {
        "question": "3급 팀장이 EX 평가를 받으면 직책급, 연봉차등액, 연봉상한액은?",
        "kind": "compensation_bundle",
        "expected_values": {"position_pay": 1956000.0, "salary_diff": 3024000.0, "salary_cap": 77724000.0},
    },
]


def _write_artifact(backend: str, question: str, payload: dict) -> str:
    base_dir = Path(__file__).resolve().parents[1] / "artifacts" / "query_failures"
    base_dir.mkdir(parents=True, exist_ok=True)
    slug = "".join(character if character.isalnum() else "_" for character in question).strip("_")[:80] or backend
    file_path = base_dir / f"pytest_{backend}_{slug}.json"
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path)


def _assert_expected(backend: str, question: str, result: dict, expected_kind: str, expected_values: dict):
    deterministic = result["trace"].get("deterministic_execution")
    if deterministic is None:
        artifact = _write_artifact(
            backend,
            question,
            {
                "backend": backend,
                "question": question,
                "answer": result["answer"],
                "trace": result["trace"],
                "expected_kind": expected_kind,
                "expected_values": expected_values,
            },
        )
        pytest.fail(f"deterministic execution missing for question '{question}' (artifact: {artifact})")

    if deterministic["kind"] != expected_kind:
        artifact = _write_artifact(
            backend,
            question,
            {
                "backend": backend,
                "question": question,
                "answer": result["answer"],
                "trace": result["trace"],
                "expected_kind": expected_kind,
                "expected_values": expected_values,
            },
        )
        pytest.fail(
            f"expected kind {expected_kind} but got {deterministic['kind']} for question '{question}' (artifact: {artifact})"
        )

    actual_values = deterministic.get("values") or {}
    mismatches = {}
    for key, expected in expected_values.items():
        actual = actual_values.get(key)
        if isinstance(expected, float):
            if actual is None or abs(float(actual) - expected) >= 1:
                mismatches[key] = {"expected": expected, "actual": actual}
        else:
            if actual != expected:
                mismatches[key] = {"expected": expected, "actual": actual}

    if mismatches:
        artifact = _write_artifact(
            backend,
            question,
            {
                "backend": backend,
                "question": question,
                "answer": result["answer"],
                "trace": result["trace"],
                "expected_kind": expected_kind,
                "expected_values": expected_values,
                "mismatches": mismatches,
            },
        )
        pytest.fail(f"value mismatches for question '{question}': {mismatches} (artifact: {artifact})")


@pytest.mark.parametrize(
    "backend,module",
    [
        ("typedb", typedb_nl_query),
        ("neo4j", neo4j_nl_query),
    ],
)
@pytest.mark.parametrize("case", CASES)
def test_nl_regressions(monkeypatch, backend, module, case):
    monkeypatch.setattr(module, "_invoke_json", lambda prompt: {})
    monkeypatch.setattr(module, "generate_answer", lambda question, entities, rules_context, graph_context: "FALLBACK")

    result = module.run_with_trace(case["question"])

    _assert_expected(backend, case["question"], result, case["kind"], case["expected_values"])