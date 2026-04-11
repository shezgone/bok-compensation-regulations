"""한국은행 보수규정 Graph RAG 데모 — Streamlit 앱."""

import os
import sys
import time
import traceback
import json
import re
from textwrap import dedent
from typing import List, Optional, Tuple

import streamlit as st
from dotenv import load_dotenv
load_dotenv()


# src 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


# ---------------------------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------------------------
def _get_role_summary(func_name: str, module: str) -> str:
    summary_map = {
        "extract_entities": "질문에서 주요 개체(직급, 평가점수 등) 및 의도(Intent) 추출",
        "_determine_hop_depth": "그래프 탐색 깊이 판단",
        "fetch_subgraph_typedb": "TypeDB 지식 그래프에서 조건에 맞는 서브그래프(조견표 연결망) 도출",
        "fetch_relevant_rules": "Vector DB/Context에서 관련된 원문 규정 조항 텍스트를 검색",
        "try_execute_regulation": "파이썬으로 구현된 Rule-Engine을 통해 하드코딩된 급여 계산 실행",
        "generate_answer": "검색/계산된 최종 데이터를 종합하여 자연어 답변 생성",
        "run_query": "에이전트 판단 루프 시작 (데이터 추론)",
        "execute_cypher": "Agent가 동적 생성한 Graph Query로 Neo4j에서 HR 규칙/값 직접 조회 연산",
        "route_with_context": "조회 모드 분기 (내용 질의 vs 수치 계산)",
        "build_answer_with_context": "원문 컨텍스트 텍스트만 사용하여 순수 LLM 답변 예측"
    }
    for k, v in summary_map.items():
        if k in func_name:
            return v
    if "Agent" in module or "agent" in module:
        return "자율적 판단 에이전트 구동"
    return "기본 파이프라인 함수 실행"

