from bok_compensation import nl_query as typedb_nl_query
from bok_compensation_neo4j import nl_query as neo4j_nl_query


def test_typedb_extract_entities_normalizes_llm_intent(monkeypatch):
    monkeypatch.setattr(
        typedb_nl_query,
        "_invoke_json",
        lambda prompt: {"intent": "definition", "topics": [], "position": "", "eval": "", "country": "", "track": "", "article_no": None, "keyword": "", "amount_threshold": None},
    )

    entities = typedb_nl_query.extract_entities("해외직원은 누구를 말하나?")

    assert entities["intent"] == "regulation_definition"


def test_neo4j_extract_entities_infers_listing_intent(monkeypatch):
    monkeypatch.setattr(neo4j_nl_query, "_invoke_json", lambda prompt: {})

    entities = neo4j_nl_query.extract_entities("연봉차등액이 200만원 이상인 조합 목록을 보여줘.")

    assert entities["intent"] == "salary_diff_listing"


def test_typedb_extract_entities_infers_compensation_bundle_intent(monkeypatch):
    monkeypatch.setattr(typedb_nl_query, "_invoke_json", lambda prompt: {})

    entities = typedb_nl_query.extract_entities("3급 팀장 EX 기준 보수 패키지에서 직책급과 연봉차등액, 연봉상한액을 알려줘")

    assert entities["intent"] == "compensation_bundle"