"""한국은행 보수규정 Graph RAG 데모 — Streamlit 앱."""

import os
import sys
import time
import traceback
import json

import streamlit as st
from dotenv import load_dotenv
load_dotenv()


# src 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


# ---------------------------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="보수규정 Graph RAG 데모",
    page_icon="🏛️",
    layout="wide",
)

st.title("🏛️ 한국은행 보수규정 — 4-Way 아키텍처 비교 데모")
st.caption("TypeDB KG RAG · Neo4j Graph RAG · Context RAG · Base LLM")

if "question_input" not in st.session_state:
    st.session_state["question_input"] = ""

# ---------------------------------------------------------------------------
# 아키텍처별 실행 함수 (lazy import — 연결 실패 시 graceful)
# ---------------------------------------------------------------------------

def _run_typedb(question: str) -> str:
    from bok_compensation.nl_query import run_with_trace as typedb_run_with_trace

    return typedb_run_with_trace(question)


def _run_neo4j(question: str) -> str:
    from bok_compensation_neo4j.nl_query import run_with_trace as neo4j_run_with_trace

    return neo4j_run_with_trace(question)


def _run_context_rag(question: str) -> str:
    from bok_compensation_context.context_query import run_with_trace as context_run_with_trace

    return context_run_with_trace(question)


def _run_base_llm(question: str) -> str:
    from langchain_core.messages import HumanMessage
    from bok_compensation.llm import create_chat_model

    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=question)])
    return {
        "answer": response.content,
        "trace": {
            "question": question,
            "mode": "direct_llm",
        },
    }


def _render_trace(trace: dict) -> None:
    entities = trace.get("entities")
    if entities is not None:
        st.markdown("**추출 엔티티**")
        st.code(json.dumps(entities, ensure_ascii=False, indent=2), language="json")

    selected_sections = trace.get("selected_sections")
    if selected_sections is not None:
        st.markdown("**선택 섹션**")
        st.write(", ".join(selected_sections) if selected_sections else "없음")

    section_count = trace.get("section_count")
    if section_count is not None:
        st.caption(f"선택 섹션 수: {section_count}")

    rules_context = trace.get("rules_context")
    if rules_context is not None:
        st.markdown("**규정 컨텍스트**")
        st.code(rules_context or "없음", language="text")

    graph_context = trace.get("graph_context")
    if graph_context is not None:
        st.markdown("**그래프 컨텍스트**")
        st.code(graph_context or "없음", language="text")

    context_excerpt = trace.get("context_excerpt")
    if context_excerpt is not None:
        st.markdown("**문서 컨텍스트**")
        st.code(context_excerpt or "없음", language="markdown")

    mode = trace.get("mode")
    if mode is not None:
        st.markdown("**실행 모드**")
        st.write(mode)


ARCHITECTURES = {
    "TypeDB KG RAG": {"fn": _run_typedb, "icon": "🚀", "color": "#2196F3"},
    "Neo4j Graph RAG": {"fn": _run_neo4j, "icon": "🕸️", "color": "#4CAF50"},
    "Context RAG": {"fn": _run_context_rag, "icon": "📄", "color": "#FF9800"},
    "Base LLM": {"fn": _run_base_llm, "icon": "🏛️", "color": "#9C27B0"},
}

# ---------------------------------------------------------------------------
# 예시 질문
# ---------------------------------------------------------------------------
EXAMPLE_QUESTIONS = [
    {
        "id": "Q1",
        "label": "단일 조회 — 연봉제 본봉 산정",
        "question": (
            "3급 G3 종합기획직원 A가 다음 조건을 모두 충족할 때, "
            "2025년 5월 1일 기준으로 적용되는 연봉제 본봉을 산정하시오.\n"
            "조건:\n"
            "1. 2024년 12월 31일 기준 직전 연봉제 본봉: 60,000,000원\n"
            "2. 2024년도 성과평가 등급: 'EX'"
        ),
        "answer": "63,024,000원 (= 60,000,000 + 3,024,000)",
    },
    {
        "id": "Q2",
        "label": "다중 관계 조인 — 직책급·차등액·상한액",
        "question": "3급 팀장이며 성과평가 EX 등급인 직원의 직책급, 연봉차등액, 연봉상한액을 모두 조회하시오.",
        "answer": "직책급 1,956,000원, 차등액 3,024,000원, 상한액 77,724,000원",
    },
    {
        "id": "Q3",
        "label": "범위 필터 — 차등액 ≥ 200만원",
        "question": "연봉차등액이 200만원 이상인 직급과 평가등급 조합을 모두 나열하시오.",
        "answer": "1급EX(3,672,000), 1급EE(2,448,000), 2급EX(3,348,000), 2급EE(2,232,000), 3급EX(3,024,000), 3급EE(2,016,000) — 6건",
    },
]


