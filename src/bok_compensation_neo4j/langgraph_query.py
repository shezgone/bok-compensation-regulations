import json
import os
import sys
from typing import TypedDict, List, Annotated, Dict, Any
import operator

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END, START

from bok_compensation_neo4j.config import Neo4jConfig
from bok_compensation_neo4j.connection import get_driver
from bok_compensation.llm import create_chat_model
from bok_compensation_neo4j.nl_query import run as graph_first_run
from bok_compensation.planner_utils import normalize_planner_outputs

# ====== 1. 환경 설정 ======
# 모델 두개 초기화 (JSON 출력이 필요한 노드와 일반 텍스트 노드)
llm_json = create_chat_model(temperature=0.0, json_output=True)
llm_text = create_chat_model(temperature=0.0)

# ====== Neo4j 유틸리티 ======
GRAPH_SCHEMA = """
[Neo4j 그래프 스키마]
노드: (:규정), (:조문), (:개정이력), (:직렬), (:직급), (:직위), (:호봉), (:수당), (:보수기준), (:직책급기준), (:상여금기준), (:연봉차등액기준), (:연봉상한액기준), (:임금피크제기준), (:국외본봉기준), (:초임호봉기준), (:평가결과)
관계: -[:규정구성]->, -[:규정개정]->, -[:직렬분류]->, -[:호봉체계구성]->, -[:해당직급]->, -[:해당직위]->, -[:해당직책구분]->, -[:해당등급]->, -[:대상직렬]->
"""

def fetch_rules() -> str:
    config = Neo4jConfig()
    driver = get_driver(config)
    rules = []
    try:
        with driver.session(database=config.database) as session:
            res = session.run("MATCH (n:조문) RETURN n.조번호 AS id, n.조문내용 AS text ORDER BY id")
            rules = [f"Rule {r['id']}: {r['text']}" for r in res]
    except Exception as e:
        print(f"Error fetching rules: {e}")
    finally:
        driver.close()
    return "\n".join(rules)

def execute_cypher(cypher_query: str) -> List[Dict]:
    config = Neo4jConfig()
    driver = get_driver(config)
    rows = []
    try:
        with driver.session(database=config.database) as session:
            result = session.run(cypher_query)
            rows = [record.data() for record in result]
    except Exception as e:
        raise e
    finally:
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
    사용자의 질문을 분석하여 조문 검색(Semantic)이 필요한 질문과 데이터/수치 조회(Data)가 필요한 질문으로 분리합니다.
    """
    print("\n[Planner Agent] 질문 의도 분석 및 하위 쿼리 계획 수립 중...")
    prompt = f"""당신은 질문 분석 에이전트입니다. 사용자의 질문을 분석하여, 
규정이나 조문에 대한 해석이 필요한 질문(semantic_queries)과 
금액, 수치 등 DB 조회를 통한 데이터가 필요한 질문(data_queries)으로 분리하세요.

[예시]
질문: "기한부 고용계약자가 상여금을 받을 수 있는지 조문에서 찾고, 1급 보직자의 직책급 월액은 얼마인지 계산해줘."
출력:
{{
  "semantic_queries": ["기한부 고용계약자가 상여금을 받을 수 있는가?"],
  "data_queries": ["1급 보직자의 직책급 월액은 얼마인가?"]
}}

반드시 위와 동일한 JSON 키 배열로만 응답하세요.

사용자 질문: "{state['query']}"
"""
    response = llm_json.invoke([HumanMessage(content=prompt)])
    try:
        plan = json.loads(response.content)
    except Exception as e:
        print(f"JSON Parsing Error in Planner: {e}")
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
    조문 파악이 필요한 질문에 대해 답을 생성합니다.
    """
    queries = state.get("semantic_queries", [])
    if not queries:
        return {"semantic_results": []}
    
    print(f"\n[Semantic Agent] 조문 데이터 검색 및 독해 중... (대기 검색: {len(queries)}건)")
    rules = fetch_rules()
    
    results = []
    for q in queries:
        prompt = f"""다음 한국은행 보수규정 조문을 읽고 질문에 답하세요.

[보수규정 조문 내용]
{rules}

질문: {q}

규정에 기반하여 명확하게 답변하세요.
답변:"""
        res = llm_text.invoke([HumanMessage(content=prompt)])
        results.append(f"Q: {q}\nA: {res.content}")
        print(f"  -> Semantic 답변 완료: '{q}'")
    
    return {"semantic_results": results}


def data_agent_node(state: AgentState):
    """
    [Agent 3: Data Agent]
    데이터 조회가 필요한 질문들에 대해 Cypher를 생성하고 실행합니다.
    """
    queries = state.get("data_queries", [])
    if not queries:
        return {"data_results": []}
    
    print(f"\n[Data Agent] Neo4j Cypher 쿼리 생성 및 실행 중... (대기 검색: {len(queries)}건)")
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
    에이전트 2,3의 답변을 취합하여 사용자의 최초 질문에 대한 최종 응답을 작성합니다.
    """
    print("\n[Summary Agent] 모든 에이전트의 결과를 취합하여 최종 답변 생성 중...")
    
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

작성된 글은 질문자에게 직접 설명하는 어투로 간결하면서도 정확하게 작성하세요.
최종 답변:"""
    
    res = llm_text.invoke([HumanMessage(content=prompt)])
    print("  -> 결과 요약 완료!")
    
    return {"final_answer": res.content}

# ====== 4. LangGraph 그래프 구성 ======

def create_langgraph():
    workflow = StateGraph(AgentState)

    # 4개의 노드(에이전트) 등록
    workflow.add_node("planner_agent", planner_node)
    workflow.add_node("semantic_agent", semantic_agent_node)
    workflow.add_node("data_agent", data_agent_node)
    workflow.add_node("summary_agent", summary_agent_node)

    # 워크플로우 엣지 설정: PLANNER가 작업을 나눈 후, SEMANTIC/DATA가 각각 병행 진행 -> SUMMARY로 취합
    workflow.add_edge(START, "planner_agent")
    
    # planner에서 semantic, data로 병렬로 이동
    workflow.add_edge("planner_agent", "semantic_agent")
    workflow.add_edge("planner_agent", "data_agent")
    
    # 각각 완료되면 summary에서 모음
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
    print(f"🚀 [LangGraph 4기통 Agent 시작]\n질의: {query}")
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
