from bok_compensation import nl_query as typedb_nl_query
from bok_compensation_neo4j import nl_query as neo4j_nl_query


def test_typedb_override_sections_include_compensation_domains(monkeypatch):
    def fake_execute_rows(query, variables):
        if "연봉상한액기준" in query and "규정_대체" in query and "대체만료일 $end" not in query:
            return [{"buchik_jo": 2, "priority": 2, "code": "CAP-1급", "reason": "cap override", "start": "2025-01-01"}]
        if "직책급기준" in query and "규정_대체" in query and "대체만료일 $end" not in query:
            return [{"buchik_jo": 2, "priority": 2, "code": "PP-P05-3급", "reason": "position override", "start": "2025-01-01"}]
        if "상여금기준" in query and "규정_대체" in query and "대체만료일 $end" not in query:
            return [{"buchik_jo": 2, "priority": 2, "code": "BONUS-EVAL-P05-EX", "reason": "bonus override", "start": "2025-01-01"}]
        return []

    monkeypatch.setattr(typedb_nl_query, "_execute_rows", fake_execute_rows)

    sections = typedb_nl_query._fetch_override_sections_typedb(
        {
            "topics": ["연봉상한", "직책급", "상여금"],
            "grade": "3급",
            "position": "팀장",
            "eval": "EX",
            "effective_date": "2025-06-01",
        }
    )

    joined = "\n".join(sections)
    assert "부칙 연봉상한 오버라이드 3-hop" in joined
    assert "부칙 직책급 오버라이드 3-hop" in joined
    assert "부칙 상여금 오버라이드 3-hop" in joined


def test_neo4j_override_sections_include_compensation_domains(monkeypatch):
    def fake_execute_cypher(query):
        if "연봉상한액기준" in query and "규정_대체" in query:
            return [{"buchik_jo": 2, "priority": 2, "code": "CAP-1급", "reason": "cap override", "start": "2025-01-01", "end": None}]
        if "직책급기준" in query and "규정_대체" in query:
            return [{"buchik_jo": 2, "priority": 2, "code": "PP-P05-3급", "reason": "position override", "start": "2025-01-01", "end": None}]
        if "상여금기준" in query and "규정_대체" in query:
            return [{"buchik_jo": 2, "priority": 2, "code": "BONUS-EVAL-P05-EX", "reason": "bonus override", "start": "2025-01-01", "end": None}]
        return []

    monkeypatch.setattr(neo4j_nl_query, "_execute_cypher", fake_execute_cypher)

    sections = neo4j_nl_query._fetch_override_sections_neo4j(
        {
            "topics": ["연봉상한", "직책급", "상여금"],
            "grade": "3급",
            "position": "팀장",
            "eval": "EX",
            "effective_date": "2025-06-01",
        }
    )

    joined = "\n".join(sections)
    assert "부칙 연봉상한 오버라이드 3-hop" in joined
    assert "부칙 직책급 오버라이드 3-hop" in joined
    assert "부칙 상여금 오버라이드 3-hop" in joined
