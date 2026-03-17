"""Compatibility natural-language query entrypoint for Neo4j."""

import json
import os
import sys
from typing import Any, Dict, List

from .config import Neo4jConfig
from .connection import get_driver
from bok_compensation.llm import create_chat_model
from bok_compensation.query_retrieval import build_trace_context, maybe_write_query_trace
from bok_compensation.query_rules import neo4j_rule_based_plan, repair_neo4j_plan


GRAPH_SCHEMA = """
[Neo4j 그래프 스키마]
노드: (:규정), (:조문), (:개정이력), (:직렬), (:직급), (:직위), (:호봉), (:수당), (:보수기준), (:직책급기준), (:상여금기준), (:연봉차등액기준), (:연봉상한액기준), (:임금피크제기준), (:국외본봉기준), (:초임호봉기준), (:평가결과)
관계: -[:규정구성]->, -[:규정개정]->, -[:직렬분류]->, -[:호봉체계구성]->, -[:해당직급]->, -[:해당직위]->, -[:해당직책구분]->, -[:해당등급]->, -[:대상직렬]->
"""


def _invoke_text(prompt: str) -> str:
    try:
        from langchain_core.messages import HumanMessage
    except ImportError:
        return prompt

    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=prompt)])
    return response.content


def _invoke_json(prompt: str) -> Dict[str, Any]:
    try:
        from langchain_core.messages import HumanMessage
    except ImportError as exc:
        raise RuntimeError("langchain-core and an LLM backend package are required for NL query generation") from exc

    model = create_chat_model(temperature=0.0, json_output=True)
    response = model.invoke([HumanMessage(content=prompt)])
    return json.loads(response.content)


def classify_intent(question: str) -> str:
    data_markers = ("산정", "계산", "본봉", "호봉", "차등액", "상한액", "직책급", "상여금", "얼마", "금액")
    if any(marker in question for marker in data_markers):
        return "Data"
    semantic_markers = ("수 있어", "가능", "대상", "해석", "조문")
    if any(marker in question for marker in semantic_markers):
        return "Semantic"
    return "Data"


def get_rules_subgraph(driver) -> str:
    config = Neo4jConfig()
    with driver.session(database=config.database) as session:
        result = session.run(
            "MATCH (n:조문) RETURN n.조번호 AS id, n.조문내용 AS text ORDER BY id"
        )
        return "\n".join(f"Rule {record['id']}: {record['text']}" for record in result)


def semantic_answer(question: str, rules_context: str) -> str:
    prompt = f"""다음 한국은행 보수규정 조문을 읽고 질문에 답하세요.

[보수규정 조문 내용]
{rules_context}

질문: {question}
답변:"""
    return _invoke_text(prompt)


def nl_to_cypher(question: str) -> Dict[str, Any]:
    trace_context = build_trace_context(question, backend="neo4j")
    fallback = neo4j_rule_based_plan(question)
    if fallback is not None:
        plan = dict(fallback)
        plan["trace"] = trace_context
        maybe_write_query_trace(question, backend="neo4j", trace_context=trace_context, plan=plan)
        return plan

    prompt = f"""당신은 Neo4j Cypher 전문가입니다.
다음 그래프 스키마를 바탕으로 질문에 맞는 조회용 Cypher를 생성하세요.

{GRAPH_SCHEMA}

반드시 지킬 규칙:
- 직급 조건에는 `직급코드`를 사용하세요.
- 직위 조건에는 `직위명`을 사용하세요.
- 평가 조건에는 `평가등급`을 사용하세요.
- 개정이력 설명은 `설명`을 사용하세요.
- 국외본봉 금액은 `국외기본급액`을 사용하세요.
- 존재하지 않는 속성 `등급`, `이름`, `name` 을 사용하지 마세요.
- 존재하지 않는 관계를 만들지 말고, 스키마에 있는 관계만 사용하세요.

정답 예시:
- `MATCH (g:직급 {{직급코드: '4급'}})-[:호봉체계구성]->(h:호봉) RETURN h.호봉번호 AS n, h.호봉금액 AS amt`
- `MATCH (h:개정이력) RETURN h.설명 AS desc, h.개정일 AS rev_date`

응답 형식:
{{
  "cypher": "MATCH (n) RETURN n LIMIT 10",
  "explanation": "쿼리 설명"
}}

질문: {question}
"""
    plan = _invoke_json(prompt)
    repaired = repair_neo4j_plan(question, plan)
    repaired = dict(repaired)
    repaired["trace"] = trace_context
    maybe_write_query_trace(question, backend="neo4j", trace_context=trace_context, plan=repaired)
    return repaired


def execute_cypher(cypher: str) -> List[Dict[str, Any]]:
    config = Neo4jConfig()
    driver = get_driver(config)
    try:
        with driver.session(database=config.database) as session:
            return [record.data() for record in session.run(cypher)]
    finally:
        driver.close()


def _enrich_starting_step(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return rows


def generate_answer(question: str, rows: List[Dict[str, Any]], explanation: str = "") -> str:
    if not rows:
        return "조회 결과가 없습니다."

    explanation_note = f"\n조회 설명: {explanation}" if explanation else ""
    prompt = f"""다음 질문과 DB 조회 결과를 바탕으로 간결하게 답하세요.
계산이 필요하면 DB에서 조회한 숫자만 사용하여 정확하게 계산하세요. 절대 임의로 숫자를 만들지 마세요.

질문: {question}
조회 결과: {json.dumps(rows, ensure_ascii=False)}{explanation_note}
"""
    return _invoke_text(prompt)


def run(question: str) -> str:
    intent = classify_intent(question)
    if intent == "Semantic":
        config = Neo4jConfig()
        driver = get_driver(config)
        try:
            rules_context = get_rules_subgraph(driver)
            return semantic_answer(question, rules_context)
        finally:
            driver.close()

    plan = nl_to_cypher(question)
    cypher = plan["cypher"]
    explanation = plan.get("explanation", "")
    rows = execute_cypher(cypher)
    rows = _enrich_starting_step(rows)
    return generate_answer(question, rows, explanation)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "일반사무직원의 초봉은?"
    print(run(query))