"""하이브리드 라우터 그래프 — TypeDB/Neo4j/Context 자동 선택.

현재는 시뮬레이션이며, 실제 구현은 각 백엔드의 agent.py에 있음.
이 파일은 향후 단일 엔트리포인트로 질문을 받아 최적 백엔드를 자동 선택하는 라우터 역할을 할 예정.

참고: 각 백엔드 agent.py는 이미 다음 구조를 사용함:
- 커스텀 StateGraph (create_react_agent 대신)
- 엔티티 추출 → 병렬(규정 검색 + DB 조회) → 추론 → 검증 → 확정
- Qwen 쿼리 에러 시 구조화된 힌트 + 재시도
- 검증 실패 시 최대 2회 재추론
"""

from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END


class HybridAgentState(TypedDict):
    question: str
    current_date_context: str
    retrieved_rules: List[Dict]
    graph_base_values: Dict[str, Any]
    draft_answer: str
    reflection_feedback: str
    final_answer: str
    iteration_count: int


def retrieve_rules_node(state: HybridAgentState):
    question = state["question"]
    print("[Node: Retrieve Rules] 질문 시점 분석 및 관련 조문/부칙/총재의결사항 검색 중...")
    # TODO: 실제 규정 검색 연결 — context_query.select_relevant_rules() 사용
    simulated_rules = [
        {"type": "본문", "content": "1급 징계 시 3개월간 보수 20% 감액", "priority": 1},
        {"type": "총재의결사항", "effective": "2024-01-01", "content": "2024년부로 1급 징계 직책급 전액 미지급", "priority": 99}
    ]
    return {"retrieved_rules": simulated_rules, "iteration_count": state.get("iteration_count", 0)}


def fetch_graph_node(state: HybridAgentState):
    print("[Node: Fetch Graph Data] 베이스 수치를 그래프(Neo4j/TypeDB)에서 추출 중...")
    # TODO: 실제 DB 연결 — execute_typeql/execute_cypher 사용
    simulated_graph_data = {
        "1급_직책급_기준액": 2832000
    }
    return {"graph_base_values": simulated_graph_data}


def draft_synthesis_node(state: HybridAgentState):
    print("[Node: Draft Synthesis] 룰(Context)과 수치(Graph)를 결합하여 초안 연산 중...")
    if state["iteration_count"] == 0:
         draft = "1급 직책급은 2,832,000원입니다. 본문 규정에 따라 20%를 감액하여 2,265,600원이 지급됩니다."
    else:
         draft = "총재의결사항에 따라 2024년부터 전액 미지급되므로, 1급 직책급 기준 2,832,000원에서 100% 감액된 0원이 지급됩니다."
    return {"draft_answer": draft}


def reflection_node(state: HybridAgentState):
    print("[Node: Reflection] 룰 우선순위와 시점이 초안에 잘 반영되었는지 회고 중...")
    draft = state["draft_answer"]

    if "총재의결사항" not in draft and state["iteration_count"] == 0:
        feedback = "비판: 초안이 본문(우선순위 1)만 적용하고 총재의결사항(우선순위 99, 100% 감액)을 누락했습니다. 다시 계산하세요."
    else:
        feedback = "검증 완료: 최고 우선순위 규정에 맞게 수치가 잘 오버라이드 되었습니다."

    return {
        "reflection_feedback": feedback,
        "iteration_count": state["iteration_count"] + 1
    }


def route_after_reflection(state: HybridAgentState):
    if "검증 완료" in state.get("reflection_feedback", "") or state["iteration_count"] >= 3:
        return "finalize"
    return "revise_draft"


def finalize_metadata_node(state: HybridAgentState):
    print("[Node: Finalize] 최종 답변 승인 완료.")
    return {"final_answer": state["draft_answer"]}


workflow = StateGraph(HybridAgentState)
workflow.add_node("retrieve_rules", retrieve_rules_node)
workflow.add_node("fetch_graph", fetch_graph_node)
workflow.add_node("draft_synthesis", draft_synthesis_node)
workflow.add_node("reflection", reflection_node)
workflow.add_node("finalize", finalize_metadata_node)

workflow.set_entry_point("retrieve_rules")
workflow.add_edge("retrieve_rules", "fetch_graph")
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
