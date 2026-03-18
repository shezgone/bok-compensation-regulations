from bok_compensation import nl_query


def test_run_routes_semantic_queries(monkeypatch):
    calls = []

    monkeypatch.setattr(nl_query, "extract_entities", lambda question: {"topics": ["조문"], "article_no": 14})
    monkeypatch.setattr(nl_query, "try_execute_regulation", lambda question, entities: None)
    monkeypatch.setattr(nl_query, "try_execute", lambda question, entities, provider: None)

    def fake_fetch_relevant_rules(question, entities):
        calls.append(("rules", question, entities))
        return "Rule 14: 기한부 고용계약자는 상여금 미지급"

    def fake_fetch_subgraph(entities, question):
        calls.append(("graph", entities, question))
        return "", []

    def fake_generate_answer(question, entities, rules_context, graph_context):
        calls.append(("answer", question, entities, rules_context, graph_context))
        return "상여금을 받을 수 없습니다."

    monkeypatch.setattr(nl_query, "fetch_relevant_rules", fake_fetch_relevant_rules)
    monkeypatch.setattr(nl_query, "fetch_subgraph_typedb", fake_fetch_subgraph)
    monkeypatch.setattr(nl_query, "generate_answer", fake_generate_answer)

    result = nl_query.run("기한부 고용계약자는 상여금을 받을 수 있어?")

    assert result == "상여금을 받을 수 없습니다."
    assert calls[0][0] == "rules"
    assert calls[1][0] == "graph"
    assert calls[2][0] == "answer"


def test_run_routes_data_queries(monkeypatch):
    calls = []

    monkeypatch.setattr(
        nl_query,
        "extract_entities",
        lambda question: {"topics": ["연봉차등"], "grade": None, "eval": None, "amount_threshold": 2000000.0},
    )
    monkeypatch.setattr(nl_query, "try_execute_regulation", lambda question, entities: None)
    monkeypatch.setattr(nl_query, "try_execute", lambda question, entities, provider: None)

    def fake_fetch_rules(question, entities):
        calls.append(("rules", question, entities))
        return "제4조: 연봉차등액을 적용한다."

    def fake_fetch_subgraph(entities, question):
        calls.append(("graph", entities, question))
        return "[연봉차등 2-hop]\n- grade=1급, eval=EX, diff=3672000", []

    def fake_generate_answer(question, entities, rules_context, graph_context):
        calls.append(("answer", question, entities, rules_context, graph_context))
        return "결과는 1입니다."

    monkeypatch.setattr(nl_query, "fetch_relevant_rules", fake_fetch_rules)
    monkeypatch.setattr(nl_query, "fetch_subgraph_typedb", fake_fetch_subgraph)
    monkeypatch.setattr(nl_query, "generate_answer", fake_generate_answer)

    result = nl_query.run("일반사무직원의 초봉은?")

    assert result == "결과는 1입니다."
    assert calls[0][0] == "rules"
    assert calls[1][0] == "graph"
    assert calls[2][0] == "answer"