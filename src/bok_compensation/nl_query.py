"""Compatibility natural-language query entrypoint for TypeDB."""

import json
import os
import sys
from typing import Any, Dict, List, Tuple

from typedb.driver import TransactionType

from .config import TypeDBConfig
from .connection import get_driver
from .llm import create_chat_model
from .query_retrieval import build_trace_context, maybe_write_query_trace
from .query_rules import repair_typedb_plan, typedb_rule_based_plan


try:
    with open(TypeDBConfig().schema_file, "r", encoding="utf-8") as schema_file:
        SCHEMA_TEXT = schema_file.read()
except OSError:
    SCHEMA_TEXT = ""


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
    trace_context = build_trace_context(question, backend="typedb")
    fallback = typedb_rule_based_plan(question)
    if fallback is not None:
        plan = dict(fallback)
        plan["trace"] = trace_context
        maybe_write_query_trace(question, backend="typedb", trace_context=trace_context, plan=plan)
        return plan

    prompt = f"""당신은 TypeDB 3.x TypeQL READ 쿼리 전문가입니다.
사용자 질문을 TypeDB 3.x 조회 쿼리로 바꾸세요.

규칙:
1. match 절만 사용하세요.
2. 응답은 JSON 하나만 반환하세요.
3. 변수명에는 달러 기호를 포함하지 마세요.
4. 값 차이, 비율, 비교처럼 질문 해결에 필요하면 match 절 안에서 TypeQL 산술/비교 식을 사용할 수 있습니다.
5. 계산 결과를 반환해야 하면 최종적으로 조회 가능한 변수로 바인딩하세요.
6. query 본문에서 `owns`, `plays`, `relates`, 점 표기법(`$x.attr`)을 절대 사용하지 말고 반드시 `isa`, `has`, 관계 패턴만 사용하세요.
7. 문자열 값은 반드시 큰따옴표를 사용하세요.

스키마 핵심:
- 직급 필터 속성: `직급코드`
- 직위 필터 속성: `직위명`
- 평가 필터 속성: `평가등급`
- 개정이력 설명 속성: `개정이력설명`
- 국외본봉 금액 속성: `국외기본급액`

잘못된 예:
- `match $x owns 호봉번호 1;`
- `$보수기준.보수코드 = "3급";`
- `$h plays 호봉체계구성:소속직급 $g;`

올바른 예:
- `match $g isa 직급, has 직급코드 "4급"; (소속직급: $g, 구성호봉: $h) isa 호봉체계구성; $h has 호봉번호 $n;`
- `match $ev isa 평가결과, has 평가등급 "EX";`

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
    plan = _invoke_json(prompt)
    repaired = repair_typedb_plan(question, plan)
    repaired = dict(repaired)
    repaired["trace"] = trace_context
    maybe_write_query_trace(question, backend="typedb", trace_context=trace_context, plan=repaired)
    return repaired


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


def generate_answer(question: str, variables: List[Dict[str, Any]], rows: List[Dict[str, Any]], explanation: str = "") -> str:
    if not rows:
        return "조회 결과가 없습니다."

    explanation_note = f"\n조회 설명: {explanation}" if explanation else ""
    prompt = f"""다음 질문과 DB 조회 결과를 바탕으로 간결하게 답하세요.
계산이 필요하면 DB에서 조회한 숫자만 사용하여 정확하게 계산하세요. 절대 임의로 숫자를 만들지 마세요.

질문: {question}
변수 정의: {json.dumps(variables, ensure_ascii=False)}
조회 결과: {json.dumps(rows, ensure_ascii=False)}{explanation_note}
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
    explanation = plan.get("explanation", "")
    rows = execute_typeql(typeql, variables)
    rows, variables = _enrich_starting_step(rows, variables)
    return generate_answer(question, variables, rows, explanation)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "일반사무직원의 초봉은?"
    print(run(query))