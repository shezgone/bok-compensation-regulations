from types import SimpleNamespace

from bok_compensation_neo4j import nl_query


def test_run_routes_semantic_queries(monkeypatch):
    calls = []

    class DummyDriver:
        def close(self):
            calls.append("close")

    monkeypatch.setattr(nl_query, "classify_intent", lambda question: "Semantic")
    monkeypatch.setattr(nl_query, "Neo4jConfig", lambda: SimpleNamespace(database="test-db"))
    monkeypatch.setattr(nl_query, "get_driver", lambda config: DummyDriver())

    def fake_get_rules_subgraph(driver):
        calls.append(("rules", driver.__class__.__name__))
        return "Rule 14: 기한부 고용계약자는 상여금 미지급"

    def fake_semantic_answer(question, rules_context):
        calls.append(("semantic_answer", question, rules_context))
        return "상여금을 받을 수 없습니다."

    monkeypatch.setattr(nl_query, "get_rules_subgraph", fake_get_rules_subgraph)
    monkeypatch.setattr(nl_query, "semantic_answer", fake_semantic_answer)

    result = nl_query.run("기한부 고용계약자는 상여금을 받을 수 있어?")

    assert result == "상여금을 받을 수 없습니다."
    assert ("rules", "DummyDriver") in calls
    assert any(call[0] == "semantic_answer" for call in calls if isinstance(call, tuple))


def test_run_routes_data_queries(monkeypatch):
    calls = []

    monkeypatch.setattr(nl_query, "classify_intent", lambda question: "Data")
    monkeypatch.setattr(
        nl_query,
        "nl_to_cypher",
        lambda question: {
            "cypher": "MATCH (n) RETURN 1 AS value",
            "explanation": "테스트 쿼리",
        },
    )

    def fake_execute_cypher(cypher):
        calls.append(("execute", cypher))
        return [{"value": 1}]

    def fake_generate_answer(question, rows):
        calls.append(("answer", question, rows))
        return "결과는 1입니다."

    monkeypatch.setattr(nl_query, "execute_cypher", fake_execute_cypher)
    monkeypatch.setattr(nl_query, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(nl_query, "_enrich_starting_step", lambda rows: rows)

    result = nl_query.run("일반사무직원의 초봉은?")

    assert result == "결과는 1입니다."
    assert calls[0] == ("execute", "MATCH (n) RETURN 1 AS value")
    assert calls[1] == ("answer", "일반사무직원의 초봉은?", [{"value": 1}])