# ---------------------------------------------------------------------------
# 사이드바: 아키텍처 선택 & 예시 질문
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 설정")

    st.subheader("아키텍처 선택")
    selected_archs = []
    for arch_name, arch_info in ARCHITECTURES.items():
        if st.checkbox(
            f"{arch_info['icon']} {arch_name}",
            value=(arch_name != "Base LLM"),
            key=f"arch_{arch_name}",
        ):
            selected_archs.append(arch_name)

    st.divider()
    st.subheader("📋 예시 질문")
    for eq in EXAMPLE_QUESTIONS:
        if st.button(f"[{eq['id']}] {eq['label']}", key=eq["id"], use_container_width=True):
            st.session_state["question_input"] = eq["question"]

    st.divider()
    st.caption("한국은행 보수규정 Graph RAG PoC\n\nTypeDB 3.x · Neo4j 5.x · LangChain")


# ---------------------------------------------------------------------------
# 메인 영역: 질문 입력
# ---------------------------------------------------------------------------
question = st.text_area(
    "💬 질문을 입력하세요",
    height=120,
    placeholder="예: 3급 팀장이며 성과평가 EX 등급인 직원의 직책급을 조회하시오.",
    key="question_input",
)

# 예시 질문의 정답 표시: 현재 질문이 예시와 정확히 일치할 때만 노출
expected = next(
    (example["answer"] for example in EXAMPLE_QUESTIONS if example["question"] == question),
    "",
)
if expected:
    st.info(f"📌 **기대 정답:** {expected}")

col_run, col_clear = st.columns([1, 5])
with col_run:
    run_clicked = st.button("🔍 실행", type="primary", use_container_width=True)
with col_clear:
    if st.button("🗑️ 초기화"):
        st.session_state["question_input"] = ""
        st.session_state.pop("results", None)
        st.rerun()




# ---------------------------------------------------------------------------
# 실행 & 결과 표시
# ---------------------------------------------------------------------------
if run_clicked and question.strip():
    if not selected_archs:
        st.warning("왼쪽 사이드바에서 최소 1개 아키텍처를 선택하세요.")
    else:
        results = {}
        progress = st.progress(0, text="실행 준비 중...")

        for idx, arch_name in enumerate(selected_archs):
            arch_info = ARCHITECTURES[arch_name]
            progress.progress(
                (idx) / len(selected_archs),
                text=f"{arch_info['icon']} {arch_name} 실행 중...",
            )

            start = time.time()
            try:
                response = arch_info["fn"](question.strip())
                elapsed = time.time() - start
                results[arch_name] = {
                    "answer": response["answer"],
                    "trace": response.get("trace") or {},
                    "elapsed": elapsed,
                    "error": None,
                }
            except Exception as e:
                elapsed = time.time() - start
                results[arch_name] = {
                    "answer": None,
                    "trace": None,
                    "elapsed": elapsed,
                    "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                }

        progress.progress(1.0, text="완료!")
        time.sleep(0.3)
        progress.empty()

        st.session_state["results"] = results

# ---------------------------------------------------------------------------
# 결과 렌더링
# ---------------------------------------------------------------------------
if st.session_state.get("results"):
    results = st.session_state["results"]

    st.divider()
    st.subheader("📊 결과 비교")

    # 카드형 레이아웃
    cols = st.columns(len(results))
    for col, (arch_name, result) in zip(cols, results.items()):
        arch_info = ARCHITECTURES[arch_name]
        with col:
            st.markdown(f"### {arch_info['icon']} {arch_name}")
            st.caption(f"⏱️ {result['elapsed']:.1f}초")

            if result["error"]:
                st.error("실행 오류")
                with st.expander("오류 상세"):
                    st.code(result["error"], language="text")
            else:
                st.success("실행 완료")
                st.markdown(result["answer"])
                with st.expander("Trace"):
                    _render_trace(result.get("trace") or {})
