import os
import json
import logging
from typing import TypedDict, Annotated, Sequence, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from neo4j import GraphDatabase

from src.bok_compensation_neo4j.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

QWEN_SCHEMA_PROMPT = """당신은 한국은행 보수규정 전문 Neo4j Cypher 쿼리 에이전트(Qwen)입니다.
Neo4j 데이터베이스에서 기준표(수치, 금액, 한도 등)를 조회하는 역할만 담당합니다.
사용자의 질문(예: "3급 팀장 직책급액은?")을 분석하여 `execute_cypher` 도구를 호출하고 결과를 반환하세요.

[Neo4j 스키마 지식]
Nodes:
- JobGrade {name: string}
- EvaluationGrade {name: string}
- BaseSalary {amount: integer, step: integer}
- SalaryLimit {amount: integer}
- DutyAllowance {amount: integer, name: string}
- DifferentialAmount {amount: integer}

Relationships:
- (JobGrade)-[:HAS_BASE_SALARY]->(BaseSalary)
- (JobGrade)-[:HAS_SALARY_LIMIT]->(SalaryLimit)
- (JobGrade)-[:HAS_DUTY_ALLOWANCE]->(DutyAllowance)
- (EvaluationGrade)-[:HAS_DIFFERENTIAL_AMOUNT {for_grade: string}]->(DifferentialAmount)

<정상 예시 모음>
- 차등액 조회:
  `MATCH (e:EvaluationGrade {name: 'EX'})-[:HAS_DIFFERENTIAL_AMOUNT {for_grade: '3급'}]->(d:DifferentialAmount) RETURN d.amount as amount`
"""

HCX_SYSTEM_PROMPT = """당신은 한국은행 보수규정 전문 [하이브리드 RAG 에이전트(Hybrid Reasoning Agent)] (HCX) 입니다.
당신은 두 가지 강력한 도구를 적절히 분업하여 복합적인 계산과 논리적 추론을 수행해야 합니다.

[사용 가능 도구 - 분업 체계]
1. `ask_db_expert`: 기본급, 직책급, 연봉차등액, 연봉상한액, 호봉 등 수치 팩트가 필요할 때 데이터베이스 전문 하위 에이전트(Qwen)에게 자연어로 질문을 던져 수치를 가져옵니다.
2. `search_regulations`: 수치가 아니라 "결근 감액 방식, 징계, 임금피크 지급률, 적용 기준일" 등 계산 공식과 텍스트 규정이 필요할 때 텍스트에서 검색합니다.

[**필수 행동 지침 - 엄격히 준수할 것**]
1. 수식을 모를 경우 절대 임의로 식을 만들어내지 말고 무조건 `search_regulations` 도구를 제일 먼저 호출하세요.
2. 기준이 되는 기본 수치(예: XX급 직책급 등)가 필요하면 반드시 `ask_db_expert` 도구를 호출하여 정확한 숫자를 가져오세요.
3. [초강력 경고] 연봉이나 총보수를 계산하라는 질문에 "기본급" 금액 정보가 없다면, 절대로 연봉이라고 답변하지 마세요. (계산 불가 명시)
"""

@tool
def execute_cypher(query: str) -> str:
    """Neo4j Cypher 쿼리를 실행하여 결과를 반환합니다."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        def serialize_record(record):
            res = {}
            for k, v in record.items():
                if hasattr(v, "labels") and hasattr(v, "items"):
                    res[k] = {"labels": list(v.labels), "properties": dict(v.items())}
                elif hasattr(v, "type") and hasattr(v, "items"):
                    res[k] = {"type": v.type, "properties": dict(v.items())}
                else: res[k] = v
            return res

        with driver.session() as session:
            result = session.run(query)
            records = [serialize_record(record) for record in result]
            driver.close()
            if not records: return "Query executed successfully but returned no results."
            return json.dumps(records, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"Cypher Error: {str(e)}\nQuery: {query}")
        return f"Error executing Cypher query: {str(e)}"

@tool
def ask_db_expert(question: str) -> str:
    """Neo4j 데이터베이스 조회가 필요할 때 사용하는 도구입니다. Cypher 전문가인 하위 에이전트(Qwen)에게 자연어로 질문합니다."""
    from src.bok_compensation_typedb.llm import create_chat_model
    qwen_llm = create_chat_model(temperature=0)
    qwen_agent = create_react_agent(qwen_llm, [execute_cypher], prompt=QWEN_SCHEMA_PROMPT)
    res = qwen_agent.invoke({"messages": [HumanMessage(content=question)]})
    
    # 하위 에이전트의 도구 호출(Cypher) 내역을 텍스트로 함께 반환
    query_traces = []
    for msg in res["messages"]:
        if getattr(msg, "tool_calls", None):
            for tcall in msg.tool_calls:
                if tcall.get("name") == "execute_cypher":
                    query_traces.append(f"Sub-Query: {tcall.get('args', {}).get('query', '')}")
                    
    ans = res["messages"][-1].content
    if query_traces:
        return f"{ans}\n\n[내부 쿼리 실행 내역]\n" + "\n".join(query_traces)
    return ans

@tool
def search_regulations(keyword: str) -> str:
    """텍스트 문서에서 징계 감액률, 기준일 등 본문 문맥(Context)을 검색합니다."""
    from src.bok_compensation_context.context_query import select_relevant_sections
    try:
        sections = select_relevant_sections(keyword, top_k=3)
        if not sections: return "일치하는 본문 결과가 없습니다."
        return "\n\n".join([sec["content"] for sec in sections])
    except Exception as e: return f"Error: {str(e)}"

def build_neo4j_agent() -> Any:
    hcx_llm = ChatOpenAI(
        base_url="http://211.188.81.250:30402/v1",
        model="HCX-GOV-THINK-V1-32B",
        api_key="sk-dummy",
        temperature=0,
        max_tokens=2048,
    )
    tools = [ask_db_expert, search_regulations]
    return create_react_agent(hcx_llm, tools, prompt=HCX_SYSTEM_PROMPT)

def run_query(question: str):
    agent = build_neo4j_agent()
    trace_calls = [{"module": "System", "function": "Start", "arguments": {"mode": "LangGraph Hybrid Neo4j (HCX MoE)"}, "result": "검색 루프 시작"}]
    
    try:
        result = agent.invoke({"messages": [HumanMessage(content=question)]})
        final_answer = result["messages"][-1].content
        
        for msg in result["messages"]:
            if getattr(msg, "tool_calls", None):
                for tcall in msg.tool_calls:
                    trace_calls.append({
                        "module": "Agent",
                        "function": f"Call_Tool_{tcall.get('name')}",
                        "arguments": tcall.get("args"),
                        "result": "요청중"
                    })
            elif getattr(msg, "type", "") == "tool":
                snippet = str(msg.content)
                if len(snippet) > 500: snippet = snippet[:500] + "..."
                trace_calls.append({
                    "module": "Tool Response",
                    "function": msg.name,
                    "arguments": {},
                    "result": snippet
                })
        trace_calls.append({"module": "Agent", "function": "End", "arguments": {}, "result": "최종 답변 완료"})
        return {"answer": final_answer, "trace_logs": trace_calls}
    except Exception as e:
        trace_calls.append({"module": "Agent", "function": "Error", "arguments": {"error": str(e)}, "result": "오류"})
        return {"answer": f"시스템 오류 발생: {str(e)}", "trace_logs": trace_calls}
