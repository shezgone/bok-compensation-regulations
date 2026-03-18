from bok_compensation_typedb import nl_query as typedb_nl_query


def test_typedb_extract_entities_normalizes_llm_intent(monkeypatch):
    monkeypatch.setattr(
        typedb_nl_query,
        "_invoke_json",
        lambda prompt: {"intent": "definition", "topics": [], "position": "", "eval": "", "country": "", "track": "", "article_no": None, "keyword": "", "amount_threshold": None},
    )

    entities = typedb_nl_query.extract_entities("해외직원은 누구를 말하나?")

    assert entities["intent"] == "regulation_definition"




def test_typedb_extract_entities_infers_compensation_bundle_intent(monkeypatch):
    monkeypatch.setattr(typedb_nl_query, "_invoke_json", lambda prompt: {})

    entities = typedb_nl_query.extract_entities("3급 팀장 EX 기준 보수 패키지에서 직책급과 연봉차등액, 연봉상한액을 알려줘")

    assert entities["intent"] == "compensation_bundle"