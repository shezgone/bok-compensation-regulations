"""Compatibility natural-language query entrypoint for TypeDB."""

import json
import os
import sys
from typing import Any, Dict, List, Tuple

from typedb.driver import TransactionType

from .config import TypeDBConfig
from .connection import get_driver


MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

try:
    with open(TypeDBConfig().schema_file, "r", encoding="utf-8") as schema_file:
        SCHEMA_TEXT = schema_file.read()
except OSError:
    SCHEMA_TEXT = ""


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


def get_rules_subgraph() -> str:
    config = TypeDBConfig()
    driver = get_driver(config)
    tx = None
    try:
        tx = driver.transaction(config.database, TransactionType.READ)
        result = tx.query(
            """
            match
                $article isa 조문, has 조번호 $id, has 조문내용 $text;
            sort $id;
            """
        ).resolve()
        rules = []
        for row in result:
            rule_id = row.get("id").get_integer()
            rule_text = row.get("text").get_value()
            rules.append(f"Rule {rule_id}: {rule_text}")
        return "\n".join(rules)
    finally:
        if tx is not None:
            tx.close()
        driver.close()


def semantic_answer(question: str, rules_context: str) -> str:
    prompt = f"""다음 한국은행 보수규정 조문을 읽고 질문에 답하세요.

[보수규정 조문 내용]
{rules_context}

질문: {question}
답변:"""
    return _invoke_text(prompt)


def nl_to_typeql(question: str) -> Dict[str, Any]:
    prompt = f"""당신은 TypeDB 3.x TypeQL READ 쿼리 전문가입니다.
사용자 질문을 TypeDB 3.x 조회 쿼리로 바꾸세요.

규칙:
1. match 절만 사용하세요.
2. 응답은 JSON 하나만 반환하세요.
3. 변수명에는 달러 기호를 포함하지 마세요.

응답 형식:
{{
  "typeql": "match $x isa 규정;",
  "variables": [{{"name": "value", "type": "string"}}],
  "explanation": "쿼리 설명"
}}

[Schema 일부]
{SCHEMA_TEXT[:5000]}

질문: {question}
"""
    return _invoke_json(prompt)


def execute_typeql(typeql: str, variables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    config = TypeDBConfig()
    driver = get_driver(config)
    tx = None
    rows: List[Dict[str, Any]] = []
    try:
        tx = driver.transaction(config.database, TransactionType.READ)
        result = tx.query(typeql).resolve()
        for row in result:
            record: Dict[str, Any] = {}
            for variable in variables:
                name = variable["name"]
                value_type = variable.get("type", "string")
                concept = row.get(name)
                if concept is None:
                    record[name] = None
                elif value_type == "integer":
                    record[name] = concept.get_integer()
                elif value_type == "double":
                    record[name] = concept.get_double()
                elif value_type == "datetime":
                    raw = concept.get_value()
                    record[name] = str(raw)[:10] if raw else None
                else:
                    record[name] = concept.get_value()
            rows.append(record)
        return rows
    finally:
        if tx is not None:
            tx.close()
        driver.close()


def _enrich_starting_step(
    rows: List[Dict[str, Any]], variables: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    return rows, variables


def generate_answer(question: str, variables: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "조회 결과가 없습니다."

    prompt = f"""다음 질문과 DB 조회 결과를 바탕으로 간결하게 답하세요.

질문: {question}
변수 정의: {json.dumps(variables, ensure_ascii=False)}
조회 결과: {json.dumps(rows, ensure_ascii=False)}
"""
    return _invoke_text(prompt)


def run(question: str) -> str:
    intent = classify_intent(question)
    if intent == "Semantic":
        rules_context = get_rules_subgraph()
        return semantic_answer(question, rules_context)

    plan = nl_to_typeql(question)
    typeql = plan["typeql"]
    variables = plan.get("variables", [])
    rows = execute_typeql(typeql, variables)
    rows, variables = _enrich_starting_step(rows, variables)
    return generate_answer(question, variables, rows)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "일반사무직원의 초봉은?"
    print(run(query))