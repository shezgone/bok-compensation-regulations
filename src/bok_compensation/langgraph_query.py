import json
import os
import sys
from typing import TypedDict, List, Annotated, Dict, Any
import operator

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END, START

from typedb.driver import TransactionType
from bok_compensation.config import TypeDBConfig
from bok_compensation.connection import get_driver
from bok_compensation.llm import create_chat_model
from bok_compensation.nl_query import run as graph_first_run
from bok_compensation.planner_utils import normalize_planner_outputs

# ====== 1. 환경 설정 ======
llm_json = create_chat_model(temperature=0.0, json_output=True)
llm_text = create_chat_model(temperature=0.0)

# ====== TypeDB 유틸리티 ======
try:
    SCHEMA_PATH = os.path.join(
        os.path.dirname(__file__), os.pardir, os.pardir,
        "schema", "compensation_regulation.tql"
    )
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        SCHEMA_TEXT = f.read()
except Exception:
    SCHEMA_TEXT = "TypeDB Schema"

def fetch_rules() -> str:
    """TypeDB에서 조문 정보를 가져옵니다."""
    config = TypeDBConfig()
    try:
        driver = get_driver(config)
    except Exception as e:
        print(f"Error connecting to TypeDB: {e}")
        return ""
        
    try:
        tx = driver.transaction(config.database, TransactionType.READ)
        result = tx.query("""
            match
                $article isa 조문, has 조번호 $id, has 조문내용 $text;
            sort $id;
        """).resolve()
        rules = []
        for row in result:
            rule_id = row.get("id").get_integer()
            rule_text = row.get("text").get_value()
            rules.append(f"Rule {rule_id}: {rule_text}")
        return "\n".join(rules)
    except Exception as e:
        print(f"Error fetching rules: {e}")
        return ""
    finally:
        tx.close()
        driver.close()

def execute_typeql(query: str, variables: list) -> list:
    """TypeDB에서 쿼리를 실행합니다."""
    config = TypeDBConfig()
    driver = get_driver(config)
    rows = []
    try:
        tx = driver.transaction(config.database, TransactionType.READ)
        result = tx.query(query).resolve()
        
        for row in result:
            record = {}
            for var in variables:
                name = var["name"]
                vtype = var.get("type", "string")
                concept = row.get(name)
                if concept is None:
                    record[name] = None
                    continue
                if vtype == "integer":
                    record[name] = concept.get_integer()
                elif vtype == "double":
                    record[name] = concept.get_double()
                elif vtype == "datetime":
                    raw = concept.get_value()
                    record[name] = str(raw)[:10] if raw else None
                else:
                    record[name] = concept.get_value()
            rows.append(record)
    except Exception as e:
        raise e
    finally:
        tx.close()
        driver.close()
    return rows

# ====== 2. 상태 (State) 정의 ======
class AgentState(TypedDict):
    query: str
    semantic_queries: List[str]
    data_queries: List[str]
    semantic_results: Annotated[List[str], operator.add]
    data_results: Annotated[List[str], operator.add]
    final_answer: str

# ====== 3. 에이전트 노드 구현 ======

def planner_node(state: AgentState):
    """
    [Agent 1: Planner]
    사용자 질문을 분석하여 조문 해석(Semantic)과 데이터/금액 조회(Data) 쿼리로 나눕니다.
    """
    print("\n[Planner Agent] 질문 의도 분석 및 하위 쿼리 계획 수립 중...")
    prompt = f"""당신은 분석 에이전트입니다. 
질문을 규정 해석(semantic_queries)과 금액/수치 조회(data_queries)로 분리하세요.

[예시]
질문: "기한부 고용계약자가 상여금을 받을 수 있는지 조문에서 찾고, 1급 보직자의 직책급 월액은 얼마인지 계산해줘."
출력:
{{
  "semantic_queries": ["기한부 고용계약자가 상여금을 받을 수 있는가?"],
  "data_queries": ["1급 보직자의 직책급 월액은 얼마인가?"]
}}

사용자 질문: "{state['query']}"
"""
    response = llm_json.invoke([HumanMessage(content=prompt)])
    try:
        plan = json.loads(response.content)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        plan = {"semantic_queries": [], "data_queries": [state["query"]]}
    
    normalized = normalize_planner_outputs(
        state["query"],
        plan.get("semantic_queries", []),
        plan.get("data_queries", []),
    )
    sq = normalized["semantic_queries"]
    dq = normalized["data_queries"]
    print(f"  -> 계획 수립 완료:\n     * Semantic 질문: {sq}\n     * Data 질문: {dq}")
    return {"semantic_queries": sq, "data_queries": dq}

