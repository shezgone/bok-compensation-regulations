from bok_compensation.query_rules import (
    neo4j_rule_based_plan,
    repair_neo4j_plan,
    repair_typedb_plan,
    typedb_rule_based_plan,
)


def test_typedb_rule_based_plan_for_g5_question():
    plan = typedb_rule_based_plan("G5 직원의 초봉은?")

    assert plan is not None
    assert "초임호봉결정" in plan["typeql"]
    assert any(variable["name"] == "salary" for variable in plan["variables"])


def test_neo4j_rule_based_plan_for_revision_history_question():
    plan = neo4j_rule_based_plan("보수규정 개정이력을 알려줘")

    assert plan is not None
    assert "RETURN h.설명 AS desc" in plan["cypher"]


def test_rule_based_plans_cover_us_grade_one_overseas_salary_question():
    typedb_plan = typedb_rule_based_plan("미국 주재 1급 직원의 국외본봉은 얼마인가?")
    neo4j_plan = neo4j_rule_based_plan("미국 주재 1급 직원의 국외본봉은 얼마인가?")

    assert typedb_plan is not None
    assert neo4j_plan is not None
    assert '직급코드 "1급"' in typedb_plan["typeql"]
    assert "직급코드: '1급'" in neo4j_plan["cypher"]


def test_repair_typedb_plan_falls_back_when_invalid_keywords_present():
    repaired = repair_typedb_plan(
        "4급의 호봉 목록을 보여줘",
        {"typeql": "match $x owns 호봉번호 1;", "variables": [{"name": "$x", "type": "integer"}]},
    )

    assert "호봉체계구성" in repaired["typeql"]
    assert repaired["variables"][0]["name"] == "n"


def test_repair_neo4j_plan_rewrites_common_bad_properties():
    repaired = repair_neo4j_plan(
        "미국 주재 2급 직원의 국외본봉은?",
        {"cypher": "MATCH (b:국외본봉기준)-[:해당직급]->(r:직급 {등급: '2급'}) RETURN b.name AS 국외본봉"},
    )

    assert "직급코드" in repaired["cypher"]
    assert "국외기본급액" in repaired["cypher"]