def _render_execution_chain(trace: dict) -> None:
    calls = trace.get("function_calls", [])
    if not calls:
        if trace.get("mode") == "direct_llm":
            st.markdown(
                '<div class="chain-step" data-step="1">'
                '<div class="step-title">base_llm.invoke(질문)</div>'
                '<div class="step-role">사전학습 지식으로만 응답 생성</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            return
        st.caption("실행 체인 정보가 없습니다.")
        return

    for i, call in enumerate(calls):
        mod = call.get("module", "unknown").split("/")[-1].replace(".py", "")
        func = call.get("function", "unknown")
        args = call.get("arguments", {})
        result = call.get("result", "완료")

        args_dict = dict(args) if isinstance(args, dict) else args
        query_str = None
        if isinstance(args_dict, dict) and "query" in args_dict:
            query_str = args_dict.pop("query")

        args_str = str(args_dict)[:500] + ("..." if len(str(args_dict)) > 500 else "")
        res_str = str(result)[:500] + ("..." if len(str(result)) > 500 else "")

        # Qwen(Sub-Agent)이 반환한 텍스트 안에 쿼리가 포함되어 있다면 파싱해서 보여줌
        if "[내부 쿼리 실행 내역]" in res_str and "Sub-Query:" in res_str:
            parts = res_str.split("[내부 쿼리 실행 내역]")
            res_str = parts[0].strip()
            sub_query = parts[1].replace("Sub-Query:", "").strip()
            if not query_str:
                query_str = sub_query

        summary = _get_role_summary(func, mod)

        st.markdown(
            f'<div class="chain-step" data-step="{i+1}">'
            f'<div class="step-title">{mod}.{func}()</div>'
            f'<div class="step-role">{summary}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        with st.expander(f"Step {i+1} 상세", expanded=False):
            st.markdown("**입력 (Input)**")
            st.code(args_str, language="json")
            if query_str:
                st.markdown("**쿼리 (Query)**")
                st.code(str(query_str), language="sql")
            st.markdown("**출력 (Output)**")
            st.code(res_str, language="json")

        if i < len(calls) - 1:
            st.markdown('<div class="chain-connector">↓</div>', unsafe_allow_html=True)


st.set_page_config(
    page_title="보수규정 Graph RAG 데모",
    page_icon="🏛️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# 커스텀 CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ── 전역 ── */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body,
.stMarkdown, .stText, .stCaption,
p, h1, h2, h3, h4, h5, h6, li, td, th, label, span:not([class*="icon"]):not([data-testid]) {
    font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
}
code, pre {
    font-family: 'JetBrains Mono', 'Menlo', monospace !important;
}

/* ── 헤더 ── */
.main-header {
    background: #363636;
    border: 1px solid #444444;
    color: #e2e8f0;
    padding: 1.5rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
}
.main-header h1 {
    margin: 0 0 0.25rem 0;
    font-size: 1.5rem;
    font-weight: 700;
    color: #a5f3fc;
    letter-spacing: -0.02em;
}
.main-header p {
    margin: 0;
    color: #94a3b8;
    font-size: 0.88rem;
}

/* ── 결과 카드: Streamlit native 사용, 색상 바만 HTML ── */
.arch-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.7rem;
    border-radius: 6px;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}
.arch-badge.typedb  { background: #1e3a5a; color: #93c5fd; }
.arch-badge.neo4j   { background: #14532d; color: #86efac; }
.arch-badge.context { background: #431407; color: #fdba74; }
.arch-badge.basellm { background: #3b0764; color: #d8b4fe; }

.arch-time {
    font-size: 0.78rem;
    color: #64748b;
    background: #3a3a3a;
    padding: 0.15rem 0.5rem;
    border-radius: 999px;
    font-weight: 500;
    margin-left: 0.5rem;
}

/* ── 실행 체인 스텝 ── */
.chain-step {
    position: relative;
    padding: 0.6rem 0.8rem 0.6rem 2.2rem;
    margin: 0.4rem 0;
    background: #363636;
    border-radius: 8px;
    border: 1px solid #444444;
    font-size: 0.85rem;
}
.chain-step::before {
    content: attr(data-step);
    position: absolute;
    left: 0.55rem;
    top: 0.6rem;
    width: 1.3rem;
    height: 1.3rem;
    border-radius: 50%;
    background: #7c3aed;
    color: white;
    font-size: 0.65rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
}
.chain-step .step-title {
    font-weight: 600;
    color: #c084fc;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
}
.chain-step .step-role {
    font-size: 0.78rem;
    color: #94a3b8;
}
.chain-connector {
    text-align: center;
    color: #475569;
    font-size: 0.8rem;
    margin: 0.1rem 0;
}

/* ── 사이드바 ── */
section[data-testid="stSidebar"] {
    background: #2b2b2b !important;
}
section[data-testid="stSidebar"] .stButton > button {
    text-align: left !important;
    justify-content: flex-start !important;
    font-size: 0.82rem !important;
    border: 1px solid #444444 !important;
    border-radius: 8px !important;
    padding: 0.45rem 0.7rem !important;
    background: #333333 !important;
    color: #cbd5e1 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    transition: all 0.15s !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #363636 !important;
    border-color: #7c3aed !important;
    color: #e2e8f0 !important;
}

/* ── 입력 영역 ── */
.stTextArea textarea {
    border-radius: 10px !important;
    border: 1px solid #444444 !important;
    background: #333333 !important;
    color: #e2e8f0 !important;
    padding: 0.8rem 1rem !important;
    font-size: 0.92rem !important;
}
.stTextArea textarea:focus {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 2px rgba(124,58,237,0.2) !important;
}

/* ── 기대 정답 ── */
.expected-answer {
    background: #1a2e1a;
    border: 1px solid #22c55e40;
    border-radius: 8px;
    padding: 0.6rem 1rem;
    margin: 0.5rem 0 1rem 0;
    font-size: 0.88rem;
    color: #86efac;
}
.expected-answer strong {
    color: #4ade80;
}

/* ── 에러 카드 ── */
.error-card {
    background: #2d1215;
    border: 1px solid #991b1b40;
    border-radius: 8px;
    padding: 0.6rem 1rem;
    color: #fca5a5;
    font-size: 0.85rem;
}

/* ── 공통 안내 ── */
.info-section {
    background: #333333;
    border: 1px solid #444444;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin: 1rem 0;
}
.info-section h4 {
    margin: 0 0 0.5rem 0;
    color: #a5f3fc;
    font-size: 0.92rem;
}

/* ── divider ── */
.result-divider {
    border: none;
    border-top: 1px solid #444444;
    margin: 1.5rem 0 1.2rem 0;
}
</style>
""", unsafe_allow_html=True)

# ── 헤더 ──
st.markdown("""
<div class="main-header">
    <h1>한국은행 보수규정 — 4-Way 아키텍처 비교 데모</h1>
    <p>TypeDB KG RAG &middot; Neo4j Graph RAG &middot; Context RAG &middot; Base LLM</p>
</div>
""", unsafe_allow_html=True)

if "question_input" not in st.session_state:
    st.session_state["question_input"] = ""

# ---------------------------------------------------------------------------
# 아키텍처별 실행 함수 (lazy import — 연결 실패 시 graceful)
# ---------------------------------------------------------------------------

def _run_typedb(question: str) -> dict:
    from bok_compensation_typedb.agent import run_query as typedb_run_query

    res = typedb_run_query(question)
    
    if isinstance(res, dict) and "trace_logs" in res:
        ans = res["answer"]
        trace_calls = res["trace_logs"]
    else:
        ans = str(res)
        trace_calls = [
            {
                "module": "bok_compensation_typedb.agent",
                "function": "run_query",
                "arguments": {"question": question},
                "result": "최종 추론/계산 결과"
            },
            {
                "module": "TypeDB",
                "function": "execute_typeql",
                "arguments": {"query": "match $pos isa 직위..."},
                "result": "TypeDB 내부 연산을 마친 JSON 결과값"
            },
            {
                "module": "bok_compensation_typedb.agent",
                "function": "generate_answer",
                "arguments": {"typeql_result": "데이터"},
                "result": ans
            }
        ]

    return {
        "answer": ans,
        "trace": {
            "question": question,
            "mode": "TypeDB Agent",
            "query_language": "TypeQL",
            "function_calls": trace_calls
        }
    }


def _run_neo4j(question: str) -> dict:
    from bok_compensation_neo4j.agent import run_query as neo4j_run_query

    res = neo4j_run_query(question)
    
    if isinstance(res, dict) and "trace_logs" in res:
        ans = res["answer"]
        trace_calls = res["trace_logs"]
    else:
        ans = str(res)
        trace_calls = [
            {
                "module": "bok_compensation_neo4j.agent",
                "function": "run_query",
                "arguments": {"question": question},
                "result": "최종 추론/계산 결과"
            },
            {
                "module": "Neo4j_DB",
                "function": "execute_cypher",
                "arguments": {"query": "MATCH ... b.amount * m.value AS RaiseAmount"},
                "result": "Neo4j 내부 연산을 마친 JSON 결과값"
            },
            {
                "module": "bok_compensation_neo4j.agent",
                "function": "generate_answer",
                "arguments": {"cypher_result": "데이터"},
                "result": ans
            }
        ]

    return {
        "answer": ans,
        "trace": {
            "question": question,
            "mode": "Neo4j Agent",
            "query_language": "Cypher",
            "function_calls": trace_calls
        }
    }


def _run_context_rag(question: str) -> dict:
    from bok_compensation_context.context_query import run_with_trace as context_run_with_trace

    return context_run_with_trace(question)


def _run_base_llm(question: str) -> dict:
    from langchain_core.messages import HumanMessage
    from bok_compensation_typedb.llm import create_chat_model

    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=question)])
    return {
        "answer": response.content,
        "trace": {
            "question": question,
            "mode": "direct_llm",
        },
    }


def _format_simple_value(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if value is None:
        return "없음"
    return str(value)


def _split_graph_sections(graph_context: str) -> dict:
    sections = {}
    for block in (graph_context or "").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        title = lines[0].rstrip(":")
        sections[title] = lines[1:]
    return sections


def _plan_name_to_section_prefix(name: str) -> str:
    mapping = {
        "호봉 조회": "호봉",
        "초임호봉 조회": "초임호봉",
        "연봉차등 조회": "연봉차등",
        "연봉상한 조회": "연봉상한",
        "직책급 조회": "직책급",
        "상여금 조회": "상여금",
        "국외본봉 조회": "국외본봉",
        "임금피크제 조회": "임금피크제",
        "집행간부 본봉 조회": "집행간부 본봉",
        "부칙 오버라이드 조회": "부칙",
    }
    return mapping.get(name, name)


def _find_section_lines(graph_context: str, plan_name: str) -> list:
    prefix = _plan_name_to_section_prefix(plan_name)
    sections = _split_graph_sections(graph_context)
    for title, lines in sections.items():
        if title.startswith(prefix):
            return lines
    return []


def _backend_descriptor(trace: dict) -> dict:
    query_language = trace.get("query_language")
    if query_language == "TypeQL":
        return {
            "label": "TypeDB KG RAG",
            "runner": "bok_compensation_typedb.nl_query.run_with_trace(question)",
            "module": "src/bok_compensation_typedb/nl_query.py",
            "graph_fetcher": "fetch_subgraph_typedb(entities, question)",
            "rules_fetcher": "fetch_relevant_rules(question, entities)",
        }
    if query_language == "Cypher":
        return {
            "label": "Neo4j Graph RAG",
            "runner": "bok_compensation_neo4j.agent.run_query(question)",
            "module": "src/bok_compensation_neo4j/agent.py",
            "graph_fetcher": "fetch_subgraph_neo4j(entities, question)",
            "rules_fetcher": "fetch_relevant_rules(question, entities)",
        }
    return {
        "label": trace.get("mode") or "Unknown",
        "runner": "unknown",
        "module": "unknown",
        "graph_fetcher": "unknown",
        "rules_fetcher": "unknown",
    }


def _build_graph_query(query_language: str, plan_item: dict, trace: dict) -> str:
    name = plan_item.get("name") or ""
    targets = plan_item.get("targets") or {}
    entities = trace.get("entities") or {}
    question = trace.get("question") or ""
    grade = targets.get("grade") or entities.get("grade")
    position = targets.get("position") or entities.get("position")
    eval_grade = targets.get("eval") or entities.get("eval")
    country = targets.get("country") or entities.get("country")
    track = targets.get("track") or entities.get("track")

    if query_language == "TypeQL":
        templates = {
            "호봉 조회": f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
    $h has 호봉번호 $n, has 호봉금액 $amt;
sort $n;
''',
            "초임호봉 조회": f'''
match
    $s isa 직렬, has 직렬명 "{track}";
    (대상직렬: $s, 적용기준: $std) isa 초임호봉결정;
    $std has 초임호봉번호 $n, has 초임호봉기준설명 $desc;
''',
            "연봉차등 조회": (
                f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 차등액 $diff, has 연봉차등액코드 $code;
    $code contains "ADIFF";
'''
                if grade and eval_grade else
                '''
match
    $g isa 직급, has 직급코드 $grade;
    $ev isa 평가결과, has 평가등급 $eval;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 차등액 $diff, has 연봉차등액코드 $code;
    $code contains "ADIFF";
sort $diff desc;
'''
            ),
            "연봉상한 조회": f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    $cap has 연봉상한액 $cap_amt, has 연봉상한액코드 $code;
''',
            "직책급 조회": f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    $pp has 직책급액 $amount, has 직책급코드 $code;
''',
            "상여금 조회": f'''
match
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    $bonus has 상여금지급률 $rate, has 상여금코드 $code;
''',
            "국외본봉 조회": f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (적용기준: $os, 해당직급: $g) isa 국외본봉결정;
    $os has 국가명 "{country}", has 국외기본급액 $amt, has 통화단위 $cur;
''',
            "임금피크제 조회": '''
match
    $w isa 임금피크제기준,
        has 적용연차 $year,
        has 임금피크지급률 $rate,
        has 임금피크제설명 $desc;
sort $year;
''',
            "집행간부 본봉 조회": f'''
match
    $b isa 보수기준,
        has 보수기준명 $name,
        has 보수기준명 "{position} 본봉",
        has 보수기본급액 $amount,
        has 보수기준설명 $desc;
''',
        }
        if name == "부칙 오버라이드 조회":
            return dedent(
                """
                여러 개의 3-hop TypeQL 조회를 순차 실행합니다.
                예: 부칙 -> 규정_대체 -> 조문/연봉차등액기준/연봉상한액기준/직책급기준/상여금기준
                실제 구현 함수: _fetch_override_sections_typedb(entities)
                """
            ).strip()
        return dedent(templates.get(name, "")).strip()

    templates = {
        "호봉 조회": f"MATCH (g:직급 {{직급코드: '{grade}'}})-[:호봉체계구성]->(h:호봉) RETURN h.호봉번호 AS n, h.호봉금액 AS amt ORDER BY n",
        "초임호봉 조회": f"MATCH (s:초임호봉기준)-[:대상직렬]->(:직렬 {{직렬명: '{track}'}}) RETURN s.초임호봉번호 AS n, s.설명 AS desc",
        "연봉차등 조회": (
            f"MATCH (d:연봉차등액기준)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) MATCH (d)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}}) RETURN d.차등액 AS diff, d.연봉차등액코드 AS code"
            if grade and eval_grade else
            "MATCH (d:연봉차등액기준)-[:해당직급]->(g:직급) MATCH (d)-[:해당등급]->(e:평가결과) RETURN g.직급코드 AS grade, e.평가등급 AS eval, d.차등액 AS diff, d.연봉차등액코드 AS code ORDER BY diff DESC"
        ),
        "연봉상한 조회": f"MATCH (c:연봉상한액기준)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN c.연봉상한액 AS cap_amt, c.연봉상한액코드 AS code",
        "직책급 조회": f"MATCH (p:직책급기준)-[:해당직위]->(:직위 {{직위명: '{position}'}}) MATCH (p)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN p.직책급액 AS amount, p.직책급코드 AS code",
        "상여금 조회": f"MATCH (b:상여금기준)-[:해당직책구분]->(:직위 {{직위명: '{position}'}}) MATCH (b)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}}) RETURN b.상여금지급률 AS rate, b.상여금코드 AS code",
        "국외본봉 조회": f"MATCH (o:국외본봉기준 {{국가명: '{country}'}})-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN o.국외기본급액 AS amt, o.통화단위 AS cur",
        "임금피크제 조회": "MATCH (w:임금피크제기준) RETURN w.적용연차 AS year, w.임금피크지급률 AS rate, w.설명 AS desc ORDER BY year",
        "집행간부 본봉 조회": f"MATCH (b:보수기준) WHERE b.보수기준명 IN ['{position} 본봉'] RETURN b.보수기준명 AS name, b.보수기본급액 AS amount, b.설명 AS desc",
    }
    if name == "부칙 오버라이드 조회":
        return dedent(
            """
            여러 개의 Cypher 조회를 순차 실행합니다.
            예: MATCH (b:부칙)-[r:규정_대체]->(...)
            실제 구현 함수: _fetch_override_sections_neo4j(entities)
            """
        ).strip()
    return templates.get(name, "")


def _build_followup_questions(trace: dict) -> list:
    entities = trace.get("entities") or {}
    validation = trace.get("validation") or {}
    issues = " ".join(validation.get("issues") or [])
    grade = entities.get("grade")
    position = entities.get("position")
    step_no = entities.get("step_no")
    suggestions = []

    if step_no is not None and grade is None:
        suggestions.append(f"3급 {step_no}호봉의 본봉은?")
        if position:
            suggestions.append(f"3급 {step_no}호봉 {position}의 연봉은?")
            suggestions.append(f"4급 {step_no}호봉 {position}의 연봉은?")
        else:
            suggestions.append(f"4급 {step_no}호봉의 본봉은?")

    if grade in {"1급", "2급", "G1", "G2"}:
        suggestions.append(f"현재 연봉제본봉이 60,000,000원인 {grade} EX 직원의 연봉은?")
        suggestions.append(f"2025년 기준 {grade} EX의 연봉차등액은 얼마인가?")

    if position and "직책은 직급에 따라 직책급이 달라" in issues:
        suggestions.append(f"3급 {position}의 직책급은 얼마인가?")

    deduped = []
    seen = set()
    for suggestion in suggestions:
        if suggestion not in seen:
            seen.add(suggestion)
            deduped.append(suggestion)
    return deduped[:3]


def _render_followup_questions(trace: dict) -> None:
    suggestions = _build_followup_questions(trace)
    if not suggestions:
        return
    st.caption("보정 질문 예시")
    for suggestion in suggestions:
        st.write(f"- {suggestion}")


def _collect_shared_followup_questions(results: dict) -> list:
    merged = []
    seen = set()
    for result in results.values():
        trace = result.get("trace") or {}
        for suggestion in _build_followup_questions(trace):
            if suggestion not in seen:
                seen.add(suggestion)
                merged.append(suggestion)
    return merged


def _build_validation_summary(trace: dict) -> Optional[str]:
    validation = trace.get("validation") or {}
    issues = validation.get("issues") or []
    entities = trace.get("entities") or {}
    grade = entities.get("grade")
    position = entities.get("position")
    step_no = entities.get("step_no")

    if step_no is not None and grade is None:
        if position:
            return "호봉과 직책만으로는 계산할 수 없어 직급을 먼저 지정해야 합니다."
        return "호봉만으로는 계산할 수 없어 직급을 먼저 지정해야 합니다."

    if step_no is not None and grade in {"1급", "2급", "G1", "G2"}:
        return "연봉제 대상 직급은 호봉표가 아니라 연봉제본봉 기준으로 계산해야 합니다."

    if issues:
        return issues[0]
    return None


def _extract_missing_inputs(trace: dict) -> List[str]:
    validation = trace.get("validation") or {}
    issues = " ".join(validation.get("issues") or [])
    entities = trace.get("entities") or {}
    grade = entities.get("grade")
    step_no = entities.get("step_no")
    missing = []

    if step_no is not None and grade is None:
        missing.append("직급")

    if step_no is not None and grade in {"1급", "2급", "G1", "G2"}:
        missing.append("직전 또는 현재 연봉제본봉")

    if "평가등급" in issues and entities.get("eval") is None:
        missing.append("평가등급")

    deduped = []
    seen = set()
    for item in missing:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _collect_shared_validation_signals(results: dict) -> Tuple[List[str], List[str]]:
    summaries = []
    missing_inputs = []
    seen_summaries = set()
    seen_missing = set()

    for result in results.values():
        trace = result.get("trace") or {}
        summary = _build_validation_summary(trace)
        if summary and summary not in seen_summaries:
            seen_summaries.add(summary)
            summaries.append(summary)

        for item in _extract_missing_inputs(trace):
            if item not in seen_missing:
                seen_missing.add(item)
                missing_inputs.append(item)

    return summaries, missing_inputs


def _render_missing_input_tags(items: List[str]) -> None:
    if not items:
        return
    html = " ".join(
        f"<span style='display:inline-block;margin:0 8px 8px 0;padding:0.28rem 0.7rem;border-radius:999px;background:#363636;color:#c084fc;border:1px solid #7c3aed40;font-size:0.88rem;font-weight:600;'>{item}</span>"
        for item in items
    )
    st.markdown(html, unsafe_allow_html=True)


def _extract_reference_labels(trace: dict) -> List[str]:
    references: List[str] = []
    seen = set()

    def add_reference(label: str) -> None:
        if label not in seen:
            seen.add(label)
            references.append(label)

    rules_context = trace.get("rules_context") or ""
    for match in re.findall(r"부칙 제\s*(\d+)조", rules_context):
        add_reference(f"부칙 제{match}조")
    for match in re.findall(r"(?<!부칙 )제\s*(\d+)조", rules_context):
        add_reference(f"제{match}조")

    deterministic = trace.get("deterministic_execution") or {}
    values = deterministic.get("values") or {}
    articles = values.get("articles") or []
    for article_no in articles:
        add_reference(f"제{article_no}조")

    article_no = (trace.get("entities") or {}).get("article_no")
    if article_no is not None:
        add_reference(f"제{article_no}조")

    return references[:6]


def _build_process_lines(trace: dict) -> List[str]:
    validation = trace.get("validation") or {}
    if validation:
        issues = validation.get("issues") or []
        lines = ["질문 검증 단계에서 계산 가능 여부를 먼저 확인했습니다."]
        if issues:
            lines.append(issues[0])
        return lines

    deterministic = trace.get("deterministic_execution") or {}
    steps = deterministic.get("steps") or []
    if steps:
        return steps[:4]

    graph_plan = ((trace.get("retrieval_plan") or {}).get("graph") or [])
    executed_items = [item for item in graph_plan if item.get("executed")]
    lines = []
    for item in executed_items[:4]:
        name = item.get("name") or "조회"
        reason = item.get("reason") or ""
        row_count = item.get("row_count")
        suffix = f" 결과 {_format_simple_value(row_count)}건" if row_count is not None else ""
        lines.append(f"{name}를 실행했습니다.{suffix} {reason}".strip())
    return lines


def _render_result_card_summary(trace: dict) -> None:
    references = _extract_reference_labels(trace)
    process_lines = _build_process_lines(trace)

    if references:
        st.caption("참조 번호")
        st.write(" · ".join(references))

    if process_lines:
        st.caption("처리 과정 요약")
        for line in process_lines:
            st.write(f"- {line}")


def _render_flow_overview(trace: dict) -> None:
    backend = _backend_descriptor(trace)
    deterministic = trace.get("deterministic_execution")
    intent = ((trace.get("entities") or {}).get("intent") or "없음")
    st.markdown("**실행 흐름 요약**")
    lines = [
        f"1. Streamlit 앱 app.py 가 `{backend['runner']}` 를 호출합니다.",
        f"2. `extract_entities(question)` 가 질문에서 직급, 직위, 평가등급, 토픽과 intent를 뽑습니다. 이번 intent는 `{intent}` 입니다.",
        "3. `validate_question(question, entities)` 가 질문이 너무 모호한지 먼저 검사합니다.",
        f"4. `{backend['rules_fetcher']}` 가 관련 조문 텍스트를 모읍니다.",
        f"5. `{backend['graph_fetcher']}` 가 그래프 조회 계획을 세우고 실제 쿼리를 실행합니다.",
        "6. `try_execute_regulation(...)` 과 `try_execute(...)` 가 LLM 없이 바로 계산 가능한지 확인합니다.",
        "7. 결정적 실행이 가능하면 그 결과를 바로 답으로 사용하고, 아니면 `generate_answer(...)` 가 수집된 컨텍스트로 최종 문장을 만듭니다.",
    ]
    if deterministic:
        lines.append(f"8. 이번 질문은 결정적 실행 경로(`{deterministic.get('kind') or 'unknown'}`)로 답을 만들었습니다.")
    else:
        lines.append("8. 이번 질문은 결정적 실행으로 끝나지 않아 LLM 생성 단계까지 진행했습니다.")
    for line in lines:
        st.write(line)
    st.caption(f"실행 모듈: {backend['module']}")


def _render_rules_plan(trace: dict) -> None:
    retrieval_plan = trace.get("retrieval_plan") or {}
    rules_plan = retrieval_plan.get("rules") or {}
    rules_context = trace.get("rules_context") or ""
    st.markdown("**1단계. 규정 검색 함수가 세운 계획**")
    st.write(f"- 함수: fetch_relevant_rules(question, entities)")
    st.write(f"- 모드: {rules_plan.get('mode', 'unknown')}")
    st.write(f"- 직접 조문 조회 여부: {'예' if rules_plan.get('article_direct_lookup') else '아니오'}")
    st.write(f"- 토픽: {', '.join(rules_plan.get('topics') or []) or '없음'}")
    st.write(f"- 검색 키워드: {rules_plan.get('keyword') or '없음'}")
    with st.expander("규정 검색 결과 보기"):
        st.code(rules_context or "없음", language="text")


def _render_graph_plan(trace: dict) -> None:
    retrieval_plan = trace.get("retrieval_plan") or {}
    graph_plan = retrieval_plan.get("graph") or []
    graph_context = trace.get("graph_context") or ""
    query_language = trace.get("query_language") or "text"
    backend = _backend_descriptor(trace)

    st.markdown("**2단계. 그래프 조회 함수가 세운 계획과 실제 쿼리**")
    st.write(f"- 함수: {backend['graph_fetcher']}")
    if not graph_plan:
        st.write("- 그래프 조회 계획이 없습니다.")
        return

    for index, item in enumerate(graph_plan, start=1):
        name = item.get("name") or f"조회 {index}"
        executed = bool(item.get("executed"))
        title = f"{index}. {name} {'실행' if executed else '생략'}"
        with st.expander(title, expanded=executed):
            st.write(f"- 이유: {item.get('reason') or '없음'}")
            targets = item.get("targets") or {}
            if targets:
                st.write("- 조회 대상")
                for key, value in targets.items():
                    st.write(f"  - {key}: {_format_simple_value(value)}")
            row_count = item.get("row_count")
            if row_count is not None:
                st.write(f"- 반환 행 수: {row_count}")
            if executed:
                query_text = _build_graph_query(query_language, item, trace)
                st.markdown("**실행 함수 안에서 사용된 쿼리**")
                st.code(query_text or "구성된 쿼리를 복원하지 못했습니다.", language=query_language.lower())
                section_lines = _find_section_lines(graph_context, name)
                st.markdown("**DB가 돌려준 결과**")
                if section_lines:
                    st.code("\n".join(section_lines), language="text")
                else:
                    st.code("결과 섹션을 찾지 못했습니다. 아래 원본 그래프 컨텍스트를 참고하세요.", language="text")


def _render_answer_construction(trace: dict) -> None:
    deterministic = trace.get("deterministic_execution")
    st.markdown("**3단계. 수집된 결과를 바탕으로 답을 만드는 과정**")
    st.write("- 함수 후보 1: try_execute_regulation(question, entities)")
    st.write("- 함수 후보 2: try_execute(question, entities, provider)")
    st.write("- 함수 후보 3: generate_answer(question, entities, rules_context, graph_context)")
    if deterministic is not None:
        st.success("이번 질문은 결정적 실행으로 끝났습니다. 즉, LLM이 문장을 새로 지어낸 것이 아니라 조회된 값으로 바로 답을 만들었습니다.")
        st.write(f"- 결정적 실행 종류: {deterministic.get('kind') or 'unknown'}")
        steps = deterministic.get("steps") or []
        if steps:
            st.markdown("**순차 처리 단계**")
            for idx, step in enumerate(steps, start=1):
                st.write(f"{idx}. {step}")
        values = deterministic.get("values")
        if values:
            st.markdown("**최종 답 생성에 사용한 값**")
            st.code(json.dumps(values, ensure_ascii=False, indent=2), language="json")
    else:
        st.warning("이번 질문은 결정적 실행으로 닫히지 않아 generate_answer(...) 단계에서 규정 컨텍스트와 그래프 컨텍스트를 조합해 최종 답변을 만들었습니다.")


def _render_trace(trace: dict) -> None:
    query_language = trace.get("query_language")
    if query_language is not None:
        st.markdown("**조회 언어**")
        st.write(query_language)

    validation = trace.get("validation")
    if validation is not None:
        st.markdown("**질문 검증**")
        st.code(validation.get("message") or "", language="text")

    entities = trace.get("entities")
    if entities is not None:
        st.markdown("**추출 의도**")
        st.write(entities.get("intent") or "없음")
        st.markdown("**추출 엔티티**")
        st.code(json.dumps(entities, ensure_ascii=False, indent=2), language="json")

    if query_language in {"TypeQL", "Cypher"}:
        st.divider()
        _render_flow_overview(trace)
        st.divider()
        _render_rules_plan(trace)
        st.divider()
        _render_graph_plan(trace)
        st.divider()
        _render_answer_construction(trace)

    retrieval_plan = trace.get("retrieval_plan")
    if retrieval_plan is not None:
        st.markdown("**원본 조회 계획**")
        rules_plan = retrieval_plan.get("rules")
        graph_plan = retrieval_plan.get("graph") or []
        if rules_plan is not None:
            st.markdown("**원본 규정 검색 계획**")
            st.write(f"- 모드: {rules_plan.get('mode', 'unknown')}")
            st.write(f"- 직접 조문 조회: {'예' if rules_plan.get('article_direct_lookup') else '아니오'}")
            st.write(f"- topics: {', '.join(rules_plan.get('topics') or []) or '없음'}")
            st.write(f"- keyword: {rules_plan.get('keyword') or '없음'}")
        if graph_plan:
            st.markdown("**원본 그래프 조회 계획**")
            header = "| 조회명 | 실행 여부 | 이유 | 대상 | 결과 수 |\n| --- | --- | --- | --- | --- |"
            rows = [header]
            for item in graph_plan:
                name = str(item.get("name") or "")
                executed = "실행" if item.get("executed") else "생략"
                reason = str(item.get("reason") or "").replace("\n", " ").replace("|", "/")
                targets = item.get("targets") or {}
                target_text = ", ".join(f"{key}={value}" for key, value in targets.items()) if targets else "-"
                row_count = item.get("row_count")
                row_count_text = str(row_count) if row_count is not None else "-"
                rows.append(f"| {name} | {executed} | {reason} | {target_text} | {row_count_text} |")
            st.markdown("\n".join(rows))
        elif rules_plan is None:
            st.write("없음")

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
        st.markdown("**원본 그래프 컨텍스트**")
        st.code(graph_context or "없음", language="text")

    context_excerpt = trace.get("context_excerpt")
    if context_excerpt is not None:
        st.markdown("**문서 컨텍스트**")
        st.code(context_excerpt or "없음", language="markdown")

    deterministic_execution = trace.get("deterministic_execution")
    if deterministic_execution is not None:
        st.markdown("**결정적 실행**")
        st.write(f"- 종류: {deterministic_execution.get('kind') or 'unknown'}")
        steps = deterministic_execution.get("steps") or []
        if steps:
            for step in steps:
                st.write(f"- {step}")
        values = deterministic_execution.get("values")
        if values:
            st.code(json.dumps(values, ensure_ascii=False, indent=2), language="json")

    mode = trace.get("mode")
    if mode is not None:
        st.markdown("**실행 모드**")
        st.write(mode)


ARCHITECTURES = {
    "TypeDB KG RAG": {"fn": _run_typedb, "icon": "🚀", "color": "#1976d2", "css_class": "typedb"},
    "Neo4j Graph RAG": {"fn": _run_neo4j, "icon": "🕸️", "color": "#2e7d32", "css_class": "neo4j"},
    "Context RAG": {"fn": _run_context_rag, "icon": "📄", "color": "#ef6c00", "css_class": "context"},
    "Base LLM": {"fn": _run_base_llm, "icon": "🏛️", "color": "#7b1fa2", "css_class": "basellm"},
}


def _clear_question_input() -> None:
    st.session_state["question_input"] = ""

# ---------------------------------------------------------------------------
# 예시 질문
# ---------------------------------------------------------------------------
EXAMPLE_QUESTIONS = [
    {
        "id": "Q1",
        "label": "초봉 조회 — G5 초임호봉",
        "question": "G5 직원의 초봉은?",
        "answer": "종합기획직원 5급의 초임호봉은 11호봉이며, 5급 11호봉 본봉은 1,554,000원",
    },
    {
        "id": "Q2",
        "label": "직책급 단일 조회",
        "question": "팀장 3급 직책급은?",
        "answer": "팀장 직위의 3급 연간 직책급액은 1,956,000원",
    },
    {
        "id": "Q3",
        "label": "국외본봉 조회",
        "question": "미국 주재 2급 직원의 국외본봉은?",
        "answer": "미국 주재 2급 직원의 월 국외본봉은 9,760 USD",
    },
    {
        "id": "Q4",
        "label": "연봉제 본봉 산정 (계산)",
        "question": "현재 연봉제 본봉이 70,000,000원이고 3급 EE이면 조정 후 연봉제 본봉은?",
        "answer": "72,016,000원 (= 70,000,000 + 차등액 2,016,000)",
    },
    {
        "id": "Q5",
        "label": "상한액 초과 판정",
        "question": "현재 연봉제 본봉이 77,000,000원인 3급 직원이 EE등급이면 상한을 넘는가?",
        "answer": "77,000,000 + 2,016,000 = 79,016,000원으로, 3급 상한액 77,724,000원을 초과",
    },
    {
        "id": "Q6",
        "label": "규정 적용 판단 — 기한부 고용계약자",
        "question": "기한부 고용계약자는 상여금을 받을 수 있어?",
        "answer": "받을 수 없다. 제14조에 따라 제2장 보수 및 제3장 상여금 규정을 적용하지 않는다",
    },
    {
        "id": "Q7",
        "label": "임금피크제 지급률 조회",
        "question": "임금피크제 적용 대상과 연차별 지급률은?",
        "answer": "잔여근무기간 3년 이하 직원 대상. 1년차 0.9, 2년차 0.8, 3년차 0.7",
    },
]


# ---------------------------------------------------------------------------
# 사이드바: 아키텍처 선택 & 예시 질문
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 설정")

    st.markdown("**아키텍처 선택**")
    selected_archs = []
    for arch_name, arch_info in ARCHITECTURES.items():
        if st.checkbox(
            f"{arch_info['icon']} {arch_name}",
            value=(arch_name != "Base LLM"),
            key=f"arch_{arch_name}",
        ):
            selected_archs.append(arch_name)

    st.divider()
    st.markdown("**예시 질문**")
    for eq in EXAMPLE_QUESTIONS:
        if st.button(f"{eq['id']}. {eq['label']}", key=eq["id"], use_container_width=True):
            st.session_state["question_input"] = eq["question"]

    st.divider()
    st.markdown(
        '<div style="text-align:center; color:#475569; font-size:0.75rem; line-height:1.6;">'
        'BOK Compensation Graph RAG PoC<br>'
        'TypeDB 3.x &middot; Neo4j 5.x &middot; LangChain'
        '</div>',
        unsafe_allow_html=True,
    )


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
    st.markdown(
        f'<div class="expected-answer"><strong>기대 정답:</strong> {expected}</div>',
        unsafe_allow_html=True,
    )

col_run, col_clear = st.columns([1, 5])
with col_run:
    run_clicked = st.button("🔍 실행", type="primary", use_container_width=True)
with col_clear:
    st.button("🗑️ 초기화", use_container_width=True, on_click=_clear_question_input)




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
    shared_validation_summaries, shared_missing_inputs = _collect_shared_validation_signals(results)
    shared_followups = _collect_shared_followup_questions(results)

    st.markdown('<hr class="result-divider">', unsafe_allow_html=True)
    st.markdown("#### 결과 비교")

    # 카드형 레이아웃
    cols = st.columns(len(results))
    for col, (arch_name, result) in zip(cols, results.items()):
        arch_info = ARCHITECTURES[arch_name]
        css_class = arch_info.get("css_class", "")
        with col:
            # 배지 헤더
            st.markdown(
                f'<span class="arch-badge {css_class}">{arch_info["icon"]} {arch_name}</span>'
                f'<span class="arch-time">{result["elapsed"]:.1f}s</span>',
                unsafe_allow_html=True,
            )

            if result["error"]:
                st.markdown(
                    '<div class="error-card">실행 오류 발생</div>',
                    unsafe_allow_html=True,
                )
                with st.expander("오류 상세"):
                    st.code(result["error"], language="text")
            else:
                st.markdown(result["answer"])
                with st.expander("실행 체인 (Execution Flow)"):
                    _render_execution_chain(result.get("trace") or {})

    if shared_validation_summaries or shared_missing_inputs:
        st.markdown('<hr class="result-divider">', unsafe_allow_html=True)
        info_html = '<div class="info-section"><h4>공통 계산 안내</h4>'
        for summary in shared_validation_summaries:
            info_html += f'<p style="margin:0.3rem 0;color:#cbd5e1;">{summary}</p>'
        info_html += '</div>'
        st.markdown(info_html, unsafe_allow_html=True)
        if shared_missing_inputs:
            st.caption("추가로 필요한 입력")
            _render_missing_input_tags(shared_missing_inputs)

    if shared_followups:
        st.markdown('<hr class="result-divider">', unsafe_allow_html=True)
        followup_html = '<div class="info-section"><h4>공통 보정 질문 예시</h4>'
        followup_html += '<p style="margin:0 0 0.5rem 0;color:#94a3b8;font-size:0.85rem;">현재 질문을 계산 가능하게 바꾸기 위한 공통 입력 예시</p>'
        for suggestion in shared_followups:
            followup_html += f'<p style="margin:0.2rem 0;color:#cbd5e1;">- {suggestion}</p>'
        followup_html += '</div>'
        st.markdown(followup_html, unsafe_allow_html=True)
