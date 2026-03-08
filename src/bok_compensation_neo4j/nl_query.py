"""Compatibility natural-language query entrypoint for Neo4j."""

import json
import os
import sys
from typing import Any, Dict, List

from .config import Neo4jConfig
from .connection import get_driver


MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

GRAPH_SCHEMA = """
[Neo4j 그래프 스키마]
노드: (:규정), (:조문), (:직렬), (:직급), (:직위), (:호봉), (:수당), (:보수기준), (:직책급기준), (:상여금기준), (:연봉차등액기준), (:연봉상한액기준), (:임금피크제기준), (:국외본봉기준), (:초임호봉기준), (:평가결과)
관계: -[:규정구성]->, -[:직렬분류]->, -[:호봉체계구성]->, -[:해당직급]->, -[:해당직위]->, -[:해당직책구분]->, -[:해당등급]->, -[:대상직렬]->
"""


def _invoke_text(prompt: str) -> str:
    try:
        from langchain_core.messages import HumanMessage
        from langchain_ollama import ChatOllama
    except ImportError:
        return prompt

    model = ChatOllama(model=MODEL_NAME, base_url=OLLAMA_URL, temperature=0.0)
    response = model.invoke([HumanMessage(content=prompt)])
    return response.content


def _invoke_json(prompt: str) -> Dict[str, Any]:
    try:
        from langchain_core.messages import HumanMessage
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise RuntimeError("langchain-ollama and langchain-core are required for NL query generation") from exc

    model = ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_URL,
        temperature=0.0,
        format="json",
    )
    response = model.invoke([HumanMessage(content=prompt)])
    return json.loads(response.content)


def classify_intent(question: str) -> str:
    semantic_markers = ("수 있어", "가능", "대상", "해석", "규정", "조문", "해당", "조건")
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
    prompt = f"""당신은 Neo4j Cypher 전문가입니다.
다음 그래프 스키마를 바탕으로 질문에 맞는 조회용 Cypher를 생성하세요.

{GRAPH_SCHEMA}

응답 형식:
{{
  "cypher": "MATCH (n) RETURN n LIMIT 10",
  "explanation": "쿼리 설명"
}}

질문: {question}
"""
    return _invoke_json(prompt)


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


def generate_answer(question: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "조회 결과가 없습니다."

    prompt = f"""다음 질문과 DB 조회 결과를 바탕으로 간결하게 답하세요.

질문: {question}
조회 결과: {json.dumps(rows, ensure_ascii=False)}
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
    rows = execute_cypher(cypher)
    rows = _enrich_starting_step(rows)
    return generate_answer(question, rows)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "일반사무직원의 초봉은?"
    print(run(query))