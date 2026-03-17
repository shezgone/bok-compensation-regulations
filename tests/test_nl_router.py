from bok_compensation_neo4j import nl_query


def test_run_rejects_invalid_grade_step_combination(monkeypatch):
    monkeypatch.setattr(
        nl_query,
        "extract_entities",
        lambda question: {"grade": "1급", "step_no": 49, "topics": ["호봉"], "eval": "EX"},
    )

    result = nl_query.run("1급 49호봉 팀장의 연봉은? 평가는 EX")

    assert "질문 조건이 현재 규정 체계와 맞지 않아" in result
    assert "1급은(는) 연봉제본봉 적용 대상" in result


def test_run_uses_graph_first_semantic_context(monkeypatch):
    calls = []

    monkeypatch.setattr(nl_query, "extract_entities", lambda question: {"topics": ["조문"], "article_no": 14})
    monkeypatch.setattr(nl_query, "try_execute_regulation", lambda question, entities: None)
    monkeypatch.setattr(nl_query, "try_execute", lambda question, entities, provider: None)

    def fake_fetch_relevant_rules(question, entities):
        calls.append(("rules", question, entities))
        return "Rule 14: 기한부 고용계약자는 상여금 미지급"

    def fake_fetch_subgraph(question_entities, question):
        calls.append(("graph", question_entities, question))
        return "", []

    def fake_generate_answer(question, entities, rules_context, graph_context):
        calls.append(("answer", question, entities, rules_context, graph_context))
        return "상여금을 받을 수 없습니다."

    monkeypatch.setattr(nl_query, "fetch_relevant_rules", fake_fetch_relevant_rules)
    monkeypatch.setattr(nl_query, "fetch_subgraph_neo4j", fake_fetch_subgraph)
    monkeypatch.setattr(nl_query, "generate_answer", fake_generate_answer)

    result = nl_query.run("기한부 고용계약자는 상여금을 받을 수 있어?")

    assert result == "상여금을 받을 수 없습니다."
    assert calls[0][0] == "rules"
    assert calls[1][0] == "graph"
    assert calls[2][0] == "answer"


def test_run_uses_graph_first_data_context(monkeypatch):
    calls = []

    monkeypatch.setattr(
        nl_query,
        "extract_entities",
        lambda question: {"topics": ["연봉차등"], "grade": None, "eval": None, "amount_threshold": 2000000.0},
    )

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
    monkeypatch.setattr(nl_query, "fetch_subgraph_neo4j", fake_fetch_subgraph)
    monkeypatch.setattr(nl_query, "generate_answer", fake_generate_answer)

    result = nl_query.run("일반사무직원의 초봉은?")

    assert result == "결과는 1입니다."
    assert calls[0][0] == "rules"
    assert calls[1][0] == "graph"
    assert calls[2][0] == "answer"


def test_neo4j_salary_diff_listing_dedupes_base_and_addendum(monkeypatch):
    calls = []

    def fake_execute_cypher(query):
        calls.append(query)
        if "MATCH (b:부칙)-[r:규정_대체]->(d:연봉차등액기준)" in query:
            return []
        if "RETURN g.직급코드 AS grade, e.평가등급 AS eval, d.차등액 AS amount, d.연봉차등액코드 AS code" in query:
            return [
                {"grade": "1급", "eval": "EX", "amount": 3672000.0, "code": "ADIFF-1급-EX"},
                {"grade": "1급", "eval": "EX", "amount": 3672000.0, "code": "DIFF-1급-EX"},
                {"grade": "2급", "eval": "EE", "amount": 2232000.0, "code": "ADIFF-2급-EE"},
                {"grade": "2급", "eval": "EE", "amount": 2232000.0, "code": "DIFF-2급-EE"},
            ]
        raise AssertionError(query)

    monkeypatch.setattr(nl_query, "_execute_cypher", fake_execute_cypher)

    rows = nl_query._Neo4jDeterministicProvider().list_salary_diffs(2000000.0, "2026-03-18")

    assert rows == [
        {"grade": "1급", "eval": "EX", "amount": 3672000.0},
        {"grade": "2급", "eval": "EE", "amount": 2232000.0},
    ]


def test_run_rejects_step_salary_without_grade(monkeypatch):
    monkeypatch.setattr(
        nl_query,
        "extract_entities",
        lambda question: {"grade": None, "position": "팀장", "step_no": 50, "topics": ["호봉"]},
    )

    result = nl_query.run("50호봉 팀장의 연봉은?")

    assert "직급 정보가 필요" in result
    assert "팀장 정보만으로는 연봉을 계산할 수 없습니다" in result