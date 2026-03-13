import json
from pathlib import Path

import pytest

from bok_compensation.nl_query import execute_typeql, nl_to_typeql
from bok_compensation_neo4j.nl_query import execute_cypher, nl_to_cypher


CASES = [
    ("일반사무직원의 초임호봉과 초봉은?", [1, 531000]),
    ("청원경찰의 초임호봉과 초봉은?", [6, 740000]),
    ("3급 부장 직책급은?", [2868000]),
    ("부서장(가)가 EX 평가를 받으면 평가상여금 지급률은?", [1.0]),
    ("종합기획직 G5의 초임호봉과 본봉 액수를 알려줘", [11, 1554000]),
    ("3급 팀장이 EX 평가를 받으면 직책급, 연봉차등액, 연봉상한액은?", [1956000, 3024000, 77724000]),
    ("3급 팀장 EX 기준 보수 패키지에서 직책급과 연봉차등액, 연봉상한액을 알려줘", [1956000, 3024000, 77724000]),
]


def _flatten_numeric(rows):
    values = []
    for row in rows:
        for value in row.values():
            if isinstance(value, (int, float)):
                values.append(value)
    return values


def _write_artifact(backend: str, question: str, payload: dict) -> str:
    base_dir = Path(__file__).resolve().parents[1] / "artifacts" / "query_failures"
    base_dir.mkdir(parents=True, exist_ok=True)
    slug = "".join(character if character.isalnum() else "_" for character in question).strip("_")[:80] or backend
    file_path = base_dir / f"pytest_{backend}_{slug}.json"
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path)


def _assert_expected(backend: str, question: str, plan: dict, rows: list, expected_values: list):
    numeric_values = _flatten_numeric(rows)
    missing = [expected for expected in expected_values if not any(abs(value - expected) < 1 for value in numeric_values)]
    if missing:
        artifact = _write_artifact(
            backend,
            question,
            {
                "backend": backend,
                "question": question,
                "plan": plan,
                "rows": rows,
                "missing_values": missing,
            },
        )
        pytest.fail(f"missing values {missing} for question '{question}' (artifact: {artifact})")


@pytest.mark.parametrize("question,expected_values", CASES)
def test_typedb_nl_regressions(question, expected_values):
    plan = nl_to_typeql(question)
    rows = execute_typeql(plan["typeql"], plan.get("variables", []))
    _assert_expected("typedb", question, plan, rows, expected_values)


@pytest.mark.parametrize("question,expected_values", CASES)
def test_neo4j_nl_regressions(question, expected_values):
    plan = nl_to_cypher(question)
    rows = execute_cypher(plan["cypher"])
    _assert_expected("neo4j", question, plan, rows, expected_values)