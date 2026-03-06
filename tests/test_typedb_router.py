from bok_compensation import nl_query


def test_run_routes_semantic_queries(monkeypatch):
    calls = []

    monkeypatch.setattr(nl_query, "classify_intent", lambda question: "Semantic")

    def fake_get_rules_subgraph():
        calls.append("rules")
        return "Rule 14: 기한부 고용계약자는 상여금 미지급"

    def fake_semantic_answer(question, rules_context):
        calls.append(("semantic_answer", question, rules_context))
        return "상여금을 받을 수 없습니다."

    monkeypatch.setattr(nl_query, "get_rules_subgraph", fake_get_rules_subgraph)
    monkeypatch.setattr(nl_query, "semantic_answer", fake_semantic_answer)

    result = nl_query.run("기한부 고용계약자는 상여금을 받을 수 있어?")

    assert result == "상여금을 받을 수 없습니다."
    assert "rules" in calls
    assert any(call[0] == "semantic_answer" for call in calls if isinstance(call, tuple))


def test_run_routes_data_queries(monkeypatch):
    calls = []

    monkeypatch.setattr(nl_query, "classify_intent", lambda question: "Data")
    monkeypatch.setattr(
        nl_query,
        "nl_to_typeql",
        lambda question: {
            "typeql": "match $x isa 규정;",
            "variables": [{"name": "value", "label": "값", "type": "integer"}],
            "explanation": "테스트 쿼리",
        },
    )

    def fake_execute_typeql(typeql, variables):
        calls.append(("execute", typeql, variables))
        return [{"value": 1}]

    def fake_generate_answer(question, variables, rows):
        calls.append(("answer", question, variables, rows))
        return "결과는 1입니다."

    monkeypatch.setattr(nl_query, "execute_typeql", fake_execute_typeql)
    monkeypatch.setattr(nl_query, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(nl_query, "_enrich_starting_step", lambda rows, variables: (rows, variables))

    result = nl_query.run("일반사무직원의 초봉은?")

    assert result == "결과는 1입니다."
    assert calls[0][0] == "execute"
    assert calls[1] == (
        "answer",
        "일반사무직원의 초봉은?",
        [{"name": "value", "label": "값", "type": "integer"}],
        [{"value": 1}],
    )