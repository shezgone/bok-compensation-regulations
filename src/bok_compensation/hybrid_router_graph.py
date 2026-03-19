import operator
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
# LLM 및 기존 모듈 임포트는 실제 환경에 맞게 조정 (예: ChatOpenAI 등)

# 1. State 정의: 규정, 수치, 회고 상태를 개별적으로 관리
class HybridAgentState(TypedDict):
    question: str
    current_date_context: str            # 질문의 시점 (예: 2024년 기준)
    retrieved_rules: List[Dict]          # 텍스트 DB에서 가져온 조문/부칙/의결사항 (우선순위 포함)
    graph_base_values: Dict[str, Any]    # 그래프 DB에서 가져온 기준표 수치 (팩트)
    draft_answer: str                    # 연산 초안
    reflection_feedback: str             # 리플렉션(회고) 결과
    final_answer: str                    # 최종 답변
    iteration_count: int                 # 회고 반복 횟수

# 2. Node: 텍스트 규정 검색 (우선순위/시점 오버라이드 룰 확보)
def retrieve_rules_node(state: HybridAgentState):
    question = state["question"]
    print("[Node: Retrieve Rules] 질문 시점 분석 및 관련 조문/부칙/총재의결사항 검색 중...")
    # TODO: Vector DB 또는 BM25를 통해 시점별 오버라이드 텍스트 검색 로직 연결
    simulated_rules = [
        {"type": "본문", "content": "1급 징계 시 3개월간 보수 20% 감액", "priority": 1},
        {"type": "총재의결사항", "effective": "2024-01-01", "content": "2024년부로 1급 징계 직책급 전액 미지급", "priority": 99}
    ]
    return {"retrieved_rules": simulated_rules, "iteration_count": state.get("iteration_count", 0)}

# 3. Node: 그래프 DB 조회 (순수 기준 수치만 추출)
def fetch_graph_node(state: HybridAgentState):
    print("[Node: Fetch Graph Data] 베이스 수치를 그래프(Neo4j/TypeDB)에서 추출 중...")
    # TODO: Entity를 판별하여 Neo4j/TypeDB에 Cypher/TypeQL 쿼리 실행
    simulated_graph_data = {
        "1급_직책급_기준액": 2832000
    }
    return {"graph_base_values": simulated_graph_data}

# 4. Node: 룰과 그래프 결합 및 초안 생성 (Synthesis)
def draft_synthesis_node(state: HybridAgentState):
    print("[Node: Draft Synthesis] 룰(Context)과 수치(Graph)를 결합하여 초안 연산 중...")
    # LLM이 rules와 graph_base_values를 보고 답변 초안 생성
    # 실제로는 LLM 호출: llm.invoke(...)
    
    # 의도적으로 오버라이드를 놓친 바보같은 초안(ReAct 테스트용)
    if state["iteration_count"] == 0:
         draft = "1급 직책급은 2,832,000원입니다. 본문 규정에 따라 20%를 감액하여 2,265,600원이 지급됩니다."
    else:
         draft = "총재의결사항에 따라 2024년부터 전액 미지급되므로, 1급 직책급 기준 2,832,000원에서 100% 감액된 0원이 지급됩니다."
         
    return {"draft_answer": draft}

# 5. Node: 리플렉션 (오버라이드 적용 여부, 계산 검증)
def reflection_node(state: HybridAgentState):
    print("[Node: Reflection] 룰 우선순위와 시점이 초안에 잘 반영되었는지 회고 중...")
    rules = state["retrieved_rules"]
    draft = state["draft_answer"]
    
    # LLM이 초안을 비판하게 함
    is_valid = False
    feedback = ""
    
    if "총재의결사항" not in draft and state["iteration_count"] == 0:
        feedback = "비판: 초안이 본문(우선순위 1)만 적용하고 총재의결사항(우선순위 99, 100% 감액)을 누락했습니다. 다시 계산하세요."
    else:
        is_valid = True
        feedback = "검증 완료: 최고 우선순위 규정에 맞게 수치가 잘 오버라이드 되었습니다."
        
    return {
        "reflection_feedback": feedback,
        "iteration_count": state["iteration_count"] + 1
    }

# 6. Edge: 조건부 라우팅 (검증 통과 시 종료, 실패 시 다시 초안 생성)
def route_after_reflection(state: HybridAgentState):
    if "검증 완료" in state.get("reflection_feedback", "") or state["iteration_count"] >= 3:
        return "finalize"
    return "revise_draft"

# 7. Node: 최종 답변 노드
def finalize_metadata_node(state: HybridAgentState):
    print("[Node: Finalize] 최종 답변 승인 완료.")
    return {"final_answer": state["draft_answer"]}

# 8. LangGraph 파이프라인 조립
workflow = StateGraph(HybridAgentState)
workflow.add_node("retrieve_rules", retrieve_rules_node)
workflow.add_node("fetch_graph", fetch_graph_node)
workflow.add_node("draft_synthesis", draft_synthesis_node)
workflow.add_node("reflection", reflection_node)
workflow.add_node("finalize", finalize_metadata_node)

# Flow 연결
workflow.set_entry_point("retrieve_rules")
workflow.add_edge("retrieve_rules", "fetch_graph")  # 병렬 처리로 변경 가능
workflow.add_edge("fetch_graph", "draft_synthesis")
workflow.add_edge("draft_synthesis", "reflection")
workflow.add_conditional_edges(
    "reflection",
    route_after_reflection,
    {
        "revise_draft": "draft_synthesis",
        "finalize": "finalize"
    }
)
workflow.add_edge("finalize", END)

hybrid_app = workflow.compile()

if __name__ == "__main__":
    print("=== 하이브리드 RAG (Temporal-Aware) 시뮬레이션 ===")
    initial_state = {
        "question": "2024년 기준, 징계를 받은 1급 직원의 첫 달 직책급은 얼마입니까?",
        "iteration_count": 0
    }
    
    for output in hybrid_app.stream(initial_state):
        print("---")
        for key, value in output.items():
            print(f"[{key}] 완료")
            if "draft_answer" in value:
                print(f" └ 초안: {value['draft_answer']}")
            if "reflection_feedback" in value:
                print(f" └ 피드백: {value['reflection_feedback']}")
    
    print("========================================")
    final_state = hybrid_app.get_state(hybrid_app.get_graph().nodes).values
    # Note: langgraph version에 따라 state 출력 방식 상이할 수 있음