def semantic_agent_node(state: AgentState):
    """
    [Agent 2: Semantic Agent]
    조문 파악 질문에 대해 TypeDB에서 조회한 규정을 읽고 답합니다.
    """
    queries = state.get("semantic_queries", [])
    if not queries:
        return {"semantic_results": []}
    
    print(f"\n[Semantic Agent] 조문 데이터 검색 및 독해 중... (대기 쿼리: {len(queries)}건)")
    rules = fetch_rules()
    
    results = []
    for q in queries:
        prompt = f"""다음 한국은행 보수규정 조문을 읽고 질문에 명확히 답하세요.

[보수규정 조문 내용]
{rules}

질문: {q}
답변:"""
        res = llm_text.invoke([HumanMessage(content=prompt)])
        results.append(f"Q: {q}\nA: {res.content}")
        print(f"  -> Semantic 답변 완료: '{q}'")
    
    return {"semantic_results": results}

def data_agent_node(state: AgentState):
    """
    [Agent 3: Data Agent]
    데이터 조회가 필요한 질문에 대해 TypeQL을 생성하고 TypeDB에서 실행합니다.
    """
    queries = state.get("data_queries", [])
    if not queries:
        return {"data_results": []}
    
    print(f"\n[Data Agent] TypeDB TypeQL 쿼리 생성 및 실행 중... (대기 쿼리: {len(queries)}건)")
    results = []
    
    for q in queries:
        try:
            answer = graph_first_run(q)
            results.append(f"Q: {q}\nGraph-first 답변: {answer}")
            print("  -> Data 조회 완료: graph-first 파이프라인 응답 리턴")
        except Exception as e:
            err_msg = f"Q: {q}\n조회 실패: graph-first 파이프라인 에러 ({str(e)})"
            results.append(err_msg)
            print(f"  -> 에러: {e}")

    return {"data_results": results}

def summary_agent_node(state: AgentState):
    """
    [Agent 4: Summary Agent]
    에이전트 2,3의 답변을 취합합니다.
    """
    print("\n[Summary Agent] 합산 및 최종 답변 생성 중...")
    
    semantic_info = "\n\n".join(state.get("semantic_results", []))
    data_info = "\n\n".join(state.get("data_results", []))
    
    prompt = f"""당신은 한국은행 보수규정에 대해 완벽하게 답변하는 AI 어시스턴트입니다.
사용자의 원래 질문에 대해 각 하위 에이전트들이 도출한 분석결과를 참고하여, 
자연스럽고 완벽하게 연결된 하나의 통합된 최종 답변을 작성하세요.

사용자의 원래 질문: "{state['query']}"

[참고할 조문 분석결과 (Semantic Agent)]
{semantic_info if semantic_info else '(필요하지 않음)'}

[참고할 직책/수치 분석결과 (Data Agent)]
{data_info if data_info else '(필요하지 않음)'}

최종 답변:"""
    
    res = llm_text.invoke([HumanMessage(content=prompt)])
    print("  -> 결과 요약 완료!")
    return {"final_answer": res.content}

# ====== 4. LangGraph 그래프 구성 ======
def create_langgraph():
    workflow = StateGraph(AgentState)
    workflow.add_node("planner_agent", planner_node)
    workflow.add_node("semantic_agent", semantic_agent_node)
    workflow.add_node("data_agent", data_agent_node)
    workflow.add_node("summary_agent", summary_agent_node)

    workflow.add_edge(START, "planner_agent")
    workflow.add_edge("planner_agent", "semantic_agent")
    workflow.add_edge("planner_agent", "data_agent")
    workflow.add_edge("semantic_agent", "summary_agent")
    workflow.add_edge("data_agent", "summary_agent")
    workflow.add_edge("summary_agent", END)

    return workflow.compile()


def run(query: str) -> str:
    app = create_langgraph()
    final_state = app.invoke({
        "query": query,
        "semantic_queries": [],
        "data_queries": [],
        "semantic_results": [],
        "data_results": [],
    })
    return final_state["final_answer"]

# ====== 5. 실행 엔트리포인트 ======
def run_langgraph(query: str):
    print("=" * 70)
    print(f"🚀 [LangGraph TypeDB Multi-Agent 시작]\n질의: {query}")
    print("=" * 70)
    final_answer = run(query)
    
    print("\n" + "=" * 70)
    print("✅ [최종 응답 (Summary Agent)]")
    print("=" * 70)
    print(final_answer)
    print("=" * 70)

if __name__ == "__main__":
    test_query = "기한부 고용계약자가 상여금을 받을 수 있는지 조문에서 찾고, 1급 보직자의 직책급 월액은 얼마인지 계산해줘."
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    run_langgraph(test_query)
